"""Static site generation + git publishing for adishmuhammed.github.io."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import markdown as md_lib

from .config import Config
from .utils import split_front_matter

MD_EXT = ["tables", "fenced_code", "sane_lists"]

# --- helpers ---
def _escape_attr(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")

def _extract_first_image(md_text: str) -> str | None:
    # match ![alt](url) or ![alt](url "title")
    m = re.search(r'!\[[^\]]*\]\(([^)\s]+)', md_text)
    if m:
        return m.group(1).strip()
    return None

def _og_locale(lang: str) -> str:
    mapping = {
        "ml": "ml_IN", "en": "en_US", "ar": "ar_SA", "hi": "hi_IN", "ur": "ur_PK",
        "bn": "bn_BD", "ta": "ta_IN", "id": "id_ID", "tr": "tr_TR", "fr": "fr_FR",
        "es": "es_ES", "ms": "ms_MY", "de": "de_DE", "pt": "pt_PT", "ru": "ru_RU",
        "fa": "fa_IR", "ps": "ps_AF", "sw": "sw_KE", "ha": "ha_NG", "tl": "tl_PH",
        "zh": "zh_CN", "ja": "ja_JP", "ko": "ko_KR", "vi": "vi_VN", "th": "th_TH",
        "it": "it_IT",
    }
    return mapping.get(lang, lang)

PAGE_TMPL = """<!doctype html>
<html lang="{lang}" dir="{dir}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="google-site-verification" content="Av_XpCmnivIEF9qGNM-zHFQ3oaJPO9R4wBAJz8egCJY" />
<title>{title} | {site_title}</title>
<meta name="description" content="{desc_attr}">
<meta name="author" content="{author_attr}">
<link rel="canonical" href="{canonical}">
<link rel="stylesheet" href="/style.css">
<link rel="alternate" type="application/rss+xml" title="RSS" href="/rss.xml">
{alternates}
<meta property="og:type" content="article">
<meta property="og:site_name" content="{site_title}">
<meta property="og:locale" content="{og_locale}">
<meta property="og:title" content="{og_title_attr}">
<meta property="og:description" content="{desc_attr}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{og_image}">
<meta property="article:published_time" content="{published_time}">
<meta property="article:author" content="{author_attr}">
<meta property="article:section" content="{category_name}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{og_title_attr}">
<meta name="twitter:description" content="{desc_attr}">
<meta name="twitter:image" content="{og_image}">
<script type="application/ld+json">{jsonld}</script>
</head>
<body>
<nav class="top" aria-label="Breadcrumb"><a href="/">Islamic Resources Hub</a> · <a href="/{lang}/">{lang_label}</a> · <a href="/{lang}/{category}/">{category_name}</a></nav>
<main>
<article>
<header><h1>{title}</h1>
<p class="byline">{byline}</p></header>
{body}
<footer class="source">Source: Nerpatham Weekly · {issue_line} ·
<a href="{pdf_url}" rel="noopener">original PDF</a> ·
<a href="{md_url}">markdown</a> · <a href="/llms.txt">AI index</a></footer>
</article>
</main>
</body>
</html>
"""

INDEX_TMPL = """<!doctype html>
<html lang="{lang}" dir="{dir}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="google-site-verification" content="Av_XpCmnivIEF9qGNM-zHFQ3oaJPO9R4wBAJz8egCJY" />
<title>{title}</title>
<meta name="description" content="{desc_attr}">
<link rel="canonical" href="{canonical}">
<link rel="stylesheet" href="/style.css">
<link rel="alternate" type="application/rss+xml" title="RSS" href="/rss.xml">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Islamic Resources Hub">
<meta property="og:locale" content="{og_locale}">
<meta property="og:title" content="{og_title_attr}">
<meta property="og:description" content="{desc_attr}">
<meta property="og:url" content="{canonical}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{og_title_attr}">
<meta name="twitter:description" content="{desc_attr}">
<script type="application/ld+json">{jsonld}</script>
</head>
<body>
<nav class="top" aria-label="Breadcrumb"><a href="/">Islamic Resources Hub</a>{crumb}</nav>
<main>
<h1>{heading}</h1>
<p class="index-desc">{index_desc}</p>
<ul class="cards">
{items}
</ul>
</main>
</body>
</html>
"""


class SiteGen:
    def __init__(self, cfg: Config):
        self.site = cfg.root / "site"

    # ------------------------------------------------------------- repo ----
    def ensure_repo(self, cfg: Config):
        if not (self.site / ".git").exists():
            self._git(cfg, "init", "-b", "main")
            (self.site / ".nojekyll").write_text("", encoding="utf-8")
            self._style()
            self._git(cfg, "config", "user.name", cfg["git"]["author_name"])
            self._git(cfg, "config", "user.email", cfg["git"]["author_email"])
            print("[site] repository initialised")
        remote = f"https://github.com/{cfg['site']['repo']}.git"
        token = cfg.github_token
        if token and not token.startswith("PASTE-"):
            remote = f"https://x-access-token:{token}@github.com/{cfg['site']['repo']}.git"
        # else: rely on gh credential helper (gh auth setup-git)
        r = self._git(cfg, "remote")
        if "origin" not in r.stdout.split():
            self._git(cfg, "remote", "add", "origin", remote)
        elif token and not token.startswith("PASTE-"):
            self._git(cfg, "remote", "set-url", "origin", remote)

    def _git(self, cfg: Config, *args) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=self.site, capture_output=True, text=True, check=False)

    def publish(self, cfg: Config, message: str) -> bool:
        """Regenerate derived files, commit everything, push. Returns push success."""
        try:
            self.regenerate_indexes(cfg)
        except Exception as e:
            print(f"[site] index regeneration warning: {e}")
        self._git(cfg, "add", "-A")
        commit = self._git(cfg, "commit", "-m", message)
        if commit.returncode != 0:
            print("[site] nothing new to commit")
        push = self._git(cfg, "push", "-u", "origin", "main")
        if push.returncode == 0:
            return True
        print(f"[site] PUSH FAILED (will retry next cycle): {push.stderr.strip()[:300]}")
        return False

    # ------------------------------------------------------------ render ----
    def render_article(self, cfg: Config, rel_md: str) -> str:
        path = self.site / rel_md
        fm, body_md = split_front_matter(path.read_text(encoding="utf-8"))
        body_html = md_lib.markdown(body_md, extensions=MD_EXT)
        slug = fm.get("slug") or path.stem
        base = cfg["site"]["base_url"].rstrip("/")
        site_title = cfg["site"]["title"]
        url_path = "/" + rel_md.replace(".md", ".html")
        canonical = base + url_path

        alternates = []
        for sibling in sorted(self.site.glob(f"*/*/{slug}.md")):
            code = sibling.parts[-3]
            if code != fm.get("lang"):
                alternates.append(
                    f'<link rel="alternate" hreflang="{code}" '
                    f'href="{base}/{code}/{fm.get("category")}/{slug}.html">'
                )

        source = fm.get("source") or {}
        issue_date = source.get("issue_date") or ""
        pdf_url = source.get("pdf_url") or "#"
        byline_bits = [fm.get("author") or "Unknown author", issue_date,
                       cfg.category_name(fm.get("category", ""))]
        # OG image: first image in markdown or fallback
        raw_img = _extract_first_image(body_md)
        if raw_img:
            if raw_img.startswith("http"):
                og_image = raw_img
            elif raw_img.startswith("/"):
                og_image = base + raw_img
            else:
                og_image = base + "/" + raw_img.lstrip("/")
        else:
            og_image = base + "/assets/og-default.jpg"

        # Escaped attrs
        title_str = str(fm.get("title", ""))
        summary_str = str(fm.get("summary") or "")[:200]
        desc_attr = _escape_attr(summary_str).replace("\n", " ")
        og_title_attr = _escape_attr(title_str)
        author_attr = _escape_attr(str(fm.get("author") or ""))
        category_name = cfg.category_name(fm.get("category", ""))
        og_locale = _og_locale(str(fm.get("lang", "ml")))
        published_time = ""
        if issue_date:
            try:
                # expect YYYY-MM-DD
                dt = datetime.fromisoformat(str(issue_date))
                published_time = dt.strftime("%Y-%m-%dT00:00:00Z")
            except Exception:
                published_time = str(issue_date)

        # Enhanced JSON-LD with Breadcrumb + Article + Publisher
        jsonld_obj = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": title_str,
            "description": summary_str,
            "author": {"@type": "Person", "name": str(fm.get("author") or "Unknown")},
            "publisher": {
                "@type": "Organization",
                "name": site_title,
                "logo": {"@type": "ImageObject", "url": base + "/assets/logo.png"}
            },
            "inLanguage": str(fm.get("lang", "ml")),
            "datePublished": issue_date,
            "isPartOf": {"@type": "PublicationIssue", "name": "Nerpatham Weekly"},
            "keywords": ", ".join(fm.get("tags") or []),
            "url": canonical,
            "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
            "image": og_image,
            "articleSection": category_name,
            "breadcrumb": {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": site_title, "item": base + "/"},
                    {"@type": "ListItem", "position": 2, "name": cfg.lang_name(str(fm.get("lang", "ml"))), "item": f"{base}/{fm.get('lang')}/index.html"},
                    {"@type": "ListItem", "position": 3, "name": category_name, "item": f"{base}/{fm.get('lang')}/{fm.get('category')}/index.html"},
                    {"@type": "ListItem", "position": 4, "name": title_str, "item": canonical},
                ]
            }
        }
        jsonld = json.dumps(jsonld_obj, ensure_ascii=False).replace("</", "<\\/")

        html = PAGE_TMPL.format(
            lang=str(fm.get("lang", "ml")),
            dir="rtl" if Config.is_rtl(str(fm.get("lang", "ml"))) else "ltr",
            lang_label=cfg.lang_name(str(fm.get("lang", "ml"))),
            title=title_str,
            site_title=site_title,
            desc_attr=desc_attr,
            author_attr=author_attr,
            canonical=canonical,
            og_locale=og_locale,
            og_title_attr=og_title_attr,
            og_image=og_image,
            published_time=published_time,
            category=fm.get("category", ""),
            category_name=category_name,
            alternates="\n".join(alternates),
            jsonld=jsonld,
            byline=" · ".join(str(b) for b in byline_bits if b),
            body=body_html,
            issue_line=issue_date,
            pdf_url=pdf_url,
            md_url=url_path.replace(".html", ".md"),
        )
        out = path.with_suffix(".html")
        out.write_text(html, encoding="utf-8")
        return url_path

    # ----------------------------------------------------------- indexes ----
    def _scan_entries(self) -> list[dict]:
        entries = []
        for p in sorted(self.site.rglob("*.md")):
            rel = p.relative_to(self.site).as_posix()
            if rel.startswith("src/") or rel.startswith(".github/"):
                continue
            parts = rel.split("/")
            if len(parts) != 3:
                continue
            lang, category, fname = parts
            if lang in ("src", ".github"):
                continue
            fm, _ = split_front_matter(p.read_text(encoding="utf-8"))
            entries.append({
                "slug": fm.get("slug") or p.stem,
                "lang": lang,
                "category": category,
                "title": fm.get("title"),
                "summary": fm.get("summary"),
                "author": fm.get("author"),
                "issue_date": (fm.get("source") or {}).get("issue_date"),
                "html_url": f"/{lang}/{category}/{p.stem}.html",
                "md_url": f"/{rel}",
            })
        return entries

    def _write_page(self, rel_path: str, html: str):
        target = self.site / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")

    def regenerate_indexes(self, cfg: Config):
        entries = self._scan_entries()
        base = cfg["site"]["base_url"].rstrip("/")
        site_title = cfg["site"]["title"]
        site_desc = cfg["site"]["description"]

        # Enhanced index.json for AI
        (self.site / "index.json").write_text(
            json.dumps({
                "generated_for_ai": True,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "site": {"title": site_title, "description": site_desc, "base_url": base, "canonical_lang": cfg.canonical_lang},
                "languages": [{"code": cfg.canonical_lang, "name": cfg.lang_name(cfg.canonical_lang)}] + [{"code": l["code"], "name": l["name"]} for l in cfg.target_languages],
                "categories": [{"slug": c["slug"], "name": c["en"]} for c in cfg["categories"]],
                "count": len(entries),
                "articles": entries
            }, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        self._sitemap(cfg, entries)
        self._rss(cfg, entries)
        self._robots(cfg)
        self._llms(cfg, entries)

        # root portal: language -> category map
        langs: dict[str, set[str]] = {}
        for e in entries:
            langs.setdefault(e["lang"], set()).add(e["category"])
        lines = [
            '<li><strong>For AI systems:</strong> machine-readable catalog at <a href="/index.json">/index.json</a>; '
            'raw Markdown sits beside every HTML page (<code>.md</code> next to <code>.html</code>); RSS at <a href="/rss.xml">/rss.xml</a>; <a href="/llms.txt">llms.txt</a> for LLMs.</li>',
        ]
        for code in sorted(langs):
            cats = sorted(langs[code])
            cat_links = " · ".join(f'<a href="/{code}/{c}/index.html">{cfg.category_name(c)}</a>' for c in cats)
            lines.append(f'<li><a href="/{code}/index.html"><strong>{cfg.lang_name(code)}</strong></a> ({code}): {cat_links}</li>')

        # Root index - SEO enhanced
        root_desc = _escape_attr(site_desc)
        root_canonical = base + "/"
        root_jsonld = json.dumps({
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": site_title,
            "description": site_desc,
            "url": root_canonical,
            "isPartOf": {"@type": "Organization", "name": site_title, "url": base},
            "inLanguage": "en"
        }, ensure_ascii=False).replace("</", "<\\/")
        self._write_page("index.html", INDEX_TMPL.format(
            lang="en", dir="ltr", title=site_title,
            heading=site_title, crumb="", items="\n".join(lines),
            desc_attr=root_desc, canonical=root_canonical,
            og_locale="en_US", og_title_attr=_escape_attr(site_title),
            jsonld=root_jsonld, index_desc=site_desc))

        # per-language index
        for code in langs:
            lang_desc = f"{cfg.lang_name(code)} Islamic articles from {site_title} — {site_desc}"
            lang_canonical = f"{base}/{code}/index.html"
            lang_jsonld = json.dumps({
                "@context": "https://schema.org",
                "@type": "CollectionPage",
                "name": f"{site_title} — {cfg.lang_name(code)}",
                "description": lang_desc,
                "url": lang_canonical,
                "inLanguage": code,
                "isPartOf": {"@type": "WebSite", "name": site_title, "url": base}
            }, ensure_ascii=False).replace("</", "<\\/")
            items = "\n".join(self._card(e, cfg, with_cat=True) for e in entries if e["lang"] == code)
            self._write_page(f"{code}/index.html", INDEX_TMPL.format(
                lang=code, dir="rtl" if Config.is_rtl(code) else "ltr",
                title=f"{cfg.lang_name(code)} — {site_title}",
                heading=cfg.lang_name(code), crumb=f' · <a href="/">home</a>', items=items or "<li>Nothing yet.</li>",
                desc_attr=_escape_attr(lang_desc[:160]), canonical=lang_canonical,
                og_locale=_og_locale(code), og_title_attr=_escape_attr(f"{cfg.lang_name(code)} — {site_title}"),
                jsonld=lang_jsonld, index_desc=lang_desc))
            # per category index
            for cat in sorted(langs[code]):
                sub = [e for e in entries if e["lang"] == code and e["category"] == cat]
                cat_name = cfg.category_name(cat)
                cat_desc = f"{cat_name} articles in {cfg.lang_name(code)} — {site_title}"
                cat_canonical = f"{base}/{code}/{cat}/index.html"
                cat_jsonld = json.dumps({
                    "@context": "https://schema.org",
                    "@type": "CollectionPage",
                    "name": f"{cat_name} — {cfg.lang_name(code)}",
                    "description": cat_desc,
                    "url": cat_canonical,
                    "inLanguage": code,
                    "isPartOf": {"@type": "WebSite", "name": site_title, "url": base},
                    "breadcrumb": {
                        "@type": "BreadcrumbList",
                        "itemListElement": [
                            {"@type": "ListItem", "position": 1, "name": site_title, "item": base + "/"},
                            {"@type": "ListItem", "position": 2, "name": cfg.lang_name(code), "item": f"{base}/{code}/index.html"},
                            {"@type": "ListItem", "position": 3, "name": cat_name, "item": cat_canonical},
                        ]
                    }
                }, ensure_ascii=False).replace("</", "<\\/")
                items = "\n".join(self._card(e, cfg) for e in sub)
                self._write_page(f"{code}/{cat}/index.html", INDEX_TMPL.format(
                    lang=code, dir="rtl" if Config.is_rtl(code) else "ltr",
                    title=f"{cat_name} — {cfg.lang_name(code)} | {site_title}",
                    heading=cat_name,
                    crumb=f' · <a href="/{code}/index.html">{cfg.lang_name(code)}</a>',
                    items=items or "<li>Nothing yet.</li>",
                    desc_attr=_escape_attr(cat_desc), canonical=cat_canonical,
                    og_locale=_og_locale(code), og_title_attr=_escape_attr(f"{cat_name} — {cfg.lang_name(code)} | {site_title}"),
                    jsonld=cat_jsonld, index_desc=cat_desc))

    @staticmethod
    def _card(e: dict, cfg: Config, with_cat: bool = False) -> str:
        bits = [e["lang"]]
        if with_cat:
            bits.append(cfg.category_name(e["category"]))
        if e["issue_date"]:
            bits.append(e["issue_date"])
        return (f'<li><a href="{e["html_url"]}">{e["title"]}</a>'
                f'<small> {" · ".join(bits)}</small></li>')

    def _sitemap(self, cfg: Config, entries):
        base = cfg["site"]["base_url"].rstrip("/")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        urls = []
        # root + indexes
        urls.append((f"{base}/", now, "1.0"))
        urls.append((f"{base}/index.json", now, "0.8"))
        urls.append((f"{base}/rss.xml", now, "0.8"))
        urls.append((f"{base}/llms.txt", now, "0.7"))
        # language and category indexes
        langs = set(e["lang"] for e in entries)
        for code in langs:
            urls.append((f"{base}/{code}/index.html", now, "0.9"))
            cats = set(e["category"] for e in entries if e["lang"] == code)
            for cat in cats:
                urls.append((f"{base}/{code}/{cat}/index.html", now, "0.8"))
        # articles
        for e in entries:
            lastmod = e.get("issue_date") or now
            # ensure YYYY-MM-DD
            try:
                datetime.fromisoformat(str(lastmod))
            except Exception:
                lastmod = now
            urls.append((base + e["html_url"], str(lastmod), "0.9"))
            # also sitemap for markdown? optional include but prioritize html
        xml = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for loc, lastmod, priority in dict.fromkeys(urls):
            xml.append(f"  <url><loc>{loc}</loc><lastmod>{lastmod}</lastmod><priority>{priority}</priority></url>")
        xml.append("</urlset>")
        (self.site / "sitemap.xml").write_text("\n".join(xml), encoding="utf-8")

    def _robots(self, cfg: Config):
        base = cfg["site"]["base_url"].rstrip("/")
        txt = f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n"
        (self.site / "robots.txt").write_text(txt, encoding="utf-8")

    def _llms(self, cfg: Config, entries):
        base = cfg["site"]["base_url"].rstrip("/")
        site_title = cfg["site"]["title"]
        site_desc = cfg["site"]["description"]
        lines = [
            f"# {site_title}",
            f"> {site_desc}",
            "",
            f"Base URL: {base}",
            f"Canonical language: {cfg.canonical_lang} (Malayalam)",
            "",
            "## For AI systems",
            "- Machine-readable catalog: /index.json (all articles with html_url + md_url)",
            "- Every article has Markdown source beside HTML: e.g. /ml/dawah/foo.html → /ml/dawah/foo.md",
            "- RSS: /rss.xml  |  Sitemap: /sitemap.xml",
            "- Use `Accept: text/markdown` conceptually via .md URLs for clean LLM ingestion.",
            "",
            "## Categories",
        ]
        for c in cfg["categories"]:
            lines.append(f"- {c['en']} ({c['slug']}): {base}/ml/{c['slug']}/index.html")
        lines.append("")
        lines.append("## Languages")
        lines.append(f"- {cfg.lang_name(cfg.canonical_lang)} ({cfg.canonical_lang}): {base}/{cfg.canonical_lang}/index.html (canonical)")
        for l in cfg.target_languages:
            lines.append(f"- {l['name']} ({l['code']}): {base}/{l['code']}/index.html")
        lines.append("")
        lines.append("## Recent Articles (sample 30)")
        for e in entries[:30]:
            lines.append(f"- [{e['title']}]({base}{e['html_url']}): {e['summary'] or ''} — Markdown: {base}{e['md_url']}")
        lines.append("")
        lines.append("## Usage")
        lines.append("- Prefer .md URLs for training / RAG - they are cleaner than HTML.")
        lines.append("- Respect `html_url` as canonical link when citing.")
        lines.append(f"- Publisher: {site_title} · Source: Nerpatham Weekly")
        (self.site / "llms.txt").write_text("\n".join(lines), encoding="utf-8")
        # also copy to root as llms-full? keep simple

    def _rss(self, cfg: Config, entries):
        base = cfg["site"]["base_url"].rstrip("/")
        canon = [e for e in entries if e["lang"] == cfg.canonical_lang][:100]
        items = "\n".join(
            f"<item><title>{_escape_attr(str(e['title']))}</title>"
            f"<link>{base}{e['html_url']}</link>"
            f"<guid isPermaLink=\"false\">{e['slug']}</guid>"
            f"<description><![CDATA[{(e['summary'] or '')[:300]}]]></description>"
            f"<pubDate>{e.get('issue_date') or ''}</pubDate></item>"
            for e in canon
        )
        rss = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>\n'
            f"<title>{_escape_attr(cfg['site']['title'])}</title>\n<link>{base}</link>\n"
            f"<atom:link href=\"{base}/rss.xml\" rel=\"self\" type=\"application/rss+xml\" />\n"
            f"<description>{_escape_attr(cfg['site']['description'])}</description>\n"
            f"<language>{cfg.canonical_lang}</language>\n"
            + items + "\n</channel></rss>"
        )
        (self.site / "rss.xml").write_text(rss, encoding="utf-8")

    def _style(self):
        css = """:root{--ink:#1c2430;--bg:#fdfcf9;--accent:#0f6e5d;--muted:#6b7280}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:19px/1.75 Georgia,'Times New Roman',serif}
.top{padding:.7rem 1rem;border-bottom:1px solid #e5e1d8;font-family:system-ui,sans-serif;font-size:.85rem}
.top a{color:var(--accent);text-decoration:none;margin-right:.4rem}
main{max-width:46rem;margin:0 auto;padding:2rem 1.25rem 4rem}
h1{line-height:1.25;font-size:2rem;margin:.2em 0}
.byline{color:var(--muted);font-style:italic;margin-top:0}
blockquote{border-left:4px solid var(--accent);margin:1.2em 0;padding:.2em 1em;background:#f6f4ee}
.source{margin-top:3rem;padding-top:1rem;border-top:1px solid #e5e1d8;font-size:.85rem;color:var(--muted);font-family:system-ui,sans-serif}
.cards{list-style:none;padding:0}
.cards li{margin:1.1rem 0}
.cards a{font-size:1.15rem;color:var(--ink);text-decoration:none;font-weight:bold}
.cards a:hover{color:var(--accent)}
.cards small{display:block;color:var(--muted);font-family:system-ui,sans-serif}
img{max-width:100%;height:auto}
[dir=rtl]{text-align:right;direction:rtl}
[dir=rtl] .top a{margin-right:0;margin-left:.4rem}
[dir=rtl] blockquote{border-left:none;border-right:4px solid var(--accent)}
[dir=rtl] body{font-family:'Traditional Arabic','Scheherazade New','Noto Naskh Arabic',Georgia,'Times New Roman',serif}
.index-desc{color:var(--muted);font-family:system-ui,sans-serif;font-size:1rem;margin-top:0}
"""
        (self.site / "style.css").write_text(css, encoding="utf-8")
