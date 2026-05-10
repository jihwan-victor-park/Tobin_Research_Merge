"""
First-scrape pass for the curated batch added by seed_curated_sites.py.

Targets only rows where scraper_name LIKE 'curated:%' so existing sites that
happen to be due aren't re-scraped. Each site is run with force=True.

Logs to logs/curated_first_scrape_YYYYMMDD_HHMM.log so you can monitor
progress with `tail -f`. Prints a final by-status tally.

Run:
    python scripts/scrape_curated_sites.py [--limit N]
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / f"curated_first_scrape_{datetime.now().strftime('%Y%m%d_%H%M')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("curated_scrape")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None,
                   help="Cap how many sites to scrape (default: all curated rows)")
    args = p.parse_args()

    from backend.db.connection import session_scope
    from backend.db.models import SiteHealth
    from backend.orchestrator.orchestrator import Orchestrator

    with session_scope() as s:
        rows = (
            s.query(SiteHealth.domain, SiteHealth.url)
            .filter(SiteHealth.scraper_name.like("curated:%"))
            .filter(SiteHealth.url.isnot(None))
            .all()
        )
        targets = [(d, u) for (d, u) in rows]

    if args.limit:
        targets = targets[: args.limit]

    logger.info(f"=== curated first-scrape: {len(targets)} sites, log={LOG_PATH.name} ===")

    orch = Orchestrator()
    by_status: dict[str, int] = {}
    total_records = 0
    total_new = 0

    for i, (domain, url) in enumerate(targets, 1):
        logger.info(f"[{i}/{len(targets)}] {domain} → {url}")
        try:
            result = orch.run(url, force=True)
        except Exception as e:
            logger.exception(f"  CRASH: {e}")
            by_status["crash"] = by_status.get("crash", 0) + 1
            continue
        by_status[result.status] = by_status.get(result.status, 0) + 1
        if result.success:
            total_records += result.records_found or 0
            total_new += result.records_new or 0
            logger.info(f"  OK: {result.records_found} found, {result.records_new} new")
        else:
            logger.warning(f"  {result.status}: {(result.error_message or '')[:160]}")

    logger.info("=== done ===")
    for k, v in sorted(by_status.items(), key=lambda x: -x[1]):
        logger.info(f"  {k:18s} {v:4d}")
    logger.info(f"records_found total = {total_records}")
    logger.info(f"records_new total   = {total_new}")


if __name__ == "__main__":
    main()
