#!/usr/bin/env python3
"""
PitchBook Company Import
========================
Imports companies from the PitchBook global company parquet into the DB.

Unlike import_pitchbook.py (which matches *deals* to existing companies),
this script creates new Company records from the PitchBook company file —
seeding the DB with international startups that no other source covers.

Filter chain:
  1. Target countries (default: South Korea, Israel, China)
  2. Active business status (drops Out of Business / Bankruptcy)
  3. Founded >= 2010
  4. IT sector (or --all-sectors to skip)
  5. ai_score >= --min-ai-score (default 0.1; computed from description/keywords)

Usage:
    # Dry-run to see what would be imported
    python scripts/import_pitchbook_companies.py --company data/pitchbook_other_glob_company.parquet --dry-run

    # Import SK/IL/CN (defaults)
    python scripts/import_pitchbook_companies.py --company data/pitchbook_other_glob_company.parquet

    # Any country, all sectors, lower AI threshold
    python scripts/import_pitchbook_companies.py --company data/pitchbook_other_glob_company.parquet \\
        --countries "Germany" "France" --all-sectors --min-ai-score 0.05
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

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
logger = logging.getLogger("import_pb_companies")

DEFAULT_COUNTRIES = ["South Korea", "Israel", "China"]

DEAD_STATUSES = {
    "Out of Business",
    "Bankruptcy: Liquidation",
    "Bankruptcy: Admin/Reorg",
}

# Maps PitchBook full country names to ISO codes used in the DB
COUNTRY_MAP = {
    "south korea": "KR", "korea, republic of": "KR",
    "israel": "IL", "israel (state of)": "IL",
    "china": "CN", "china, people's republic of": "CN",
    "united states": "US", "usa": "US",
    "united kingdom": "GB", "england": "GB",
    "germany": "DE", "france": "FR", "india": "IN",
    "canada": "CA", "japan": "JP", "australia": "AU",
    "brazil": "BR", "singapore": "SG", "netherlands": "NL",
    "sweden": "SE", "switzerland": "CH", "spain": "ES",
    "italy": "IT", "ireland": "IE", "denmark": "DK",
    "norway": "NO", "finland": "FI", "belgium": "BE",
    "austria": "AT", "poland": "PL", "portugal": "PT",
    "hong kong": "HK", "taiwan": "TW", "uae": "AE",
    "united arab emirates": "AE", "russia": "RU",
    "turkey": "TR", "ukraine": "UA", "mexico": "MX",
    "argentina": "AR", "colombia": "CO", "chile": "CL",
    "nigeria": "NG", "south africa": "ZA", "kenya": "KE",
    "egypt": "EG", "indonesia": "ID", "malaysia": "MY",
    "thailand": "TH", "vietnam": "VN", "philippines": "PH",
    "new zealand": "NZ", "estonia": "EE", "latvia": "LV",
    "lithuania": "LT", "czech republic": "CZ", "czechia": "CZ",
    "hungary": "HU", "romania": "RO", "greece": "GR",
    "bulgaria": "BG", "croatia": "HR", "serbia": "RS",
    "saudi arabia": "SA", "qatar": "QA", "kuwait": "KW",
    "pakistan": "PK", "bangladesh": "BD",
}


def to_country_code(raw: str) -> str:
    return COUNTRY_MAP.get(raw.lower().strip(), raw.strip())


def load_and_filter(
    path: str,
    countries: List[str],
    min_founded: int,
    it_only: bool,
    min_ai_score: float,
) -> pd.DataFrame:
    logger.info(f"Loading {path}")
    df = pd.read_parquet(path)
    logger.info(f"  Total rows: {len(df):,}")

    # Country filter
    df = df[df["HQCountry"].isin(countries)]
    logger.info(f"  After country filter ({countries}): {len(df):,}")

    # Drop dead companies
    df = df[~df["BusinessStatus"].isin(DEAD_STATUSES)]
    logger.info(f"  After active filter: {len(df):,}")

    # Founded year
    df = df[df["YearFounded"].fillna(0) >= min_founded]
    logger.info(f"  After founded >= {min_founded}: {len(df):,}")

    # IT sector
    if it_only:
        df = df[df["PrimaryIndustrySector"] == "Information Technology"]
        logger.info(f"  After IT sector filter: {len(df):,}")

    # Compute ai_score from description + keywords
    def _score(row) -> float:
        text = " ".join(filter(None, [
            str(row.get("Description", "") or ""),
            str(row.get("Keywords", "") or ""),
        ]))
        return compute_ai_score(description=text)

    logger.info("  Computing AI scores...")
    df = df.copy()
    df["_ai_score"] = df.apply(_score, axis=1)
    df = df[df["_ai_score"] >= min_ai_score]
    logger.info(f"  After ai_score >= {min_ai_score}: {len(df):,}")

    return df


def import_companies(df: pd.DataFrame, dry_run: bool) -> Dict[str, int]:
    stats = {"new": 0, "updated": 0, "skipped_domain_conflict": 0}
    now = datetime.now(timezone.utc)

    with session_scope() as db:
        # Preload existing domains and normalized names for dedup
        existing_domains: Set[str] = set()
        existing_norm_names: Dict[str, int] = {}
        for c in db.query(Company.domain, Company.normalized_name, Company.id).all():
            if c.domain:
                existing_domains.add(c.domain.lower())
            if c.normalized_name:
                existing_norm_names[c.normalized_name.lower()] = c.id

        for _, row in df.iterrows():
            name = str(row.get("CompanyName", "") or "").strip()
            if not name:
                continue

            domain = canonicalize_domain(str(row.get("Website", "") or ""))
            norm = normalize_company_name(name)
            country_raw = str(row.get("HQCountry", "") or "")
            country_code = to_country_code(country_raw)
            city = str(row.get("HQCity", "") or "").strip() or None
            description = str(row.get("Description", "") or "").strip() or None
            ai_score = float(row["_ai_score"])

            founded_raw = row.get("YearFounded")
            founded_year = int(founded_raw) if pd.notna(founded_raw) else None

            business_status = str(row.get("BusinessStatus", "") or "").strip()
            operating_status = "operating" if business_status not in DEAD_STATUSES else "closed"

            if dry_run:
                stats["new"] += 1
                continue

            # Check for existing by domain first, then name
            existing = None
            if domain and domain.lower() in existing_domains:
                existing = db.query(Company).filter(
                    Company.domain == domain
                ).first()
            elif norm and norm.lower() in existing_norm_names:
                existing = db.query(Company).get(existing_norm_names[norm.lower()])

            if existing:
                # Enrich — fill gaps only, don't overwrite richer data
                changed = False
                if not existing.country and country_code:
                    existing.country = country_code
                    existing.location_source = LocationSource.pitchbook
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
                    existing.verification_status = VerificationStatus.verified_pb
                    changed = True
                if changed:
                    existing.updated_at = now
                    stats["updated"] += 1
                else:
                    stats["skipped_domain_conflict"] += 1
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
                    verification_status=VerificationStatus.verified_pb,
                    location_source=LocationSource.pitchbook if country_code else None,
                    first_seen_at=now,
                    last_seen_at=now,
                    created_at=now,
                    updated_at=now,
                )
                db.add(company)
                # Update local dedup sets
                if domain:
                    existing_domains.add(domain.lower())
                if norm:
                    existing_norm_names[norm.lower()] = -1  # placeholder id
                stats["new"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(description="Import PitchBook companies into the DB")
    parser.add_argument("--company", required=True, help="Path to pitchbook company parquet")
    parser.add_argument(
        "--countries", nargs="+", default=DEFAULT_COUNTRIES,
        help=f"HQCountry values to import (default: {DEFAULT_COUNTRIES})",
    )
    parser.add_argument("--min-founded", type=int, default=2010, help="Min founding year (default: 2010)")
    parser.add_argument("--all-sectors", action="store_true", help="Skip IT sector filter")
    parser.add_argument("--min-ai-score", type=float, default=0.1, help="Min AI score to import (default: 0.1)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    parser.add_argument("--init-db", action="store_true", help="Create DB tables before running")
    args = parser.parse_args()

    if args.init_db:
        init_db()

    if not os.path.exists(args.company):
        logger.error(f"File not found: {args.company}")
        sys.exit(1)

    df = load_and_filter(
        path=args.company,
        countries=args.countries,
        min_founded=args.min_founded,
        it_only=not args.all_sectors,
        min_ai_score=args.min_ai_score,
    )

    if df.empty:
        logger.warning("No companies passed filters — nothing to import.")
        return

    # Preview sample
    logger.info(f"\n── Sample companies ──")
    sample = df.nlargest(10, "_ai_score")[["CompanyName", "HQCountry", "HQCity", "_ai_score", "Description"]]
    for _, r in sample.iterrows():
        logger.info(f"  [{r['HQCountry']}] {r['CompanyName']} (ai={r['_ai_score']:.2f}): {str(r['Description'])[:100]}")

    if args.dry_run:
        logger.info(f"\n── Dry-run summary ──")
        logger.info(f"  Would import: {len(df):,} companies")
        by_country = df["HQCountry"].value_counts()
        for country, count in by_country.items():
            logger.info(f"    {country}: {count:,}")
        ai_buckets = pd.cut(df["_ai_score"], bins=[0, 0.1, 0.2, 0.3, 0.5, 1.0])
        logger.info(f"\n  AI score distribution:")
        for bucket, count in df["_ai_score"].value_counts(bins=[0, 0.1, 0.2, 0.3, 0.5, 1.0]).sort_index().items():
            logger.info(f"    {bucket}: {count:,}")
        return

    logger.info(f"\nImporting {len(df):,} companies...")
    stats = import_companies(df, dry_run=False)

    logger.info("=" * 55)
    logger.info("PitchBook Company Import Complete!")
    logger.info(f"  New companies:     {stats['new']:,}")
    logger.info(f"  Updated existing:  {stats['updated']:,}")
    logger.info(f"  Skipped (no change): {stats['skipped_domain_conflict']:,}")
    logger.info("=" * 55)


if __name__ == "__main__":
    main()
