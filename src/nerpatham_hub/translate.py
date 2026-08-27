"""Translation stage: one (article x language) per call."""
from __future__ import annotations

import json
from pathlib import Path

from .config import Config
from .db import Store
from .llm import LLMClient
from .utils import split_front_matter, build_front_matter


def translate_next(store: Store, cfg: Config, llm: LLMClient, sitegen) -> bool:
    row = store.next_translation()
    if not row:
        return False
    aid, lang = row["aid"], row["lang"]
    art = store.q("SELECT * FROM articles WHERE id=?", (aid,))[0]
    src_path = cfg.root / "site" / art["md_rel_path"]
    if not src_path.exists():
        store.x("UPDATE translations SET status='failed', error='canonical md missing' WHERE article_id=? AND lang=?", (aid, lang))
        return True

    fm, body = split_front_matter(src_path.read_text(encoding="utf-8"))
    tpl = (cfg.root / "src" / "prompts" / "translate.md").read_text(encoding="utf-8")
    prompt = (
        tpl.replace("{language_name}", cfg.lang_name(lang))
        .replace("{lang_code}", lang)
        .replace("{title}", str(fm.get("title", "")))
        .replace("{summary}", str(fm.get("summary") or ""))
        .replace("{body}", body)
    )
    try:
        data = llm.json_chat(prompt, "", temperature=cfg["llm"]["temperature_translation"])
        t_title = str(data.get("title") or fm.get("title")).strip()
        t_summary = str(data.get("summary") or fm.get("summary") or "").strip()
        t_body = str(data.get("body_markdown") or "").strip()
        if len(t_body) < min(300, int(len(body) * 0.3)):
            raise ValueError("translation implausibly short")
    except Exception as e:
        attempts = _bump(store, aid, lang, e)
        status = "failed" if attempts >= cfg["pipeline"]["max_attempts"] else "pending"
        store.x("UPDATE translations SET status=?, attempts=? WHERE article_id=? AND lang=?", (status, attempts, aid, lang))
        print(f"[translate] {art['slug']} -> {lang} attempt failed: {e}")
        return True

    new_fm = dict(fm)
    new_fm["title"] = t_title
    new_fm["summary"] = t_summary
    new_fm["lang"] = lang
    new_fm["translation_of"] = art["slug"]
    rel = art["md_rel_path"].replace("ml/", f"{lang}/", 1)
    abs_path = cfg.root / "site" / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(build_front_matter(new_fm) + "\n\n" + t_body + "\n", encoding="utf-8")
    sitegen.render_article(cfg, rel)

    ok = sitegen.publish(cfg, f"translate {art['slug']} -> {lang}")
    store.x("UPDATE translations SET status='done', md_rel_path=? WHERE article_id=? AND lang=?",
            (rel, aid, lang))
    print(f"[translate] {art['slug']} -> {lang} {'published' if ok else 'committed (push pending)'}")
    return True


def _bump(store: Store, aid: int, lang: str, err: Exception) -> int:
    cur = store.x(
        "UPDATE translations SET attempts=attempts+1, error=? WHERE article_id=? AND lang=?",
        (str(err)[:400], aid, lang),
    )
    return cur.lastrowid if cur.rowcount is None else store.q(
        "SELECT attempts FROM translations WHERE article_id=? AND lang=?", (aid, lang)
    )[0]["attempts"]
