"""CLI wrapper around ProductHuntScraper.

Pulls the latest ~50 posts from the Product Hunt Atom feed and inserts them
as companies. Safe to re-run — base.py dedup handles upserts, so re-running
when only 10 new posts have appeared just no-ops the other 40.

Usage:
    python scripts/run_producthunt.py
    python scripts/run_producthunt.py --no-save   # dry run, prints counts only
    python scripts/run_producthunt.py --ai-only   # drop non-AI-keyword posts
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.scrapers.easy.producthunt_scraper import ProductHuntScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ph_runner")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Product Hunt RSS scraper.")
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Fetch + parse but do not write to the database.",
    )
    parser.add_argument(
        "--ai-only",
        action="store_true",
        help="Drop entries with no AI-keyword match in title+description.",
    )
    args = parser.parse_args()

    scraper = ProductHuntScraper(ai_only=args.ai_only)
    result = scraper.run(save_to_db=not args.no_save)
    logger.info(
        "Done: status=%s found=%s new=%s updated=%s",
        result.status, result.records_found, result.records_new, result.records_updated,
    )


if __name__ == "__main__":
    main()
