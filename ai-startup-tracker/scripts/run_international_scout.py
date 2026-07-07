#!/usr/bin/env python3
"""
International Scout Runner
===========================
Systematically rotates through target countries, running the scout agent
for each one and tracking coverage so no country gets over- or under-served.

Coverage state is persisted in data/scout_coverage.json:
  {
    "KR": {"last_run": "2026-05-24T18:00:00Z", "total_found": 12, "runs": 3},
    ...
  }

Priority order for unsupervised runs (--all):
  1. Never scouted (sorted by country code for determinism)
  2. Scouted but yield was 0 (retry with back-off)
  3. Scouted longest ago

Usage:
    # Run a single country
    python scripts/run_international_scout.py --country KR --limit 20

    # Run all countries in priority order (one pass)
    python scripts/run_international_scout.py --all --limit 20

    # Run all countries, pause between each to respect rate limits
    python scripts/run_international_scout.py --all --limit 20 --pause 30
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from backend.discovery.scout import scout, _QUERIES_BY_COUNTRY

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("international_scout")

# Countries with dedicated query sets, in recommended priority order.
# KR / IL / CN are the primary focus; SG / JP / IN are high-value secondaries.
PRIORITY_COUNTRIES = ["KR", "IL", "CN", "SG", "JP", "IN"]

COVERAGE_FILE = Path(__file__).parent.parent / "data" / "scout_coverage.json"


# ── Coverage helpers ───────────────────────────────────────────────────────

def load_coverage() -> Dict[str, dict]:
    if COVERAGE_FILE.exists():
        try:
            return json.loads(COVERAGE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_coverage(coverage: Dict[str, dict]) -> None:
    COVERAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE_FILE.write_text(json.dumps(coverage, indent=2, default=str))


def update_coverage(coverage: Dict[str, dict], country: str, found: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    entry = coverage.get(country, {"total_found": 0, "runs": 0})
    entry["last_run"] = now
    entry["total_found"] = entry.get("total_found", 0) + found
    entry["runs"] = entry.get("runs", 0) + 1
    entry["last_found"] = found
    coverage[country] = entry


def prioritised_countries(coverage: Dict[str, dict], countries: list[str]) -> list[str]:
    """Sort countries: never scouted first, then by oldest last_run."""
    def sort_key(c: str):
        entry = coverage.get(c)
        if not entry:
            return (0, "")         # never scouted → highest priority
        return (1, entry.get("last_run", ""))   # scouted → oldest first

    return sorted(countries, key=sort_key)


# ── Runner ─────────────────────────────────────────────────────────────────

def run_country(country: str, limit: int) -> int:
    """Run scout for one country. Returns number of new sites found."""
    logger.info(f"{'='*55}")
    logger.info(f"Scouting: {country}  (limit={limit})")
    logger.info(f"{'='*55}")
    results = scout(country=country, limit=limit)
    logger.info(f"{country}: {len(results)} new site(s) registered")
    for r in results:
        logger.info(f"  {r.domain:40s}  {r.category:22s}  conf={r.confidence:.2f}")
    return len(results)


def main() -> None:
    parser = argparse.ArgumentParser(description="International Scout Runner")
    parser.add_argument("--country", help="Run a single country (ISO code, e.g. KR)")
    parser.add_argument("--all", action="store_true", help="Run all priority countries")
    parser.add_argument("--limit", type=int, default=20, help="Max new sites per country (default: 20)")
    parser.add_argument("--pause", type=int, default=15, help="Seconds to pause between countries (default: 15)")
    parser.add_argument("--show-coverage", action="store_true", help="Print coverage summary and exit")
    args = parser.parse_args()

    coverage = load_coverage()

    if args.show_coverage:
        if not coverage:
            print("No scout runs recorded yet.")
        else:
            print(f"\n{'Country':<8} {'Runs':<6} {'Total Found':<14} {'Last Run'}")
            print("-" * 55)
            for c in PRIORITY_COUNTRIES:
                entry = coverage.get(c)
                if entry:
                    print(
                        f"{c:<8} {entry['runs']:<6} {entry['total_found']:<14} "
                        f"{entry['last_run'][:19]}"
                    )
                else:
                    print(f"{c:<8} {'—':<6} {'—':<14} never")
        return

    if not args.country and not args.all:
        parser.print_help()
        return

    if args.country:
        countries = [args.country.upper()]
    else:
        countries = prioritised_countries(coverage, PRIORITY_COUNTRIES)

    total_found = 0
    for i, country in enumerate(countries):
        found = run_country(country, limit=args.limit)
        update_coverage(coverage, country, found)
        save_coverage(coverage)
        total_found += found

        if args.all and i < len(countries) - 1:
            logger.info(f"Pausing {args.pause}s before next country...")
            time.sleep(args.pause)

    logger.info(f"\n{'='*55}")
    logger.info(f"Scout run complete.  Total new sites: {total_found}")
    logger.info(f"Coverage saved to: {COVERAGE_FILE}")
    logger.info(f"{'='*55}")

    # Print final coverage table
    print(f"\n{'Country':<8} {'Runs':<6} {'Total Found':<14} {'Last Run'}")
    print("-" * 55)
    for c in PRIORITY_COUNTRIES:
        entry = coverage.get(c)
        if entry:
            print(
                f"{c:<8} {entry['runs']:<6} {entry['total_found']:<14} "
                f"{entry['last_run'][:19]}"
            )
        else:
            print(f"{c:<8} {'—':<6} {'—':<14} never")


if __name__ == "__main__":
    main()
