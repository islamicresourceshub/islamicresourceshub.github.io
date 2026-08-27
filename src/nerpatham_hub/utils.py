"""Shared helpers: slugs, front matter, dates."""
from __future__ import annotations

import re
import unicodedata

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "seo": 9,  # site typos "Seo" occur in some filenames
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

TOKEN_RE = re.compile(r"(?P<year>20\d{2})(?P<mon>[A-Za-z]{3,9})(?P<day>\d{2})")
TEXT_URL_RE = re.compile(r"issue-\d+-(?P<year>20\d{2})-(?P<mon>[a-z]+)-(?P<day>\d{1,2})\.html", re.I)


def date_token(filename: str) -> tuple[str, int | None]:
    """Extract ISO date + year from 'Nerpatham-2025Dec27.pdf' style names."""
    m = TOKEN_RE.search(filename)
    if not m:
        return "", None
    mon = MONTHS.get(m.group("mon").lower())
    if not mon:
        return "", int(m.group("year"))
    return f"{m.group('year')}-{mon:02d}-{int(m.group('day')):02d}", int(m.group("year"))


def iso_from_text_url(url: str) -> tuple[str, int | None]:
    """ISO date from 'vol-no-01-issue-01-2017-january-14.html' style URLs."""
    m = TEXT_URL_RE.search(url)
    if not m:
        return "", None
    mon = MONTHS.get(m.group("mon").lower())
    if not mon:
        return "", int(m.group("year"))
    return f"{m.group('year')}-{mon:02d}-{int(m.group('day')):02d}", int(m.group("year"))


def slugify(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text[:max_len].rstrip("-") or "article"


def split_front_matter(md_text: str) -> tuple[dict, str]:
    """Return (front_matter_dict, body). Tolerates missing front matter."""
    if md_text.startswith("---"):
        parts = md_text.split("\n---", 2)
        if len(parts) >= 2:
            try:
                import yaml
                fm = yaml.safe_load(parts[0][3:].strip()) or {}
                body = parts[1] if len(parts) == 2 else parts[1]
                # body may carry trailing '\n---' remainder; rejoin defensively
                if len(parts) == 3:
                    body += "\n" + parts[2]
                return fm, body.strip()
            except Exception:
                pass
    return {}, md_text.strip()


def build_front_matter(fm: dict) -> str:
    import yaml
    return "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, width=1000).strip() + "\n---"


def strip_page_markers(text: str) -> str:
    return re.sub(r"\n?\[\[p\d+\]\]\n?", "\n\n", text).strip()
