#!/usr/bin/env python3
"""
Backfill ai_score for all companies that currently have ai_score = 0.

Uses the same compute_ai_score() function as the live pipeline — no API calls,
pure regex keyword matching on descriptions. CB companies also get the +0.2
boost from cb_ai_tagged.

Only writes when the computed score > 0, leaving true zeros untouched so we
can distinguish "never scored" from "scored and not AI".

Usage:
    python scripts/backfill_ai_score.py [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text

from backend.db.connection import get_engine
from backend.utils.scoring import compute_ai_score

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill_ai_score")

BATCH_SIZE = 5000


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    engine = get_engine()

    # Fetch all unscored companies that have a description to work with
    logger.info("Fetching unscored companies with descriptions…")
    query = """
        SELECT id, description, cb_ai_tagged
        FROM companies
        WHERE (ai_score IS NULL OR ai_score = 0)
          AND description IS NOT NULL
          AND length(description) >= 20
    """
    if args.limit:
        query += f" LIMIT {args.limit}"

    with engine.connect() as c:
        rows = c.execute(text(query)).fetchall()

    logger.info(f"Candidates: {len(rows):,}")

    updates: list[tuple[float, int]] = []
    score_buckets = {">= 0.5": 0, "0.3-0.49": 0, "0.2-0.29": 0, "0.1-0.19": 0, "> 0": 0}

    for row_id, description, cb_ai_tagged in rows:
        score = compute_ai_score(
            description=description,
            cb_ai_flag=bool(cb_ai_tagged),
        )
        if score > 0:
            updates.append((score, row_id))
            if score >= 0.5:
                score_buckets[">= 0.5"] += 1
            elif score >= 0.3:
                score_buckets["0.3-0.49"] += 1
            elif score >= 0.2:
                score_buckets["0.2-0.29"] += 1
            else:
                score_buckets["0.1-0.19"] += 1
            score_buckets["> 0"] += 1

    logger.info(f"Companies with score > 0: {len(updates):,}")
    logger.info("Score distribution:")
    for bucket, n in score_buckets.items():
        logger.info(f"  {bucket}: {n:,}")

    if args.dry_run:
        logger.info("[DRY RUN] No writes.")
        return

    logger.info(f"Writing {len(updates):,} scores in batches of {BATCH_SIZE}…")
    written = 0
    with engine.begin() as c:
        for i in range(0, len(updates), BATCH_SIZE):
            batch = updates[i : i + BATCH_SIZE]
            for score, row_id in batch:
                c.execute(
                    text("UPDATE companies SET ai_score = :s WHERE id = :id"),
                    {"s": score, "id": row_id},
                )
            written += len(batch)
            if written % 50000 == 0 or written == len(updates):
                logger.info(f"  Written {written:,}/{len(updates):,}")

    # Final tally
    with engine.connect() as c:
        for threshold in (0.5, 0.3, 0.2, 0.1):
            n = c.execute(
                text("SELECT COUNT(*) FROM companies WHERE ai_score >= :t OR cb_ai_tagged = TRUE"),
                {"t": threshold},
            ).scalar()
            logger.info(f"AI companies (ai_score >= {threshold} OR cb_ai_tagged): {n:,}")


if __name__ == "__main__":
    main()
