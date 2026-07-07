#!/usr/bin/env python3
"""
Backfill companies.categories from Crunchbase and PitchBook parquets.

Pass 1 — CB (organizations.parquet):
  Joins on domain, maps category_groups_list → canonical verticals.
  Updates all CB companies (overwrites any existing value).

Pass 2 — PB global (pitchbook_other_glob_company.parquet):
  Joins on domain, maps PrimaryIndustryGroup → canonical vertical.
  Only fills WHERE categories IS NULL (CB takes priority).

Pass 3 — PB VC-NA (pitchbook_vc_na_company.parquet):
  Same as pass 2.

Usage:
    python scripts/backfill_company_categories.py [--dry-run] [--cb-only] [--pb-only]
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from sqlalchemy import text

from backend.db.connection import get_engine
from backend.utils.domain import canonicalize_domain
from backend.utils.industry import map_cb_categories, map_pb_category

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill_categories")

CB_PARQUET   = "/Users/alastairpage/Downloads/organizations.parquet"
PB_GLOBAL    = "/Users/alastairpage/Downloads/pitchbook_other_glob_company.parquet"
PB_NA        = "/Users/alastairpage/Downloads/pitchbook_vc_na_company.parquet"
BATCH_SIZE   = 2000


def _load_db_domains(engine) -> dict[str, int]:
    """Return {domain: company_id} for all companies with a domain."""
    logger.info("Loading DB domains…")
    with engine.connect() as c:
        rows = c.execute(text("SELECT id, domain FROM companies WHERE domain IS NOT NULL")).fetchall()
    return {row[1]: row[0] for row in rows}


def _bulk_update(engine, updates: list[tuple[list[str], int]], dry_run: bool) -> int:
    """Bulk UPDATE categories for (categories, id) pairs. Returns rows written."""
    if dry_run or not updates:
        return len(updates)
    written = 0
    with engine.begin() as c:
        for i in range(0, len(updates), BATCH_SIZE):
            batch = updates[i : i + BATCH_SIZE]
            for cats, cid in batch:
                c.execute(
                    text("UPDATE companies SET categories = :cats WHERE id = :id"),
                    {"cats": cats, "id": cid},
                )
            written += len(batch)
            if written % 10000 == 0:
                logger.info(f"    Written {written:,}…")
    return written


def pass_cb(engine, domain_map: dict[str, int], dry_run: bool) -> Counter:
    """Map CB category_groups_list → canonical and update all matched companies."""
    logger.info(f"Pass 1: CB parquet ({CB_PARQUET})")
    df = pd.read_parquet(CB_PARQUET, columns=["domain", "category_groups_list"])
    df = df[df["domain"].notna() & df["category_groups_list"].notna()]
    logger.info(f"  CB rows with domain+category: {len(df):,}")

    updates: list[tuple[list[str], int]] = []
    counts: Counter = Counter()
    skipped = 0

    for _, row in df.iterrows():
        domain = str(row["domain"]).strip().lower()
        cid = domain_map.get(domain)
        if cid is None:
            skipped += 1
            continue
        cats = map_cb_categories(row["category_groups_list"])
        if not cats:
            counts["(unmapped)"] += 1
            continue
        for c in cats:
            counts[c] += 1
        updates.append((cats, cid))

    logger.info(f"  Matched: {len(updates):,}  |  No DB match: {skipped:,}  |  Unmapped: {counts['(unmapped)']:,}")
    written = _bulk_update(engine, updates, dry_run)
    logger.info(f"  {'[DRY RUN] Would write' if dry_run else 'Written'}: {written:,}")
    return counts


def pass_pb(engine, domain_map: dict[str, int], parquet_path: str,
            label: str, dry_run: bool) -> Counter:
    """Map PB PrimaryIndustryGroup → canonical, fill gaps only (categories IS NULL)."""
    logger.info(f"Pass: {label} ({parquet_path})")
    df = pd.read_parquet(parquet_path, columns=["Website", "PrimaryIndustryGroup"])
    df = df[df["Website"].notna() & df["PrimaryIndustryGroup"].notna()]
    logger.info(f"  Rows with website+industry: {len(df):,}")

    # Fetch which companies already have categories set
    with engine.connect() as c:
        already = set(
            row[0] for row in
            c.execute(text("SELECT id FROM companies WHERE categories IS NOT NULL")).fetchall()
        )
    logger.info(f"  Companies already categorised (skip): {len(already):,}")

    updates: list[tuple[list[str], int]] = []
    counts: Counter = Counter()
    skipped_no_match = 0
    skipped_has_cats = 0

    for _, row in df.iterrows():
        domain = canonicalize_domain(str(row["Website"]))
        if not domain:
            skipped_no_match += 1
            continue
        cid = domain_map.get(domain)
        if cid is None:
            skipped_no_match += 1
            continue
        if cid in already:
            skipped_has_cats += 1
            continue
        cats = map_pb_category(row["PrimaryIndustryGroup"])
        if not cats:
            counts["(unmapped)"] += 1
            continue
        for c in cats:
            counts[c] += 1
        updates.append((cats, cid))
        already.add(cid)  # don't double-process within same PB run

    logger.info(f"  New updates: {len(updates):,}  |  No DB match: {skipped_no_match:,}  |  Already set: {skipped_has_cats:,}")
    written = _bulk_update(engine, updates, dry_run)
    logger.info(f"  {'[DRY RUN] Would write' if dry_run else 'Written'}: {written:,}")
    return counts


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--cb-only", action="store_true")
    p.add_argument("--pb-only", action="store_true")
    args = p.parse_args()

    engine = get_engine()
    domain_map = _load_db_domains(engine)
    logger.info(f"DB domains loaded: {len(domain_map):,}")

    all_counts: Counter = Counter()

    if not args.pb_only:
        counts = pass_cb(engine, domain_map, args.dry_run)
        all_counts.update(counts)

    if not args.cb_only:
        counts = pass_pb(engine, domain_map, PB_GLOBAL, "PB Global", args.dry_run)
        all_counts.update(counts)
        counts = pass_pb(engine, domain_map, PB_NA, "PB VC-NA", args.dry_run)
        all_counts.update(counts)

    logger.info("\n── Canonical category distribution ──────────────────")
    for cat, n in sorted(all_counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {cat:30} {n:>8,}")

    # Final DB check
    with engine.connect() as c:
        filled = c.execute(text(
            "SELECT COUNT(*) FROM companies WHERE categories IS NOT NULL AND array_length(categories,1) > 0"
        )).scalar()
        total = c.execute(text("SELECT COUNT(*) FROM companies")).scalar()
    logger.info(f"\nDB: {filled:,}/{total:,} companies have categories ({filled/total*100:.1f}%)")


if __name__ == "__main__":
    main()
