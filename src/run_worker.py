"""Entry point: python run_worker.py [--once] [--verbose]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nerpatham_hub.worker import main  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="run a single work cycle then exit")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    try:
        main(once=args.once, verbose=args.verbose)
    except KeyboardInterrupt:
        print("\nstopped by user")
