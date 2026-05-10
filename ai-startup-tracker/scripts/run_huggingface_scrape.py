#!/usr/bin/env python3
"""
Run the HuggingFace organizations scraper.

Why this exists separately from the orchestrator: HF is a long, two-stage
crawl (listing pages + per-org profile fetches) that benefits from explicit
flags rather than the registry's default cooldown logic.

Usage:
  # Quick smoke test — 3 listing pages, no profile enrichment, dry-run
  python scripts/run_huggingface_scrape.py --max-pages 3 --no-enrich --dry-run

  # Production run — top ~25k orgs, full enrichment, save to DB
  python scripts/run_huggingface_scrape.py --max-pages 500

  # Cap at the high-signal slice (top ~5k orgs, very fast)
  python scripts/run_huggingface_scrape.py --max-pages 100 --min-followers 50
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.db.connection import init_db  # noqa: E402
from backend.scrapers.base import (  # noqa: E402
    postprocess_records,
    save_companies_to_db,
    validate_records,
)
from backend.scrapers.easy.huggingface_scraper import HuggingFaceScraper  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("hf_scrape")


def main() -> None:
    p = argparse.ArgumentParser(description="HuggingFace org scraper")
    p.add_argument("--mode", choices=("api", "listing"), default="api",
                   help="api: enumerate orgs via /api/models cursor (recommended); "
                        "listing: scrape /organizations HTML (gets rate-limited)")
    p.add_argument("--api-model-pages", type=int, default=10,
                   help="API mode: number of /api/models cursor pages (1000 models/page)")
    p.add_argument("--api-sort", choices=("downloads", "likes", "trending"),
                   default="downloads",
                   help="API mode: which model ranking to traverse for author discovery")
    p.add_argument("--max-pages", type=int, default=500,
                   help="Listing-mode only: pages to crawl (50 orgs/page)")
    p.add_argument("--page-offset", type=int, default=0,
                   help="Start crawl at this listing page (resume support)")
    p.add_argument("--min-followers", type=int, default=0,
                   help="Drop orgs below this follower count")
    p.add_argument("--no-enrich", action="store_true",
                   help="Skip per-org profile fetch (no website/social discovery)")
    p.add_argument("--enrich-workers", type=int, default=8,
                   help="Concurrent workers for profile fetches (default: 8)")
    p.add_argument("--include-non-companies", action="store_true",
                   help="Keep orgs typed university/non-profit/community/classroom too")
    p.add_argument("--allow-no-website", action="store_true",
                   help="Keep orgs with no detected external website")
    p.add_argument("--dry-run", action="store_true",
                   help="Run scraper but skip DB writes")
    args = p.parse_args()

    init_db()

    scraper = HuggingFaceScraper(
        mode=args.mode,
        api_model_pages=args.api_model_pages,
        api_sort=args.api_sort,
        max_pages=args.max_pages,
        page_offset=args.page_offset,
        enrich_companies=not args.no_enrich,
        keep_only_company=not args.include_non_companies,
        min_followers=args.min_followers,
        require_website=not args.allow_no_website,
        enrich_workers=args.enrich_workers,
    )

    if args.dry_run:
        records = scraper.scrape()
        validation = validate_records(records)
        cleaned = postprocess_records(records)
        logger.info(
            f"[dry-run] scraped={len(records)} cleaned={len(cleaned)} "
            f"valid={validation.is_good} reason={validation.reason}"
        )
        for r in records[:5]:
            logger.info(f"  sample: {r.name} | {r.website_url} | {r.profile_url}")
        return

    result = scraper.run(save_to_db=True)
    logger.info(
        f"Done: status={result.status} found={result.records_found} "
        f"new={result.records_new} updated={result.records_updated}"
    )


if __name__ == "__main__":
    main()
