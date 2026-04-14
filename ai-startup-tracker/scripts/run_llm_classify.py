#!/usr/bin/env python3
"""
Standalone LLM classification for GitHub repo snapshots.

Runs LLM classification (Ollama local or Groq cloud) on snapshots
that haven't been classified yet.
Can be run independently after github_weekly_discover.py --no-llm.

Usage:
    python scripts/run_llm_classify.py [--batch-limit 100] [--dry-run]
"""
import argparse
import logging
import os
import sys
import time

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.db.connection import session_scope
from backend.db.models import GithubRepoSnapshot
from backend.utils.llm_filter import (
    classify_batch_with_llm, BATCH_SIZE, LLM_STARTUP_CONFIDENCE,
    LLM_BACKEND, LLM_MODEL,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("llm_classify")


def get_unclassified_snapshots(limit: int = 0):
    """Fetch snapshots that haven't been LLM-classified yet."""
    with session_scope() as session:
        query = session.query(GithubRepoSnapshot).filter(
            GithubRepoSnapshot.llm_classification.is_(None)
        ).order_by(GithubRepoSnapshot.startup_likelihood.desc())

        if limit > 0:
            query = query.limit(limit)

        snapshots = query.all()

        records = []
        for s in snapshots:
            records.append({
                "repo_full_name": s.repo_full_name,
                "owner_type": s.owner_type,
                "description": s.description,
                "domain": None,
                "homepage_url": s.homepage_url,
                "topics": s.topics or [],
                "stars": s.stars or 0,
                "forks": s.forks or 0,
                "language": s.language,
                "readme_snippet": None,
                "startup_likelihood": s.startup_likelihood,
                "snapshot_id": s.id,
            })
        return records


def classify_and_save(records, dry_run=False):
    """Classify records in batches and save results to DB."""
    total = len(records)
    classified = 0
    startups = 0
    consecutive_failures = 0

    for i in range(0, total, BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

        if consecutive_failures >= 3:
            logger.warning(f"3 consecutive LLM failures. Stopping. Classified {classified}/{total} so far.")
            break

        logger.info(f"Batch {batch_num}/{total_batches} ({len(batch)} repos)...")
        results = classify_batch_with_llm(batch)

        batch_failed = all(r.get("classification") == "unknown" for r in results)
        if batch_failed:
            consecutive_failures += 1
            logger.warning(f"Batch failed ({consecutive_failures} consecutive failures)")
        else:
            consecutive_failures = 0

        if not dry_run:
            with session_scope() as session:
                for rec, result in zip(batch, results):
                    snapshot_id = rec["snapshot_id"]
                    snapshot = session.get(GithubRepoSnapshot, snapshot_id)
                    if snapshot:
                        snapshot.llm_classification = result.get("classification", "unknown")
                        snapshot.llm_confidence = float(result.get("confidence", 0.0))
                        snapshot.llm_reason = result.get("reason", "")
                        classified += 1
                        if result.get("classification") == "startup" and float(result.get("confidence", 0)) >= LLM_STARTUP_CONFIDENCE:
                            startups += 1

        if classified % 100 == 0 and classified > 0:
            logger.info(f"Progress: {classified}/{total} classified, {startups} startups so far")

    logger.info(f"Done: {classified}/{total} classified, {startups} identified as startups")
    return classified, startups


def main():
    parser = argparse.ArgumentParser(description="Run LLM classification on unclassified snapshots")
    parser.add_argument("--batch-limit", type=int, default=0,
                        help="Max snapshots to classify (0=all unclassified)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run LLM but don't save results")
    args = parser.parse_args()

    logger.info(f"Backend: {LLM_BACKEND} | Model: {LLM_MODEL} | Batch size: {BATCH_SIZE}")
    logger.info("Fetching unclassified snapshots...")
    records = get_unclassified_snapshots(limit=args.batch_limit)
    logger.info(f"Found {len(records)} unclassified snapshots")

    if not records:
        logger.info("Nothing to classify!")
        return

    classify_and_save(records, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
