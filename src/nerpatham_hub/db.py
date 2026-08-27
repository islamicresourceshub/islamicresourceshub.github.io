"""SQLite state store - the single source of truth for queue and progress."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT

SCHEMA = """
CREATE TABLE IF NOT EXISTS issues(
  id INTEGER PRIMARY KEY,
  pdf_url TEXT UNIQUE NOT NULL,
  txt_url TEXT,
  year INTEGER,
  issue_date TEXT,
  status TEXT DEFAULT 'discovered',  -- discovered|downloaded|extracting|published|failed
  pdf_path TEXT,
  txt_path TEXT,
  pages INTEGER DEFAULT 0,
  error TEXT,
  attempts INTEGER DEFAULT 0,
  discovered_at TEXT,
  downloaded_at TEXT,
  published_at TEXT
);
CREATE TABLE IF NOT EXISTS pages(
  issue_id INTEGER NOT NULL REFERENCES issues(id),
  page_no INTEGER NOT NULL,
  md_path TEXT,
  status TEXT DEFAULT 'pending',     -- pending|done|failed
  attempts INTEGER DEFAULT 0,
  PRIMARY KEY(issue_id, page_no)
);
CREATE TABLE IF NOT EXISTS articles(
  id INTEGER PRIMARY KEY,
  issue_id INTEGER NOT NULL REFERENCES issues(id),
  seq INTEGER NOT NULL,
  slug TEXT UNIQUE,
  title_ml TEXT,
  author TEXT,
  category TEXT,
  kind TEXT,                          -- article|story|poem|kids|tafsir (kept kinds)
  page_start INTEGER, page_end INTEGER,
  status TEXT DEFAULT 'segmented',    -- segmented|published|skipped
  md_rel_path TEXT,
  error TEXT,
  attempts INTEGER DEFAULT 0,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS translations(
  article_id INTEGER NOT NULL REFERENCES articles(id),
  lang TEXT NOT NULL,
  status TEXT DEFAULT 'pending',      -- pending|done|failed
  md_rel_path TEXT,
  error TEXT,
  attempts INTEGER DEFAULT 0,
  PRIMARY KEY(article_id, lang)
);
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    def __init__(self):
        self.db_path = ROOT / "state" / "state.db"
        self.db_path.parent.mkdir(exist_ok=True)
        self.con = sqlite3.connect(self.db_path, timeout=30)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA busy_timeout=30000")
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.executescript(SCHEMA)
        self.con.commit()

    def q(self, sql: str, params=()) -> list[sqlite3.Row]:
        return self.con.execute(sql, params).fetchall()

    def x(self, sql: str, params=()) -> sqlite3.Cursor:
        cur = self.con.execute(sql, params)
        self.con.commit()
        return cur

    def kv_get(self, key: str, default: str | None = None) -> str | None:
        rows = self.q("SELECT value FROM kv WHERE key=?", (key,))
        return rows[0]["value"] if rows else default

    def kv_set(self, key: str, value: str):
        self.x("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    # ---- issues ----
    def upsert_issue(self, pdf_url: str, year: int | None, issue_date: str | None, txt_url: str | None):
        existing = self.q("SELECT id FROM issues WHERE pdf_url=?", (pdf_url,))
        if existing:
            self.x("UPDATE issues SET txt_url=COALESCE(txt_url, ?) WHERE pdf_url=?", (txt_url, pdf_url))
            return existing[0]["id"]
        cur = self.x(
            "INSERT INTO issues(pdf_url, txt_url, year, issue_date, status, discovered_at) VALUES(?,?,?,?, 'discovered', ?)",
            (pdf_url, txt_url, year, issue_date, now()),
        )
        return cur.lastrowid

    def next_download(self) -> sqlite3.Row | None:
        rows = self.q("SELECT * FROM issues WHERE status='discovered' ORDER BY issue_date, id LIMIT 1")
        return rows[0] if rows else None

    # ---- pages ----
    def pending_page(self, issue_id: int) -> sqlite3.Row | None:
        rows = self.q("SELECT * FROM pages WHERE issue_id=? AND status='pending' ORDER BY page_no LIMIT 1", (issue_id,))
        return rows[0] if rows else None

    # ---- work pickers ----
    def next_ocr_issue(self) -> sqlite3.Row | None:
        """Issue that is downloaded (or extracting) and still has pending pages."""
        rows = self.q(
            "SELECT i.* FROM issues i WHERE i.status IN ('downloaded','extracting') AND EXISTS("
            " SELECT 1 FROM pages p WHERE p.issue_id=i.id AND p.status='pending') ORDER BY i.issue_date, i.id LIMIT 1"
        )
        return rows[0] if rows else None

    def next_finalize_issue(self) -> sqlite3.Row | None:
        """All pages processed and issue ready for finalize/publish (incl. crash resume)."""
        rows = self.q(
            "SELECT i.* FROM issues i WHERE i.status='extracting' AND NOT EXISTS("
            " SELECT 1 FROM pages p WHERE p.issue_id=i.id AND p.status='pending') "
            "AND (NOT EXISTS(SELECT 1 FROM articles a WHERE a.issue_id=i.id) "
            " OR EXISTS(SELECT 1 FROM articles a WHERE a.issue_id=i.id AND a.status='staged')) "
            "ORDER BY i.issue_date, i.id LIMIT 1"
        )
        return rows[0] if rows else None

    def next_translation(self) -> sqlite3.Row | None:
        rows = self.q(
            "SELECT t.article_id AS aid, t.lang AS lang, a.slug AS slug FROM translations t "
            "JOIN articles a ON a.id=t.article_id WHERE t.status='pending' ORDER BY a.id, t.lang LIMIT 1"
        )
        return rows[0] if rows else None
