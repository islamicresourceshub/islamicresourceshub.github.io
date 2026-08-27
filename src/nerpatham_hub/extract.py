"""Extraction stage: page preparation (raster or TXT chunks), OCR, segmentation, classification."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .config import Config
from .db import Store, now
from .llm import LLMClient, LLMPermanentError
from .utils import split_front_matter, build_front_matter, strip_page_markers, slugify


def work_dir(cfg: Config, issue_id: int) -> Path:
    d = cfg.root / "work" / f"issue-{issue_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- prepare ----
def prepare_issue(store: Store, cfg: Config, issue) -> str:
    """Create pending page rows. Returns 'txt' or 'raster' mode."""
    wdir = work_dir(cfg, issue["id"])
    existing = store.q("SELECT COUNT(*) c FROM pages WHERE issue_id=?", (issue["id"],))[0]["c"]
    if existing:
        # stale rows from a previous reset/run - wipe and prepare fresh
        store.x("DELETE FROM pages WHERE issue_id=?", (issue["id"],))
        print(f"[extract] issue #{issue['id']}: cleared {existing} stale page rows")
    has_txt = issue["txt_path"] and Path(issue["txt_path"]).exists()
    has_pdf = issue["pdf_path"] and Path(issue["pdf_path"]).exists()
    if has_txt:
        # TXT-mode: full texts harvested later directly from per-article pages.
        store.x("UPDATE issues SET status='extracting', pages=0, error=NULL WHERE id=?", (issue["id"],))
        print(f"[extract] issue #{issue['id']} TXT-mode: will harvest linked article pages")
        return "txt"
    if not has_pdf:
        # no source file left (e.g. deleted after earlier publish) -> re-queue for re-download
        store.x("UPDATE issues SET status='discovered', pdf_path=NULL, txt_path=NULL, error='pdf missing, re-queued' WHERE id=?", (issue["id"],))
        print(f"[extract] issue #{issue['id']}: source missing, re-queued for download")
        return "requeued"

    import pymupdf
    doc = pymupdf.open(issue["pdf_path"])
    n = doc.page_count
    doc.close()
    for i in range(1, n + 1):
        store.x("INSERT INTO pages(issue_id, page_no, status) VALUES(?,?,'pending')", (issue["id"], i))
    store.x("UPDATE issues SET status='extracting', pages=?, error=NULL WHERE id=?", (n, issue["id"]))
    print(f"[extract] issue #{issue['id']} raster-mode: {n} pages queued for OCR")
    return "raster"


# ------------------------------------------------------------------- ocr ----
def process_next_page(store: Store, cfg: Config, llm: LLMClient) -> bool:
    """OCR exactly one pending page. Returns True if work was done."""
    issue = store.next_ocr_issue()
    if not issue:
        return False
    row = store.pending_page(issue["id"])
    if not row:
        return False
    prompt_file = cfg.root / "src" / "prompts" / "extract_ml.md"
    prompt = prompt_file.read_text(encoding="utf-8")

    try:
        import pymupdf
        doc = pymupdf.open(issue["pdf_path"])
        page = doc[row["page_no"] - 1]
        pix = page.get_pixmap(dpi=cfg["pipeline"]["raster_dpi"])
        fmt = "jpeg" if cfg["pipeline"]["image_format"] == "jpeg" else "png"
        img_bytes = pix.tobytes(fmt)
        doc.close()
        md = llm.vision(prompt, img_bytes, f"image/{'jpeg' if fmt == 'jpeg' else 'png'}",
                        temperature=cfg["llm"]["temperature_extraction"])
        if md.strip().lower() == "(empty)":
            md = ""
        out = work_dir(cfg, issue["id"]) / f"page-{row['page_no']:03d}.md"
        out.write_text(md.strip(), encoding="utf-8")
        store.x("UPDATE pages SET status='done', md_path=? WHERE issue_id=? AND page_no=?",
                (str(out), issue["id"], row["page_no"]))
        print(f"[ocr] issue #{issue['id']} page {row['page_no']}/{issue['pages']} done ({len(md)} chars)")
    except LLMPermanentError as e:
        store.x("UPDATE pages SET status='failed', error=? WHERE issue_id=? AND page_no=?",
                (str(e)[:400], issue["id"], row["page_no"]))
        print(f"[ocr] page permanently failed: {e}")
    except Exception as e:
        attempts = row["attempts"] + 1
        status = "failed" if attempts >= cfg["pipeline"]["max_attempts"] else "pending"
        store.x("UPDATE pages SET status=?, attempts=?, error=? WHERE issue_id=? AND page_no=?",
                (status, attempts, str(e)[:400], issue["id"], row["page_no"]))
        print(f"[ocr] page attempt {attempts} failed: {e}")
    return True


# -------------------------------------------------------------- finalize ----
def finalize_issue(store: Store, cfg: Config, llm: LLMClient, sitegen, crawler=None) -> bool:
    """Segment pages into articles, classify, write canonical markdowns, publish."""
    issue = store.next_finalize_issue()
    if not issue:
        return False

    # crash-resume: staged articles already written -> just publish them
    staged = store.q("SELECT * FROM articles WHERE issue_id=? AND status='staged'", (issue["id"],))
    if staged:
        written = []
        for r in staged:
            if r["md_rel_path"] and (cfg.root / "site" / r["md_rel_path"]).exists():
                written.append((r["id"], r["md_rel_path"]))
            else:
                store.x("DELETE FROM articles WHERE id=?", (r["id"],))
        langs = [l["code"] for l in cfg.target_languages]
        for aid, _ in written:
            for code in langs:
                store.x("INSERT OR IGNORE INTO translations(article_id, lang) VALUES(?,?)", (aid, code))
        ok = sitegen.publish(cfg, f"resume: publish {len(written)} staged articles, issue #{issue['id']}")
        for aid, _ in written:
            store.x("UPDATE articles SET status='published' WHERE id=?", (aid,))
        _mark_published(store, cfg, issue)
        print(f"[finalize] issue #{issue['id']} resumed: published {len(written)} staged article(s) (push={'ok' if ok else 'pending'})")
        return True

    # TXT-mode issues: harvest full texts straight from per-article site pages
    if issue["txt_path"] and Path(issue["txt_path"]).exists() and crawler is not None:
        return _finalize_from_site(store, cfg, llm, sitegen, crawler, issue)

    frags = []
    for r in store.q("SELECT * FROM pages WHERE issue_id=? ORDER BY page_no", (issue["id"],)):
        if r["md_path"] and Path(r["md_path"]).exists():
            content = Path(r["md_path"]).read_text(encoding="utf-8").strip()
            if content:
                frags.append((r["page_no"], content))
    if not frags:
        print(f"[finalize] issue #{issue['id']}: no usable content, marking published-empty")
        _mark_published(store, cfg, issue)
        return True

    digest = "\n\n".join(f"[[p{no}]]\n{c[:1400]}" for no, c in frags)
    seg_prompt = (cfg.root / "src" / "prompts" / "segment.md").read_text(encoding="utf-8")
    seg_prompt = seg_prompt.replace("{categories}", ", ".join(cfg.category_slugs))
    segments = llm.json_chat(seg_prompt, digest, temperature=0.1)
    if not isinstance(segments, list):
        segments = [segments]

    written = []

    for seg in segments:
        kind = str(seg.get("kind", "other")).strip().lower()
        if kind not in ("article", "story", "poem", "kids"):
            continue  # news/review/ad/other dropped per policy
        start = max(1, int(seg.get("start_page", frags[0][0])))
        end = min(frags[-1][0], int(seg.get("end_page", frags[-1][0])))
        body = "\n\n".join(c for no, c in frags if start <= no <= end)
        body = strip_page_markers(body)
        title_ml = (seg.get("title_ml") or "Untitled").strip()
        author = (seg.get("author") or "").strip() or None
        if len(body) < 200:
            continue

        meta = seg if isinstance(seg, dict) else {}
        date_part = (issue["issue_date"] or "").replace("-", "") or now()[:10].replace("-", "")
        slug = f"{slugify(meta.get('title_en') or title_ml)}-{date_part}-{seg.get('seq', 1)}"
        category = meta.get("category") if meta.get("category") in cfg.category_slugs else "opinion"
        tags = meta.get("tags") or []
        rel = f"ml/{category}/{slug}.md"
        fm = {
            "title": title_ml,
            "author": author,
            "lang": cfg.canonical_lang,
            "category": category,
            "kind": kind,
            "tags": tags,
            "summary": meta.get("summary_ml"),
            "source": {
                "magazine": cfg["source"]["magazine_en"],
                "issue_date": issue["issue_date"],
                "pdf_url": issue["pdf_url"],
            },
            "date_processed": now(),
            "slug": slug,
        }
        abs_path = cfg.root / "site" / rel
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(build_front_matter(fm) + "\n\n" + body + "\n", encoding="utf-8")
        sitegen.render_article(cfg, rel)
        cur = store.x(
            "INSERT INTO articles(issue_id, seq, slug, title_ml, author, category, kind, page_start, page_end,"
            " status, md_rel_path, created_at) VALUES(?,?,?,?,?,?,?,?,?, 'staged', ?, ?)",
            (issue["id"], seg.get("seq", 0), slug, title_ml, author, category, kind, start, end, rel, now()),
        )
        written.append((cur.lastrowid, rel))

    # queue translations for every staged article
    langs = [l["code"] for l in cfg.target_languages]
    for aid, _ in written:
        for code in langs:
            store.x("INSERT OR IGNORE INTO translations(article_id, lang) VALUES(?,?)", (aid, code))

    # publish all staged articles of this issue in one commit
    if written:
        ok = sitegen.publish(cfg, f"articles: {Path(written[0][1]).stem} (+{max(0, len(written)-1)} more) from {Path(issue['pdf_path'] or issue['pdf_url']).stem}")
        if not ok:
            print("[finalize] git push failed; files committed locally, will push with next success")
    else:
        print(f"[finalize] issue #{issue['id']}: 0 articles kept after filtering")

    for aid, rel in written:
        store.x("UPDATE articles SET status='published' WHERE id=?", (aid,))
    _mark_published(store, cfg, issue)
    print(f"[finalize] issue #{issue['id']} complete: {len(written)} article(s)")
    return True


def _finalize_from_site(store: Store, cfg: Config, llm: LLMClient, sg, crawler, issue) -> bool:
    """Full texts harvested from per-article pages; one small metadata LLM call."""
    arts = crawler.fetch_issue_articles(issue)
    if not arts:
        store.x("UPDATE issues SET txt_path=NULL, status='downloaded' WHERE id=?", (issue["id"],))
        print(f"[finalize] issue #{issue['id']}: site harvest empty -> falling back to OCR path")
        return True

    items_txt = "\n".join(
        f"{i}. TITLE: {a['title']} || OPENING: {a['body'][:200].strip()}"
        for i, a in enumerate(arts, 1)
    )
    tpl = (cfg.root / "src" / "prompts" / "meta_batch.md").read_text(encoding="utf-8")
    prompt = tpl.replace("{categories}", ", ".join(cfg.category_slugs))
    try:
        metas = llm.json_chat(prompt, items_txt, temperature=0.1)
    except ValueError as e:
        print(f"[finalize] issue #{issue['id']}: metadata parse failed ({e}); retry next cycle")
        return True
    if not isinstance(metas, list):
        metas = [metas]
    by_seq = {int(m.get("seq", 0)): m for m in metas if isinstance(m, dict)}

    date_part = (issue["issue_date"] or "").replace("-", "") or now()[:10].replace("-", "")
    written = []
    dropped = 0
    import shutil as _shutil
    for i, a in enumerate(arts, 1):
        meta = by_seq.get(i, {})
        kind = str(meta.get("kind", "article")).strip().lower()
        if meta.get("keep") is False or kind == "drop":
            dropped += 1
            continue
        title_ml = (a["title"] or f"Article {i}").strip()
        slug = f"{slugify(str(meta.get('title_en')) or title_ml)}-{date_part}-{i}"
        category = meta.get("category") if meta.get("category") in cfg.category_slugs else "opinion"
        rel = f"ml/{category}/{slug}.md"

        # ---- localise images ----
        body = a["body"]
        slug_dir = f"assets/{slug}"
        dest_dir = cfg.root / "site" / slug_dir
        for im in a.get("images", []):
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                _shutil.copy2(im["path"], dest_dir / im["file"])
                body = body.replace(im["url"], f"/{slug_dir}/{im['file']}")
            except OSError as e:
                print(f"[img] copy failed {im['file']}: {e}")

        # ---- LLM structure pass (headings/quotes/lists), validated ----
        if len(body) > 800:
            body = _structure(llm, body, slug)

        fm = {
            "title": title_ml,
            "author": a.get("author") or None,
            "lang": cfg.canonical_lang,
            "category": category,
            "kind": "article",
            "tags": meta.get("tags") or [],
            "summary": meta.get("summary_ml"),
            "source": {
                "magazine": cfg["source"]["magazine_en"],
                "issue_date": issue["issue_date"],
                "pdf_url": issue["pdf_url"],
            },
            "date_processed": now(),
            "slug": slug,
        }
        abs_path = cfg.root / "site" / rel
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(build_front_matter(fm) + "\n\n" + body + "\n", encoding="utf-8")
        sg.render_article(cfg, rel)
        cur = store.x(
            "INSERT INTO articles(issue_id, seq, slug, title_ml, author, category, kind,"
            " status, md_rel_path, created_at) VALUES(?,?,?,?,?,?,'article','staged',?,?)",
            (issue["id"], i, slug, title_ml, a.get("author") or None, category, rel, now()),
        )
        written.append((cur.lastrowid, rel))

    langs = [l["code"] for l in cfg.target_languages]
    for aid, _ in written:
        for code in langs:
            store.x("INSERT OR IGNORE INTO translations(article_id, lang) VALUES(?,?)", (aid, code))

    ok = sg.publish(cfg, f"articles: {len(written)} from {Path(issue['txt_path']).stem} (site text)")
    for aid, rel in written:
        store.x("UPDATE articles SET status='published' WHERE id=?", (aid,))
    _mark_published(store, cfg, issue)
    print(f"[finalize] issue #{issue['id']} complete via site text: kept={len(written)} dropped={dropped} (push={'ok' if ok else 'pending'})")
    return True


def _structure(llm: LLMClient, body: str, slug: str) -> str:
    """LLM formatting pass with strict validation; falls back to input."""
    import re as _re
    tpl = (cfg_root_prompts() / "structure.md").read_text(encoding="utf-8")
    try:
        out = llm.chat(
            [{"role": "user", "content": tpl + "\n\n---\n\n" + body}],
            temperature=0.1,
        ).strip()
        if len(out) < 200:  # empty/refused - one retry
            out = llm.chat(
                [{"role": "user", "content": tpl + "\n\n---\n\n" + body}],
                temperature=0.3,
            ).strip()
    except Exception as e:
        print(f"[structure] {slug}: LLM failed ({e}); keeping flat body")
        return body
    out = _re.sub(r"^```(?:markdown)?\s*|\s*```$", "", out, flags=_re.MULTILINE).strip()
    imgs_in = len(_re.findall(r"!\[[^\]]*\]\([^)]+\)", body))
    imgs_out = len(_re.findall(r"!\[[^\]]*\]\([^)]+\)", out))
    if imgs_out != imgs_in or len(out) < len(body) * 0.5 or len(out) > len(body) * 2:
        print(f"[structure] {slug}: validation failed (imgs {imgs_in}->{imgs_out}, len {len(body)}->{len(out)}); keeping flat body")
        return body
    print(f"[structure] {slug}: structured ({len(body)} -> {len(out)} chars)")
    return out


def cfg_root_prompts():
    from .config import ROOT
    return ROOT / "src" / "prompts"


def _mark_published(store: Store, cfg: Config, issue):
    store.x("UPDATE issues SET status='published', published_at=? WHERE id=?", (now(), issue["id"]))
    if cfg["pipeline"]["delete_pdf_after_processing"]:
        for p in (issue["pdf_path"], issue["txt_path"]):
            if p and p.startswith(str(cfg.root)):
                try:
                    Path(p).unlink()
                    print(f"[cleanup] deleted {Path(p).name}")
                except OSError as e:
                    print(f"[cleanup] could not delete {p}: {e}")
    shutil.rmtree(work_dir(cfg, issue["id"]), ignore_errors=True)
