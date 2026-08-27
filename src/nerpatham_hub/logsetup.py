"""Rotating file + console logging."""
from __future__ import annotations

import logging
import logging.handlers
import sys

from .config import ROOT


def setup(verbose: bool = False) -> logging.Logger:
    logs_dir = ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        logs_dir / "worker.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    console = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s")
    handler.setFormatter(fmt)
    console.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(handler)
    root.addHandler(console)
    return root
