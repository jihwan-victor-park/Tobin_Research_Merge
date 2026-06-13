#!/usr/bin/env python3
"""
Backfill ai_tags subdomain on cb_ai_tagged companies using keyword classifier.

Runs classify_repo() from backend/utils/classify.py on each company's
description. Only writes ai_tags when a specific subdomain is matched
(not "Other") — leaves unclassifiable companies with empty tags rather
than polluting with a useless marker.

Usage:
    python scripts/backfill_cb_ai_tags.py [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.db.connection import session_scope
from backend.db.models import Company
from backend.utils.classify import classify_repo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill_cb_ai_tags")

# CB descriptions commonly open with these phrases — strip them so
# "developer" doesn't falsely trigger the DevTools rule.
_CB_OPENERS = re.compile(
    r"^(developer|provider|creator|builder|maker|operator|designer|"
    r"enabler|pioneer|leader|manufacturer)\s+of\s+",
    re.I,
)

BATCH_SIZE = 500


def _clean_desc(text: str | None) -> str:
    if not text:
        return ""
    return _CB_OPENERS.sub("", text.strip())


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="Classify but don't write")
    p.add_argument("--limit", type=int, default=0, help="Max companies (0=all)")
    args = p.parse_args()

    counts: Counter = Counter()
    to_update: list[tuple[int, str]] = []  # (id, subdomain)

    with session_scope() as session:
        q = (
            session.query(Company.id, Company.name, Company.description)
            .filter(
                Company.cb_ai_tagged.is_(True),
                # Only companies without existing tags
                (Company.ai_tags.is_(None)) | (Company.ai_tags == []),
            )
            .order_by(Company.id)
            .yield_per(1000)
        )
        if args.limit:
            q = q.limit(args.limit)

        processed = 0
        for company_id, name, description in q:
            text = f"{name or ''} {_clean_desc(description)}".strip()
            subdomain, _ = classify_repo(description=text)
            counts[subdomain] += 1
            if subdomain != "Other":
                to_update.append((company_id, subdomain))
            processed += 1
            if processed % 5000 == 0:
                logger.info(f"  Classified {processed:,} companies…")

    logger.info(f"Classified {processed:,} companies total")
    logger.info(f"Tagged (non-Other): {len(to_update):,}")
    logger.info(f"Unclassified (Other): {counts['Other']:,}")

    logger.info("\nSubdomain breakdown:")
    for subdomain, n in sorted(counts.items(), key=lambda x: -x[1]):
        pct = n / processed * 100 if processed else 0
        marker = "  (will write)" if subdomain != "Other" else "  (skip)"
        logger.info(f"  {subdomain:22} {n:>6,}  ({pct:.1f}%){marker}")

    if args.dry_run:
        logger.info("\n[dry-run] No writes performed.")
        return

    if not to_update:
        logger.info("Nothing to write.")
        return

    # Write in batches
    written = 0
    with session_scope() as session:
        for i in range(0, len(to_update), BATCH_SIZE):
            batch = to_update[i : i + BATCH_SIZE]
            ids_by_subdomain: dict[str, list[int]] = {}
            for cid, sub in batch:
                ids_by_subdomain.setdefault(sub, []).append(cid)
            for subdomain, ids in ids_by_subdomain.items():
                (
                    session.query(Company)
                    .filter(Company.id.in_(ids))
                    .update(
                        {Company.ai_tags: [subdomain]},
                        synchronize_session=False,
                    )
                )
            written += len(batch)
            if written % 5000 == 0:
                logger.info(f"  Written {written:,}/{len(to_update):,}…")

    logger.info(f"\nDone. {written:,} companies tagged.")
    logger.info(f"{counts['Other']:,} remain untagged (Other residual — LLM sweep optional).")


if __name__ == "__main__":
    main()
