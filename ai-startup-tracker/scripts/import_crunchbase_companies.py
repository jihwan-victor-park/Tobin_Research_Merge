#!/usr/bin/env python3
"""
Crunchbase Company Import
=========================
Imports AI startups from Crunchbase bulk-export parquet files into the DB.

Targets high-ROI international countries underrepresented in the current DB.
LocationSource.crunchbase and VerificationStatus.verified_cb already exist
in the schema — no DB migration required.

Filter chain:
  1. primary_role == "company"  (drop investors, schools)
  2. country_code in target list (3-letter ISO)
  3. status in {operating, ipo}
  4. founded_on >= --min-founded (default: 2010)
  5. category_groups_list contains AI/data/software keywords
  6. ai_score >= --min-ai-score (default: 0.15; computed from descriptions)

Usage:
    # Dry-run to see counts before writing
    python scripts/import_crunchbase_companies.py \\
        --orgs ~/Downloads/organizations.parquet \\
        --descs ~/Downloads/organization_descriptions.parquet \\
        --dry-run

    # Full import (all 14 default countries)
    python scripts/import_crunchbase_companies.py \\
        --orgs ~/Downloads/organizations.parquet \\
        --descs ~/Downloads/organization_descriptions.parquet

    # Specific countries only
    python scripts/import_crunchbase_companies.py \\
        --orgs ~/Downloads/organizations.parquet \\
        --descs ~/Downloads/organization_descriptions.parquet \\
        --countries GBR IND DEU
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Set

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.db.connection import session_scope, init_db
from backend.db.models import Company, VerificationStatus, LocationSource
from backend.utils.domain import canonicalize_domain
from backend.utils.normalize import normalize_company_name
from backend.utils.scoring import compute_ai_score

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("import_cb_companies")

# 3-letter Crunchbase ISO → 2-letter DB ISO
TARGET_COUNTRIES: Dict[str, str] = {
    "GBR": "GB",  # United Kingdom
    "IND": "IN",  # India
    "DEU": "DE",  # Germany
    "CAN": "CA",  # Canada
    "FRA": "FR",  # France
    "SGP": "SG",  # Singapore
    "AUS": "AU",  # Australia
    "ISR": "IL",  # Israel
    "KOR": "KR",  # South Korea
    "SWE": "SE",  # Sweden
    "NLD": "NL",  # Netherlands
    "BRA": "BR",  # Brazil
    "CHN": "CN",  # China
    "JPN": "JP",  # Japan
}

# Companies with this tag are always included (Crunchbase's own AI classification)
CB_AI_TAG = "Artificial Intelligence"

# Broader tech categories — included only if ai_score also passes threshold
BROAD_TECH_CATEGORIES = [
    "Data and Analytics",
    "Science and Engineering",
    "Software",
    "Information Technology",
]

ACTIVE_STATUSES = {"operating", "ipo"}


def load_and_filter(
    orgs_path: str,
    descs_path: str,
    countries: Dict[str, str],
    min_founded: int,
    min_ai_score: float,
) -> pd.DataFrame:
    logger.info(f"Loading {orgs_path}")
    orgs = pd.read_parquet(orgs_path)
    logger.info(f"  Total orgs: {len(orgs):,}")

    # 1. Companies only (drop investors, schools)
    orgs = orgs[orgs["primary_role"] == "company"]
    logger.info(f"  After primary_role=company: {len(orgs):,}")

    # 2. Target countries
    orgs = orgs[orgs["country_code"].isin(countries.keys())]
    logger.info(f"  After country filter ({list(countries.keys())}): {len(orgs):,}")

    # 3. Active status
    orgs = orgs[orgs["status"].isin(ACTIVE_STATUSES)]
    logger.info(f"  After active status filter: {len(orgs):,}")

    # 4. Founded year
    orgs = orgs.copy()
    orgs["_founded_year"] = (
        pd.to_datetime(orgs["founded_on"], errors="coerce").dt.year
    )
    orgs = orgs[orgs["_founded_year"].fillna(0) >= min_founded]
    logger.info(f"  After founded >= {min_founded}: {len(orgs):,}")

    # 5. Category pre-screen — keep AI-tagged companies AND broader tech companies
    cats = orgs["category_groups_list"].fillna("")
    is_cb_ai = cats.str.contains(CB_AI_TAG, na=False)
    broad_pattern = "|".join(BROAD_TECH_CATEGORIES)
    is_broad_tech = cats.str.contains(broad_pattern, na=False)
    orgs = orgs[is_cb_ai | is_broad_tech].copy()
    orgs["_cb_ai_tagged"] = is_cb_ai[orgs.index]
    logger.info(
        f"  After category filter: {len(orgs):,} "
        f"({is_cb_ai.sum():,} CB-AI-tagged, rest broad tech)"
    )

    # 6. Join long descriptions
    logger.info(f"Loading {descs_path}")
    descs = pd.read_parquet(descs_path, columns=["uuid", "description"])
    orgs = orgs.merge(descs, on="uuid", how="left")
    logger.info(f"  Descriptions joined ({orgs['description'].notna().sum():,} have long desc)")

    # 7. Compute AI score
    logger.info("  Computing AI scores...")
    def _score(row) -> float:
        text = " ".join(filter(None, [
            str(row.get("short_description", "") or ""),
            str(row.get("description", "") or ""),
        ]))
        return compute_ai_score(description=text)

    orgs["_ai_score"] = orgs.apply(_score, axis=1)

    # CB-AI-tagged companies always pass; broader tech companies need ai_score threshold
    orgs = orgs[orgs["_cb_ai_tagged"] | (orgs["_ai_score"] >= min_ai_score)]
    logger.info(
        f"  After AI filter (CB-tagged OR ai_score >= {min_ai_score}): {len(orgs):,}"
    )

    return orgs


BATCH_SIZE = 500  # rows per DB transaction


def _load_existing(db) -> tuple[Set[str], Dict[str, int]]:
    existing_domains: Set[str] = set()
    existing_norm_names: Dict[str, int] = {}
    for c in db.query(Company.domain, Company.normalized_name, Company.id).all():
        if c.domain:
            existing_domains.add(c.domain.lower())
        if c.normalized_name:
            existing_norm_names[c.normalized_name.lower()] = c.id
    return existing_domains, existing_norm_names


def _process_row(row, country_map, existing_domains, existing_norm_names, db, stats, now):
    name = str(row.get("name", "") or "").strip()
    if not name:
        return

    raw_domain = str(row.get("domain", "") or row.get("homepage_url", "") or "")
    domain = canonicalize_domain(raw_domain)
    norm = normalize_company_name(name)

    country_3 = str(row.get("country_code", "") or "")
    country_code = country_map.get(country_3)
    city = str(row.get("city", "") or "").strip() or None

    short_desc = str(row.get("short_description", "") or "").strip()
    long_desc = str(row.get("description", "") or "").strip()
    description = (short_desc + " " + long_desc).strip() or None

    ai_score = float(row["_ai_score"])
    founded_year_raw = row.get("_founded_year")
    founded_year = int(founded_year_raw) if pd.notna(founded_year_raw) else None

    status = str(row.get("status", "") or "").strip()
    operating_status = "operating" if status in ACTIVE_STATUSES else "closed"

    existing = None
    if domain and domain.lower() in existing_domains:
        existing = db.query(Company).filter(Company.domain == domain).first()
    elif norm and norm.lower() in existing_norm_names:
        existing = db.query(Company).filter(Company.id == existing_norm_names[norm.lower()]).first()

    if existing:
        changed = False
        if not existing.country and country_code:
            existing.country = country_code
            existing.location_source = LocationSource.crunchbase
            changed = True
        if not existing.city and city:
            existing.city = city
            changed = True
        if not existing.description and description:
            existing.description = description
            changed = True
        if not existing.founded_year and founded_year:
            existing.founded_year = founded_year
            changed = True
        if (existing.ai_score or 0) < ai_score:
            existing.ai_score = ai_score
            changed = True
        if existing.verification_status == VerificationStatus.emerging_github:
            existing.verification_status = VerificationStatus.verified_cb
            changed = True
        if changed:
            existing.updated_at = now
            stats["updated"] += 1
        else:
            stats["skipped"] += 1
    else:
        company = Company(
            name=name,
            domain=domain,
            normalized_name=norm,
            country=country_code,
            city=city,
            description=description,
            founded_year=founded_year,
            operating_status=operating_status,
            ai_score=ai_score,
            verification_status=VerificationStatus.verified_cb,
            location_source=LocationSource.crunchbase if country_code else None,
            first_seen_at=now,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(company)
        if domain:
            existing_domains.add(domain.lower())
        if norm:
            existing_norm_names[norm.lower()] = -1
        stats["new"] += 1


def import_companies(df: pd.DataFrame, country_map: Dict[str, str], dry_run: bool) -> Dict[str, int]:
    stats = {"new": 0, "updated": 0, "skipped": 0}
    now = datetime.now(timezone.utc)

    if dry_run:
        return {"new": len(df), "updated": 0, "skipped": 0}

    # Load existing dedup sets once
    with session_scope() as db:
        existing_domains, existing_norm_names = _load_existing(db)
    logger.info(f"  Loaded {len(existing_domains):,} existing domains for dedup")

    # Process in batches to avoid connection timeouts
    rows = list(df.iterrows())
    total = len(rows)
    for batch_start in range(0, total, BATCH_SIZE):
        batch = rows[batch_start: batch_start + BATCH_SIZE]
        with session_scope() as db:
            for _, row in batch:
                _process_row(row, country_map, existing_domains, existing_norm_names, db, stats, now)
        logger.info(
            f"  Batch {batch_start // BATCH_SIZE + 1}/{(total + BATCH_SIZE - 1) // BATCH_SIZE} committed "
            f"— new={stats['new']} updated={stats['updated']} skipped={stats['skipped']}"
        )

    return stats


def main():
    parser = argparse.ArgumentParser(description="Import Crunchbase companies into the DB")
    parser.add_argument("--orgs", required=True, help="Path to organizations.parquet")
    parser.add_argument("--descs", required=True, help="Path to organization_descriptions.parquet")
    parser.add_argument(
        "--countries", nargs="+", default=list(TARGET_COUNTRIES.keys()),
        help="3-letter ISO country codes to import (default: all 14 target countries)",
    )
    parser.add_argument("--min-founded", type=int, default=2010, help="Min founding year (default: 2010)")
    parser.add_argument("--min-ai-score", type=float, default=0.15, help="Min AI score (default: 0.15)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    parser.add_argument("--init-db", action="store_true", help="Create DB tables before running")
    args = parser.parse_args()

    if args.init_db:
        init_db()

    for path in [args.orgs, args.descs]:
        if not os.path.exists(path):
            logger.error(f"File not found: {path}")
            sys.exit(1)

    country_map = {k: v for k, v in TARGET_COUNTRIES.items() if k in args.countries}
    if not country_map:
        logger.error(f"No valid country codes in: {args.countries}")
        sys.exit(1)

    df = load_and_filter(
        orgs_path=args.orgs,
        descs_path=args.descs,
        countries=country_map,
        min_founded=args.min_founded,
        min_ai_score=args.min_ai_score,
    )

    if df.empty:
        logger.warning("No companies passed filters — nothing to import.")
        return

    logger.info(f"\n── Sample (top 10 by AI score) ──")
    sample = df.nlargest(10, "_ai_score")[["name", "country_code", "city", "_ai_score", "short_description"]]
    for _, r in sample.iterrows():
        logger.info(
            f"  [{r['country_code']}] {r['name']} (ai={r['_ai_score']:.2f}): "
            f"{str(r['short_description'])[:100]}"
        )

    if args.dry_run:
        logger.info(f"\n── Dry-run summary ──")
        logger.info(f"  Would import: {len(df):,} companies")
        by_country = df["country_code"].value_counts()
        for cc, count in by_country.items():
            iso2 = country_map.get(cc, cc)
            logger.info(f"    {cc} ({iso2}): {count:,}")
        logger.info(f"\n  AI score distribution:")
        bins = [0, 0.15, 0.2, 0.3, 0.5, 1.0]
        counts = pd.cut(df["_ai_score"], bins=bins).value_counts().sort_index()
        for bucket, count in counts.items():
            logger.info(f"    {bucket}: {count:,}")
        return

    logger.info(f"\nImporting {len(df):,} companies in batches of {BATCH_SIZE}...")
    stats = import_companies(df, country_map=country_map, dry_run=False)

    logger.info("=" * 55)
    logger.info("Crunchbase Company Import Complete!")
    logger.info(f"  New companies:    {stats['new']:,}")
    logger.info(f"  Updated existing: {stats['updated']:,}")
    logger.info(f"  Skipped (no change): {stats['skipped']:,}")
    logger.info("=" * 55)


if __name__ == "__main__":
    main()
