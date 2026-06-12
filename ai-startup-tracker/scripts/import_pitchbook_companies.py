#!/usr/bin/env python3
"""
PitchBook Company Import
========================
Imports companies from the PitchBook global company parquet into the DB.

Unlike import_pitchbook.py (which matches *deals* to existing companies),
this script creates new Company records from the PitchBook company file —
seeding the DB with international startups that no other source covers.

Also captures deal data (last + first financing) into FundingSignal and
enriches Company with team_size, total_raised, and stage.

Filter chain:
  1. Target countries (default: all supported)
  2. Active business status (drops Out of Business / Bankruptcy)
  3. Founded >= --min-founded (default: 2000)
  4. IT sector (or --all-sectors to skip)
  5. ai_score >= --min-ai-score (default: 0.0; computed from description/keywords)

Usage:
    python scripts/import_pitchbook_companies.py --company ~/Downloads/pitchbook_other_glob_company.parquet --dry-run
    python scripts/import_pitchbook_companies.py --company ~/Downloads/pitchbook_other_glob_company.parquet --all-sectors --min-ai-score 0.0
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.db.connection import session_scope, init_db
from backend.db.models import Company, FundingSignal, VerificationStatus, LocationSource
from backend.utils.domain import canonicalize_domain
from backend.utils.normalize import normalize_company_name
from backend.utils.scoring import compute_ai_score

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("import_pb_companies")

DEAD_STATUSES = {
    "Out of Business",
    "Bankruptcy: Liquidation",
    "Bankruptcy: Admin/Reorg",
}

# PitchBook full country names → canonical full names matching CB convention
COUNTRY_MAP = {
    "south korea": "South Korea", "korea, republic of": "South Korea",
    "israel": "Israel", "israel (state of)": "Israel",
    "china": "China", "china, people's republic of": "China",
    "united states": "United States", "usa": "United States",
    "united kingdom": "United Kingdom", "england": "United Kingdom",
    "germany": "Germany", "france": "France", "india": "India",
    "canada": "Canada", "japan": "Japan", "australia": "Australia",
    "brazil": "Brazil", "singapore": "Singapore", "netherlands": "Netherlands",
    "sweden": "Sweden", "switzerland": "Switzerland", "spain": "Spain",
    "italy": "Italy", "ireland": "Ireland", "denmark": "Denmark",
    "norway": "Norway", "finland": "Finland", "belgium": "Belgium",
    "austria": "Austria", "poland": "Poland", "portugal": "Portugal",
    "hong kong": "Hong Kong", "taiwan": "Taiwan",
    "uae": "United Arab Emirates", "united arab emirates": "United Arab Emirates",
    "russia": "Russia", "turkey": "Turkey", "ukraine": "Ukraine",
    "mexico": "Mexico", "argentina": "Argentina", "colombia": "Colombia",
    "chile": "Chile", "nigeria": "Nigeria", "south africa": "South Africa",
    "kenya": "Kenya", "egypt": "Egypt", "indonesia": "Indonesia",
    "malaysia": "Malaysia", "thailand": "Thailand", "vietnam": "Vietnam",
    "philippines": "Philippines", "new zealand": "New Zealand",
    "estonia": "Estonia", "latvia": "Latvia", "lithuania": "Lithuania",
    "czech republic": "Czech Republic", "czechia": "Czech Republic",
    "hungary": "Hungary", "romania": "Romania", "greece": "Greece",
    "bulgaria": "Bulgaria", "croatia": "Croatia", "serbia": "Serbia",
    "saudi arabia": "Saudi Arabia", "qatar": "Qatar", "kuwait": "Kuwait",
    "pakistan": "Pakistan", "bangladesh": "Bangladesh",
    "peru": "Peru", "uruguay": "Uruguay", "ecuador": "Ecuador",
    "bolivia": "Bolivia", "panama": "Panama", "ghana": "Ghana",
    "ethiopia": "Ethiopia", "tanzania": "Tanzania", "uganda": "Uganda",
    "zambia": "Zambia", "cameroon": "Cameroon", "senegal": "Senegal",
    "kazakhstan": "Kazakhstan", "uzbekistan": "Uzbekistan",
    "azerbaijan": "Azerbaijan", "georgia": "Georgia", "armenia": "Armenia",
    "luxembourg": "Luxembourg", "iceland": "Iceland", "slovenia": "Slovenia",
    "slovak republic": "Slovakia", "slovakia": "Slovakia",
    "north macedonia": "North Macedonia", "montenegro": "Montenegro",
    "jordan": "Jordan", "lebanon": "Lebanon", "morocco": "Morocco",
    "algeria": "Algeria", "mongolia": "Mongolia",
    "sri lanka": "Sri Lanka", "nepal": "Nepal",
    "myanmar": "Myanmar", "cambodia": "Cambodia",
}

DEFAULT_COUNTRIES = list(COUNTRY_MAP.values())

# PitchBook deal type → canonical stage value
DEAL_TYPE_TO_STAGE = {
    "Seed Round": "seed",
    "Angel (individual)": "angel",
    "Convertible Debt": "seed",
    "Equity Crowdfunding": "seed",
    "Early Stage VC": "seed",
    "Accelerator/Incubator": "pre-seed",
    "Later Stage VC": "growth",
    "PE Growth/Expansion": "growth",
    "Grant": "grant",
    "IPO": "ipo",
    "PIPE": "public",
}

# Deal types that are not meaningful for stage/funding research
_SKIP_DEAL_TYPES = {
    "Merger/Acquisition", "Corporate Asset Purchase", "Corporate Divestiture",
    "Buyout/LBO", "Merger of Equals", "Out of Business",
    "Bankruptcy: Liquidation", "Bankruptcy: Admin/Reorg",
    "Secondary Transaction - Private", "Debt - Acquisition",
    "Debt - PPP", "Debt Refinancing",
}


def to_country(raw: str) -> Optional[str]:
    return COUNTRY_MAP.get(raw.lower().strip())


def _parse_deal_size_usd(val) -> Optional[float]:
    """PitchBook sizes are in millions USD."""
    if pd.isna(val) or val is None:
        return None
    try:
        return float(val) * 1_000_000
    except (TypeError, ValueError):
        return None


def _parse_date(val) -> Optional[datetime]:
    if pd.isna(val) or val is None:
        return None
    try:
        return pd.Timestamp(val).to_pydatetime()
    except Exception:
        return None


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

    # Country filter — match on canonical name
    country_set = set(countries)
    df = df.copy()
    df["_country"] = df["HQCountry"].apply(lambda x: to_country(str(x or "")))
    df = df[df["_country"].isin(country_set)]
    logger.info(f"  After country filter: {len(df):,}")

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

    # AI score
    def _score(row) -> float:
        text = " ".join(filter(None, [
            str(row.get("Description", "") or ""),
            str(row.get("Keywords", "") or ""),
        ]))
        return compute_ai_score(description=text)

    logger.info("  Computing AI scores...")
    df["_ai_score"] = df.apply(_score, axis=1)
    df = df[df["_ai_score"] >= min_ai_score]
    logger.info(f"  After ai_score >= {min_ai_score}: {len(df):,}")

    return df


def _make_funding_signal(company_id: int, deal_type: str, deal_date, deal_size_raw, now: datetime) -> Optional[FundingSignal]:
    """Build a FundingSignal from PB deal fields. Returns None if deal is not meaningful."""
    if not deal_type or deal_type in _SKIP_DEAL_TYPES:
        return None
    dt = _parse_date(deal_date)
    size = _parse_deal_size_usd(deal_size_raw)
    return FundingSignal(
        company_id=company_id,
        source="pitchbook",
        deal_date=dt,
        round_type=deal_type,
        deal_size=size,
        investors=None,
        raw_metadata=None,
        collected_at=now,
    )


def import_companies(df: pd.DataFrame, dry_run: bool) -> Dict[str, int]:
    stats = {"new": 0, "updated": 0, "skipped": 0, "funding_signals": 0}
    now = datetime.now(timezone.utc)

    if dry_run:
        stats["new"] = len(df)
        return stats

    with session_scope() as db:
        # Preload existing domains + normalized names for dedup
        existing_domains: Dict[str, int] = {}  # domain → company_id
        existing_norm_names: Dict[str, int] = {}  # norm_name → company_id
        # Also preload existing funding signals for dedup
        existing_signals: Set[Tuple[int, str, Optional[datetime]]] = set()

        for c in db.query(Company.id, Company.domain, Company.normalized_name).all():
            if c.domain:
                existing_domains[c.domain.lower()] = c.id
            if c.normalized_name:
                existing_norm_names[c.normalized_name.lower()] = c.id

        for fs in db.query(FundingSignal.company_id, FundingSignal.round_type, FundingSignal.deal_date)\
                     .filter(FundingSignal.source == "pitchbook").all():
            existing_signals.add((fs.company_id, fs.round_type or "", str(fs.deal_date)))

        total = len(df)
        log_every = max(1, total // 20)

        for i, (_, row) in enumerate(df.iterrows()):
            if i % log_every == 0:
                logger.info(f"  Progress: {i:,}/{total:,}")

            name = str(row.get("CompanyName", "") or "").strip()
            if not name:
                continue

            domain = canonicalize_domain(str(row.get("Website", "") or "")) or None
            norm = normalize_company_name(name)
            country = row.get("_country")
            city = str(row.get("HQCity", "") or "").strip() or None
            description = str(row.get("Description", "") or "").strip() or None
            ai_score = float(row["_ai_score"])

            founded_raw = row.get("YearFounded")
            founded_year = int(founded_raw) if pd.notna(founded_raw) else None

            business_status = str(row.get("BusinessStatus", "") or "").strip()
            operating_status = "operating" if business_status not in DEAD_STATUSES else "closed"

            employees_raw = row.get("Employees")
            team_size = int(employees_raw) if pd.notna(employees_raw) else None

            total_raised_raw = row.get("TotalRaised")
            total_raised = _parse_deal_size_usd(total_raised_raw)

            last_deal_type = str(row.get("LastFinancingDealType", "") or "").strip() or None
            last_deal_date = row.get("LastFinancingDate")
            last_deal_size = row.get("LastFinancingSize")
            first_deal_type = str(row.get("FirstFinancingDealType", "") or "").strip() or None
            first_deal_date = row.get("FirstFinancingDate")
            first_deal_size = row.get("FirstFinancingSize")
            stage = DEAL_TYPE_TO_STAGE.get(last_deal_type or "") or None

            # Find existing company
            existing = None
            existing_id = None
            if domain and domain.lower() in existing_domains:
                existing_id = existing_domains[domain.lower()]
                existing = db.query(Company).get(existing_id)
            elif norm and norm.lower() in existing_norm_names:
                existing_id = existing_norm_names[norm.lower()]
                existing = db.query(Company).get(existing_id)

            if existing:
                changed = False
                if not existing.country and country:
                    existing.country = country
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
                if not existing.team_size and team_size:
                    existing.team_size = team_size
                    changed = True
                if not existing.total_raised and total_raised:
                    existing.total_raised = total_raised
                    changed = True
                if not existing.stage and stage:
                    existing.stage = stage
                    changed = True
                if existing.verification_status == VerificationStatus.emerging_github:
                    existing.verification_status = VerificationStatus.verified_pb
                    changed = True
                if changed:
                    existing.updated_at = now
                    stats["updated"] += 1
                else:
                    stats["skipped"] += 1
                company_id = existing.id
            else:
                company = Company(
                    name=name,
                    domain=domain,
                    normalized_name=norm,
                    country=country,
                    city=city,
                    description=description,
                    founded_year=founded_year,
                    operating_status=operating_status,
                    ai_score=ai_score,
                    team_size=team_size,
                    total_raised=total_raised,
                    stage=stage,
                    verification_status=VerificationStatus.verified_pb,
                    location_source=LocationSource.pitchbook if country else None,
                    first_seen_at=now,
                    last_seen_at=now,
                    created_at=now,
                    updated_at=now,
                )
                db.add(company)
                db.flush()  # get company.id before FundingSignal insert
                company_id = company.id
                if domain:
                    existing_domains[domain.lower()] = company_id
                if norm:
                    existing_norm_names[norm.lower()] = company_id
                stats["new"] += 1

            # Add FundingSignal(s) for this company
            for deal_type, deal_date, deal_size in [
                (last_deal_type, last_deal_date, last_deal_size),
                (first_deal_type, first_deal_date, first_deal_size),
            ]:
                if not deal_type or deal_type in _SKIP_DEAL_TYPES:
                    continue
                sig_key = (company_id, deal_type, str(_parse_date(deal_date)))
                if sig_key in existing_signals:
                    continue
                # Skip first financing if same date as last (avoid duplicate)
                if deal_date == last_deal_date and deal_type == last_deal_type and deal_date != row.get("FirstFinancingDate"):
                    continue
                fs = _make_funding_signal(company_id, deal_type, deal_date, deal_size, now)
                if fs:
                    db.add(fs)
                    existing_signals.add(sig_key)
                    stats["funding_signals"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(description="Import PitchBook companies into the DB")
    parser.add_argument("--company", required=True, help="Path to pitchbook company parquet")
    parser.add_argument(
        "--countries", nargs="+", default=DEFAULT_COUNTRIES,
        help="HQCountry values to import (default: all supported)",
    )
    parser.add_argument("--min-founded", type=int, default=2000, help="Min founding year (default: 2000)")
    parser.add_argument("--all-sectors", action="store_true", help="Skip IT sector filter")
    parser.add_argument("--min-ai-score", type=float, default=0.0, help="Min AI score (default: 0.0)")
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

    logger.info(f"\n── Sample (top 10 by AI score) ──")
    for _, r in df.nlargest(10, "_ai_score").iterrows():
        logger.info(f"  [{r['_country']}] {r['CompanyName']} (ai={r['_ai_score']:.2f}): {str(r['Description'])[:100]}")

    if args.dry_run:
        logger.info(f"\n── Dry-run summary ──")
        logger.info(f"  Would import: {len(df):,} companies")
        for country, count in df["_country"].value_counts().items():
            logger.info(f"    {country}: {count:,}")
        logger.info(f"\n  Deals available (last financing non-null):")
        logger.info(f"    LastFinancingDate set: {df['LastFinancingDate'].notna().sum():,}")
        logger.info(f"    TotalRaised set:       {df['TotalRaised'].notna().sum():,}")
        return

    logger.info(f"\nImporting {len(df):,} companies...")
    stats = import_companies(df, dry_run=False)

    logger.info("=" * 55)
    logger.info("PitchBook Company Import Complete!")
    logger.info(f"  New companies:      {stats['new']:,}")
    logger.info(f"  Updated existing:   {stats['updated']:,}")
    logger.info(f"  Skipped (no change): {stats['skipped']:,}")
    logger.info(f"  FundingSignals added: {stats['funding_signals']:,}")
    logger.info("=" * 55)


if __name__ == "__main__":
    main()
