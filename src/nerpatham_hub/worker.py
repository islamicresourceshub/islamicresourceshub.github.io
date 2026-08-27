"""Worker main loop - one unit of work per cycle, crash-safe via SQLite state."""
from __future__ import annotations

import time
import traceback

from .config import load
from .db import Store
from .crawler import Crawler
from .llm import LLMClient, LLMAuthError
from .sitegen import SiteGen
from . import extract, translate

CRAWL_INTERVAL_SECONDS = 6 * 3600  # re-check website for new issues every 6h


def do_one_cycle(store: Store, crawler: Crawler, llm: LLMClient | None, sg: SiteGen) -> str:
    """Execute the single highest-priority work item. Returns action name."""
    # 0. force a download every 10 non-download cycles so the backlog keeps flowing
    csd = int(store.kv_get("cycles_since_download", "0"))
    force_download = csd >= 10
    n = int(store.kv_get("cycle_n", "0")) + 1
    store.kv_set("cycle_n", str(n))
    translate_first = (n % 3 == 0)  # keep translations flowing while backlog finalizes

    # 1. inbox files first (user dropped them deliberately)
    if crawler.scan_inbox(store):
        return "inbox"

    # 2. translations periodically - so they never starve behind the issue backlog
    if translate_first and llm and translate.translate_next(store, load(), llm, sg):
        store.kv_set("cycles_since_download", str(csd + 1))
        return "translate"

    # 3. download next discovered issue
    issue = store.next_download()
    if issue and (force_download or not store.next_finalize_issue()
                  and not store.next_ocr_issue() and not store.next_translation()):
        crawler.download_issue(store, issue)
        store.kv_set("cycles_since_download", "0")
        return "download"

    # 4. prepare page rows for downloaded issues
    for iss in store.q("SELECT * FROM issues WHERE status='downloaded' ORDER BY issue_date, id"):
        extract.prepare_issue(store, load(), iss)
        return "prepare"

    # 5. finalize a fully-extracted issue (text-only LLM calls - cheap, go first)
    if llm and extract.finalize_issue(store, load(), llm, sg, crawler):
        store.kv_set("cycles_since_download", str(csd + 1))
        return "finalize"

    # 6. OCR / chunk processing - exactly ONE page per cycle
    if llm and extract.process_next_page(store, load(), llm):
        store.kv_set("cycles_since_download", str(csd + 1))
        return "ocr"

    # 7. translations - exactly ONE per cycle
    if llm and translate.translate_next(store, load(), llm, sg):
        store.kv_set("cycles_since_download", str(csd + 1))
        return "translate"

    return ""


def main(once: bool = False, verbose: bool = False):
    from .logsetup import setup
    log = setup(verbose)
    cfg = load()
    store = Store()
    crawler = Crawler(cfg)
    sg = SiteGen(cfg)

    last_crawl = float(store.kv_get("last_crawl", "0"))
    log.info("worker started (model=%s)", cfg.model)

    while True:
        try:
            # periodic archive re-crawl (no LLM needed)
            if time.time() - last_crawl > CRAWL_INTERVAL_SECONDS:
                try:
                    crawler.discover(store)
                    store.kv_set("last_crawl", str(time.time()))
                    last_crawl = time.time()
                except Exception as e:
                    log.warning("crawl failed: %s", e)
                    store.kv_set("last_crawl", str(time.time()))  # retry in 6h

            need_llm = bool(
                store.next_ocr_issue()
                or store.next_finalize_issue()
                or store.next_translation()
                or store.next_download()
            )
            llm = LLMClient(cfg) if need_llm else None

            action = do_one_cycle(store, crawler, llm, sg)

            if not action:
                if once:
                    log.info("queue empty; --once exit")
                    break
                time.sleep(cfg["pipeline"]["poll_interval_seconds"])
            elif once:
                log.info("cycle complete: %s (--once exit)", action)
                break
        except LLMAuthError as e:
            log.critical("AUTH: %s - fix .env and restart.", e)
            if once:
                break
            time.sleep(300)
        except RuntimeError as e:  # config errors like missing token
            log.critical("%s", e)
            break
        except KeyboardInterrupt:
            raise
        except Exception as e:
            log.error("cycle error (%s): %s\n%s", type(e).__name__, e, traceback.format_exc())
            time.sleep(60)


if __name__ == "__main__":
    main()
