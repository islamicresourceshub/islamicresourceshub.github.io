"""Archive discovery + PDF/TXT downloads + inbox watcher."""
from __future__ import annotations

import re
import shutil
import time
from pathlib import Path
from urllib.parse import urljoin, unquote

import httpx
from bs4 import BeautifulSoup

from .config import Config
from .db import Store, now
from .utils import date_token, iso_from_text_url

PDF_HREF = re.compile(r"\.pdf(\?|$)", re.I)
TEXT_HREF = re.compile(r"issue-\d+-20\d{2}-[a-z]+-\d{1,2}\.html(\?|$)", re.I)


class Crawler:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.delay = cfg["source"]["request_delay_seconds"]
        self.ua = cfg["source"]["user_agent"]
        self._last = 0.0
        from .llm import shared_client
        self._http = shared_client(60)

    def _throttle(self):
        wait = self.delay - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)

    def fetch(self, url: str) -> httpx.Response:
        self._throttle()
        r = self._http.get(url, headers={"User-Agent": self.ua}, follow_redirects=True)
        r.raise_for_status()
        self._last = time.time()
        return r

    def _links(self, page_url: str, pattern: re.Pattern) -> dict[str, str]:
        """token -> absolute URL for matching links on a page."""
        html = self.fetch(page_url).text
        soup = BeautifulSoup(html, "lxml")
        base = page_url
        base_tag = soup.find("base", href=True)
        if base_tag:
            base = urljoin(page_url, base_tag["href"])
        out: dict[str, str] = {}
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if pattern.search(href.lower()):
                absu = urljoin(base, href)
                fname = Path(unquote(absu)).name
                token = self._token(fname, absu)
                if token:
                    out[token] = absu
        return out

    @staticmethod
    def _token(fname: str, absu: str) -> str | None:
        if absu.lower().endswith(".pdf"):
            return date_token(fname)[0] or None   # ISO date as pairing key ('' -> None)
        return iso_from_text_url(absu)[0] or None

    def discover(self, store: Store) -> int:
        """Crawl all listing pages, register new issues. Returns count added."""
        pdfs: dict[str, str] = {}
        txts: dict[str, str] = {}
        for u in self.cfg["source"]["listing_urls"]:
            try:
                pdfs.update(self._links(u, PDF_HREF))
                txts.update(self._links(u, TEXT_HREF))
            except Exception as e:
                print(f"[crawler] listing failed: {u} ({e})")
        added = 0
        for token, pdf_url in sorted(pdfs.items()):
            iso_date, year = self._meta_from_url(pdf_url)
            txt_url = txts.get(token)
            before = store.q("SELECT 1 FROM issues WHERE pdf_url=?", (pdf_url,))
            store.upsert_issue(pdf_url, year, iso_date, txt_url)
            if not before:
                added += 1
        print(f"[crawler] discovered {added} new issue(s); total known={len(pdfs)}")
        return added

    def _meta_from_url(self, url: str) -> tuple[str, int | None]:
        return date_token(Path(unquote(url)).name)

    # ---- downloads ----
    def download_issue(self, store: Store, issue) -> bool:
        archive = self.cfg.root / "archive"
        try:
            pdf_path = self._download(issue["pdf_url"], archive)
            txt_path = None
            if issue["txt_url"]:
                try:
                    txt_path = self._download(issue["txt_url"], archive)
                except Exception as e:
                    print(f"[crawler] TXT optional, skipping ({e})")
            store.x(
                "UPDATE issues SET status='downloaded', pdf_path=?, txt_path=?, downloaded_at=?, error=NULL WHERE id=?",
                (str(pdf_path), str(txt_path) if txt_path else None, now(), issue["id"]),
            )
            return True
        except Exception as e:
            attempts = issue["attempts"] + 1
            status = "failed" if attempts >= self.cfg["pipeline"]["max_attempts"] else "discovered"
            store.x("UPDATE issues SET attempts=?, error=?, status=? WHERE id=?", (attempts, str(e)[:500], status, issue["id"]))
            print(f"[crawler] download FAILED {issue['pdf_url']}: {e}")
            return False

    def _download(self, url: str, archive_dir: Path) -> Path:
        if url.startswith("inbox://"):
            return Path(unquote(url[len("inbox://"):]))
        fname = Path(unquote(url)).name
        year = date_token(fname)[1]
        target_dir = archive_dir / str(year) if year else archive_dir / "misc"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / fname
        if target.exists() and target.stat().st_size > 0:
            return target
        r = self.fetch(url)
        target.write_bytes(r.content)
        print(f"[crawler] saved {fname} ({len(r.content)//1024} KB)")
        return target

    # ---- inbox ----
    # ---- per-issue full-text harvesting ----
    NAV_BLACKLIST = {"archives", "search", "flip", "index"}

    def fetch_issue_articles(self, issue) -> list[dict]:
        """Fetch the issue's text page, follow article links, return full texts."""
        import json as _json
        cache = self.cfg.root / "work" / f"issue-{issue['id']}" / "site_articles.json"
        if cache.exists():
            return _json.loads(cache.read_text(encoding="utf-8"))
        base_issue_url = issue["txt_url"]
        r = self.fetch(base_issue_url)
        soup = BeautifulSoup(r.text, "lxml")
        vol_prefix = "/" + base_issue_url.split("nerpatham.com/")[-1].split("/")[0] + "/"
        candidates: dict[str, str] = {}
        body_tag = soup.find(itemprop="articleBody") or soup.find("div", class_="item-page") or soup
        for a in body_tag.find_all("a", href=True):
            absu = urljoin(base_issue_url, a["href"])
            if "nerpatham.com" not in absu:
                continue
            path = absu.split("nerpatham.com/")[-1]
            segs = [s for s in path.split("/") if s]
            if len(segs) != 2 or not segs[1].endswith(".html"):
                continue
            vol, slug = segs
            if f"/{vol}/" != vol_prefix or slug.startswith("vol-no"):
                continue
            if slug.rsplit(".", 1)[0] in self.NAV_BLACKLIST or "/archives" in absu:
                continue
            if a.get_text(strip=True):
                candidates[path] = urljoin(base_issue_url, absu if absu.startswith("http") else "http://nerpatham.com/" + path)
        out = []
        for path, url in sorted(candidates.items()):
            try:
                art_soup = BeautifulSoup(self.fetch(url).text, "lxml")
                body_div = art_soup.find(itemprop="articleBody") or art_soup.find("div", class_="item-page")
                if not body_div:
                    continue

                # ---- collect + download images BEFORE conversion ----
                images = []
                img_dir = self.cfg.root / "work" / f"issue-{issue['id']}" / "imgs"
                img_dir.mkdir(parents=True, exist_ok=True)
                for n, img in enumerate(body_div.find_all("img")):
                    src = img.get("src") or img.get("data-src")
                    if not src:
                        img.decompose()
                        continue
                    abs_src = urljoin(url, src)
                    fname = re.sub(r"[^A-Za-z0-9._-]", "_", Path(abs_src).name) or f"img-{n}.jpg"
                    dest = img_dir / fname
                    try:
                        if not (dest.exists() and dest.stat().st_size > 0):
                            data = self.fetch(abs_src).content
                            if len(data) < 3000 or len(data) > 8 * 1024 * 1024:
                                img.decompose()
                                continue  # skip icons & monsters
                            dest.write_bytes(data)
                        img["src"] = abs_src          # absolute for md conversion
                        images.append({"url": abs_src, "file": fname, "path": str(dest)})
                    except Exception as e:
                        print(f"[img] skipped {abs_src}: {e}")
                        img.decompose()
                        continue

                # ---- strip non-content nodes ----
                for tag in body_div.find_all(["script", "style", "iframe", "form", "button", "noscript"]):
                    tag.decompose()

                # ---- HTML -> rich Markdown ----
                from markdownify import MarkdownConverter
                converter = MarkdownConverter(heading_style="ATX", bullets="-", strong_em_symbol="*", wrap=False)
                text = converter.convert_soup(body_div)
                text = re.sub(r"\n{3,}", "\n\n", text).strip()
                if len(text) < 400:
                    continue
                h = art_soup.find(["h1", "h2"])
                author_h = None
                for hh in art_soup.find_all(["h1", "h2", "h3"]):
                    if hh is not h and hh.get_text(strip=True) and len(hh.get_text(strip=True)) < 80:
                        author_h = hh.get_text(strip=True)
                        break
                title_h = h.get_text(strip=True) if h else ""
                lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
                norm = lambda s: s.lstrip("#").strip()
                # Column-page pattern: <h> holds the column name; real title/author/date
                # are the first body lines (e.g. title / author / '2017 January 21 1438 ...')
                if (
                    len(lines) > 3
                    and title_h
                    and norm(lines[0]) != title_h
                    and not norm(lines[0]).startswith("![")
                    and re.search(r"20\d{2}", " ".join(norm(x) for x in lines[2:4]))
                ):
                    title_real = norm(lines[0])
                    author_real = norm(lines[1]).lstrip("*").rstrip("*").strip()
                    text = "\n\n".join(lines[3:])
                    out_title, out_author = title_real, author_real
                else:
                    out_title, out_author = title_h, author_h
                out.append({
                    "url": url,
                    "title": out_title[:300],
                    "author": out_author or "",
                    "body": text,
                    "images": images,
                })
                print(f"[txt-harvest] {len(out)}: {out[-1]['title'][:60]} ({len(text)} chars)")
            except Exception as e:
                print(f"[txt-harvest] failed {url}: {e}")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(_json.dumps(out, ensure_ascii=False), encoding="utf-8")
        print(f"[txt-harvest] issue #{issue['id']}: harvested {len(out)} full-text articles")
        return out

    def scan_inbox(self, store: Store) -> int:
        inbox = self.cfg.root / "inbox"
        added = 0
        for f in sorted(inbox.glob("*.pdf")):
            iso_date, year = date_token(f.name)
            dest_dir = self.cfg.root / "archive" / str(year or "manual")
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f.name
            shutil.move(str(f), str(dest))
            store.upsert_issue(f"inbox://{dest}", year, iso_date or None, None)
            added += 1
            print(f"[inbox] accepted {f.name}")
        return added
