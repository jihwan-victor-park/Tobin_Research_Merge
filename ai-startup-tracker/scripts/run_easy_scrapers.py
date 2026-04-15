#!/usr/bin/env python3
"""
Run all registered easy scrapers against the live database.

Usage:
    python scripts/run_easy_scrapers.py             # run all + save to DB
    python scripts/run_easy_scrapers.py --dry-run   # scrape only, no DB writes
    python scripts/run_easy_scrapers.py --source capitalfactory.com  # single scraper
"""
import argparse
import logging
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("easy_scrapers")


def main():
    parser = argparse.ArgumentParser(description="Run all registered easy scrapers")
    parser.add_argument("--dry-run", action="store_true", help="Scrape without writing to DB")
    parser.add_argument("--source", nargs="+", help="Run specific scraper(s) by domain (e.g. capitalfactory.com)")
    args = parser.parse_args()

    from backend.scrapers.registry import SCRAPER_REGISTRY

    domains = args.source if args.source else list(SCRAPER_REGISTRY.keys())
    save_to_db = not args.dry_run

    logger.info("=" * 60)
    logger.info(f"Running {len(domains)} easy scraper(s) | save_to_db={save_to_db}")
    logger.info("=" * 60)

    results = {}
    for domain in domains:
        entry = SCRAPER_REGISTRY.get(domain)
        if entry is None:
            logger.warning(f"No registered scraper for domain: {domain}")
            continue

        scraper = entry.cls()
        logger.info(f"[{domain}] Starting scraper: {scraper.name}")
        try:
            result = scraper.run(save_to_db=save_to_db)
            results[domain] = result
            status_str = f"status={result.status} found={result.records_found} new={result.records_new} updated={result.records_updated}"
            if result.error_message:
                status_str += f" error={result.error_message}"
            logger.info(f"[{domain}] Done — {status_str}")
        except Exception as e:
            logger.error(f"[{domain}] Unhandled exception: {e}", exc_info=True)
            results[domain] = None

    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    success = sum(1 for r in results.values() if r and r.status == "success")
    failed = sum(1 for r in results.values() if r is None or r.status == "error")
    logger.info(f"  Total: {len(results)} | Success: {success} | Failed: {failed}")
    for domain, r in results.items():
        if r:
            logger.info(f"  {domain:40s} {r.status:12s} found={r.records_found:4d} new={r.records_new:4d}")
        else:
            logger.info(f"  {domain:40s} EXCEPTION")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
