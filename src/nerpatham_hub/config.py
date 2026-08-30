"""Configuration loading (config.yaml + .env)."""
from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]

RTL_LANGS = {"ar", "ur", "fa", "ps", "ha"}


class Config:
    def __init__(self, data: dict):
        self._d = data

    def __getitem__(self, key):
        return self._d[key]

    def get(self, key, default=None):
        return self._d.get(key, default)

    @property
    def root(self) -> Path:
        return ROOT

    @property
    def openrouter_key(self) -> str:
        return os.environ.get("OPENROUTER_API_KEY", "").strip()

    @property
    def github_token(self) -> str:
        return os.environ.get("GITHUB_TOKEN", "").strip()

    @property
    def google_key(self) -> str:
        return os.environ.get("GOOGLE_API_KEY", "").strip()

    @property
    def model(self) -> str:
        return os.environ.get("LLM_MODEL", "").strip() or self["llm"]["model"]

    @property
    def canonical_lang(self) -> str:
        return self["languages"]["canonical"]

    @property
    def target_languages(self) -> list[dict]:
        return self["languages"]["targets"]

    @property
    def category_slugs(self) -> list[str]:
        return [c["slug"] for c in self["categories"]]

    def category_name(self, slug: str) -> str:
        for c in self["categories"]:
            if c["slug"] == slug:
                return c["en"]
        return slug.replace("-", " ").title()

    def lang_name(self, code: str) -> str:
        if code == self.canonical_lang:
            return "Malayalam"
        for l in self.target_languages:
            if l["code"] == code:
                return l["name"]
        return code

    @staticmethod
    def is_rtl(code: str) -> bool:
        return code in RTL_LANGS


@lru_cache(maxsize=1)
def load() -> Config:
    load_dotenv(ROOT / ".env")
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return Config(yaml.safe_load(f))
