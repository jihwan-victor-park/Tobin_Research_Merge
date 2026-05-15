"""CLI wrapper around TaaftScraper.

Pulls a snapshot of tools from the TAAFT homepage and inserts them as
companies. Safe to re-run — base.py dedup handles upserts.

Usage:
    python scripts/run_taaft.py
    python scripts/run_taaft.py --no-save        # dry run, prints counts only
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.scrapers.easy.taaft_scraper import TaaftScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("taaft_runner")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TAAFT (theresanaiforthat.com) scraper.")
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Fetch + parse but do not write to the database.",
    )
    args = parser.parse_args()

    scraper = TaaftScraper()
    result = scraper.run(save_to_db=not args.no_save)
    logger.info(
        "Done: status=%s found=%s new=%s updated=%s",
        result.status, result.records_found, result.records_new, result.records_updated,
    )


if __name__ == "__main__":
    main()
