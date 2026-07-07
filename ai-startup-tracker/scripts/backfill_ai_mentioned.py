#!/usr/bin/env python3
"""
Backfill ai_mentioned for all companies.

Sets ai_mentioned = TRUE if the company name or description contains
AI-related keywords (STRONG or MODERATE patterns, or AI/ML in name).
Pure regex — no API calls, runs in under a minute across 916K companies.

Usage:
    python scripts/backfill_ai_mentioned.py [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text

from backend.db.connection import get_engine, init_db
from backend.utils.scoring import compute_ai_mentioned

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill_ai_mentioned")

BATCH_SIZE = 5000


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    init_db()

    engine = get_engine()

    logger.info("Fetching all companies with name or description…")
    query = """
        SELECT id, name, description, verification_status
        FROM companies
        WHERE name IS NOT NULL OR description IS NOT NULL
    """
    if args.limit:
        query += f" LIMIT {args.limit}"

    with engine.connect() as c:
        rows = c.execute(text(query)).fetchall()

    logger.info(f"Candidates: {len(rows):,}")

    flagged: list[int] = []
    by_source: dict[str, int] = {}

    for row_id, name, description, vs in rows:
        if compute_ai_mentioned(name=name, description=description):
            flagged.append(row_id)
            by_source[vs] = by_source.get(vs, 0) + 1

    logger.info(f"Companies with ai_mentioned=TRUE: {len(flagged):,}")
    logger.info("Breakdown by verification_status:")
    for vs, n in sorted(by_source.items(), key=lambda x: -x[1]):
        logger.info(f"  {vs}: {n:,}")

    if args.dry_run:
        logger.info("[DRY RUN] No writes.")
        return

    logger.info(f"Writing {len(flagged):,} flags in batches of {BATCH_SIZE}…")
    written = 0
    with engine.begin() as c:
        # Reset all to FALSE first so re-runs are idempotent
        c.execute(text("UPDATE companies SET ai_mentioned = FALSE WHERE ai_mentioned = TRUE"))
        for i in range(0, len(flagged), BATCH_SIZE):
            batch = flagged[i: i + BATCH_SIZE]
            c.execute(
                text("UPDATE companies SET ai_mentioned = TRUE WHERE id = ANY(:ids)"),
                {"ids": batch},
            )
            written += len(batch)
            if written % 50000 == 0 or written == len(flagged):
                logger.info(f"  Written {written:,}/{len(flagged):,}")

    # Final tally
    with engine.connect() as c:
        total = c.execute(text("SELECT COUNT(*) FROM companies WHERE ai_mentioned = TRUE")).scalar()
        logger.info(f"Final ai_mentioned=TRUE: {total:,}")

        rows2 = c.execute(text("""
            SELECT verification_status,
                   COUNT(*) FILTER (WHERE ai_mentioned) as flagged,
                   COUNT(*) as total
            FROM companies
            GROUP BY verification_status
            ORDER BY flagged DESC
        """)).fetchall()
        logger.info("Final breakdown:")
        for vs, flagged_n, total_n in rows2:
            pct = 100 * flagged_n / total_n if total_n else 0
            logger.info(f"  {vs}: {flagged_n:,}/{total_n:,} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
