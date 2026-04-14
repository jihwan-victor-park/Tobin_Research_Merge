#!/usr/bin/env python3
"""
PitchBook Import & Matching Script (FAST VERSION)
=================================================
Key speedups:
- Avoid rel_df.iterrows(): vectorized groupby to build investors_by_deal
- Avoid per-deal DB existence queries: preload existing FundingSignal + SourceMatch keys into sets
- Use itertuples() (much faster than iterrows())
- Bulk insert FundingSignal/SourceMatch in batches
- Reduce fuzzy-match work by bucketing candidates

Usage:
    python scripts/import_pitchbook.py \
        --deal data/deal.parquet \
        --relation data/deal_investor_relation.parquet
"""
import argparse
import logging
import os
import sys
from datetime import datetime, UTC
from typing import Dict, List, Optional, Tuple, Iterable

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.db.connection import session_scope, init_db
from backend.db.models import (
    Company, FundingSignal, SourceMatch,
    VerificationStatus, MatchMethod, LocationSource,
)
from backend.utils.domain import canonicalize_domain
from backend.utils.normalize import normalize_company_name, fuzzy_name_match
from backend.utils.scoring import compute_startup_score

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("import_pitchbook")

PB_NAME_MATCH_THRESHOLD = 0.95
BATCH_SIZE = 5000  # tune: 2k~20k depending on RAM


# ── Column detection ───────────────────────────────────────────────────

def detect_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    cols_lower = {c.lower(): c for c in df.columns}
    for c in candidates:
        key = c.lower()
        if key in cols_lower:
            return cols_lower[key]
    return None


def clean_str_series(s: pd.Series) -> pd.Series:
    # convert to string, strip, turn "nan" into ""
    s = s.astype("string")
    s = s.fillna("")
    s = s.str.strip()
    return s


# ── Location parsing ──────────────────────────────────────────────────

COUNTRY_ALIASES = {
    "usa": "US", "us": "US", "united states": "US", "united states of america": "US",
    "uk": "GB", "united kingdom": "GB", "england": "GB", "scotland": "GB", "wales": "GB",
    "germany": "DE", "deutschland": "DE", "france": "FR", "india": "IN", "china": "CN",
    "canada": "CA", "japan": "JP", "south korea": "KR", "korea": "KR",
    "australia": "AU", "brazil": "BR", "israel": "IL",
    "singapore": "SG", "netherlands": "NL", "holland": "NL",
    "sweden": "SE", "switzerland": "CH", "spain": "ES",
    "italy": "IT", "ireland": "IE", "portugal": "PT",
    "poland": "PL", "austria": "AT", "belgium": "BE",
    "norway": "NO", "finland": "FI", "denmark": "DK",
    "czech republic": "CZ", "czechia": "CZ",
    "new zealand": "NZ", "mexico": "MX",
    "indonesia": "ID", "thailand": "TH", "vietnam": "VN",
    "taiwan": "TW", "hong kong": "HK", "uae": "AE",
    "united arab emirates": "AE", "russia": "RU",
    "turkey": "TR", "ukraine": "UA", "romania": "RO",
    "argentina": "AR", "colombia": "CO", "chile": "CL",
    "nigeria": "NG", "south africa": "ZA", "kenya": "KE",
    "egypt": "EG", "pakistan": "PK", "bangladesh": "BD",
    "philippines": "PH", "malaysia": "MY", "estonia": "EE",
    "luxembourg": "LU", "hungary": "HU", "greece": "GR",
    "croatia": "HR", "serbia": "RS", "bulgaria": "BG",
    "peru": "PE", "saudi arabia": "SA", "qatar": "QA",
    "bahrain": "BH", "kuwait": "KW", "oman": "OM",
    "sri lanka": "LK", "nepal": "NP", "myanmar": "MM",
    "cambodia": "KH", "laos": "LA",
}


def parse_pitchbook_location(location_str: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse PitchBook SiteLocation like 'Paris, France' -> (country_code, city)."""
    if not location_str or location_str.lower() in ("", "nan", "none"):
        return None, None

    parts = [p.strip() for p in location_str.split(",")]

    if len(parts) >= 2:
        city = parts[0]
        last_part = parts[-1].strip().lower()

        if last_part in COUNTRY_ALIASES:
            return COUNTRY_ALIASES[last_part], city

        # If last part is a 2-letter code, use it directly
        if len(last_part) == 2 and last_part.isalpha():
            return last_part.upper(), city

        # Return raw country name
        return parts[-1].strip(), city

    # Single value — check if it's a known country
    single = location_str.lower().strip()
    if single in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[single], None

    return None, location_str.strip()


# ── Main import logic ──────────────────────────────────────────────────

def import_pitchbook(deal_path: str, relation_path: Optional[str] = None) -> Dict[str, int]:
    stats = {
        "total_deals": 0,
        "matched_by_domain": 0,
        "matched_by_name": 0,
        "unmatched": 0,
        "funding_signals_created": 0,
        "locations_updated": 0,
    }

    logger.info(f"Loading deals from {deal_path}")
    deals_df = pd.read_parquet(deal_path)
    logger.info(f"  Rows: {len(deals_df)}, Columns: {list(deals_df.columns)}")
    stats["total_deals"] = len(deals_df)

    # Load investor relations (FAST)
    investors_by_deal: Dict[str, List[str]] = {}
    if relation_path and os.path.exists(relation_path):
        logger.info(f"Loading investor relations from {relation_path}")
        rel_df = pd.read_parquet(relation_path)
        logger.info(f"  Rows: {len(rel_df)}, Columns: {list(rel_df.columns)}")

        rel_deal_col = detect_column(rel_df, ["deal_id", "dealid", "deal_number", "deal_identifier"])
        rel_investor_col = detect_column(rel_df, ["investor_name", "investor", "investorname", "investor_company_name"])

        if rel_deal_col and rel_investor_col:
            tmp = rel_df[[rel_deal_col, rel_investor_col]].copy()
            tmp[rel_deal_col] = clean_str_series(tmp[rel_deal_col])
            tmp[rel_investor_col] = clean_str_series(tmp[rel_investor_col])
            tmp = tmp[(tmp[rel_deal_col] != "") & (tmp[rel_investor_col] != "")]
            # keep only first 5 investors per deal (preserving file order)
            tmp["_rn"] = tmp.groupby(rel_deal_col).cumcount()
            tmp = tmp[tmp["_rn"] < 5].drop(columns=["_rn"])

            investors_by_deal = (
                tmp.groupby(rel_deal_col)[rel_investor_col]
                .apply(list)
                .to_dict()
            )
            logger.info(f"  Loaded investors for {len(investors_by_deal)} deals")

    # Detect deal columns
    col_deal_id = detect_column(deals_df, ["deal_id", "dealid", "deal_number", "id"])
    col_company_name = detect_column(deals_df, [
        "company_name", "companyname", "company", "target_company",
        "target_company_name", "portfolio_company_name",
    ])
    col_company_domain = detect_column(deals_df, ["company_domain", "company_website", "website", "domain", "company_url"])
    col_deal_date = detect_column(deals_df, ["deal_date", "dealdate", "close_date", "announced_date", "date"])
    col_deal_size = detect_column(deals_df, ["deal_size", "dealsize", "deal_size_usd", "amount", "deal_amount", "deal_size_m_usd", "size_m"])
    col_round_type = detect_column(deals_df, ["deal_type", "dealtype", "round", "round_type", "stage", "deal_type_1", "financing_type"])
    col_country = detect_column(deals_df, [
        "company_country", "country", "hq_country", "company_hq_country",
        "sitelocation", "site_location", "headquarterslocation",
    ])
    col_pb_id = detect_column(deals_df, ["company_id", "companyid", "pitchbook_id", "pb_id", "target_company_id"])

    logger.info(f"Column mapping: company_name={col_company_name}, domain={col_company_domain}")
    logger.info(f"  deal_date={col_deal_date}, size={col_deal_size}, round={col_round_type}")

    if not col_company_name:
        logger.error("Cannot find company_name column. Aborting.")
        return stats

    # Keep only needed columns in-memory to speed tuple iteration
    needed_cols = [c for c in [col_deal_id, col_company_name, col_company_domain, col_deal_date, col_deal_size,
                              col_round_type, col_pb_id, col_country] if c]
    deals_df = deals_df[needed_cols].copy()

    # Pre-clean a few hot columns (strings)
    for c in [col_deal_id, col_company_name, col_company_domain, col_round_type, col_pb_id, col_country]:
        if c and c in deals_df.columns:
            deals_df[c] = clean_str_series(deals_df[c])

    # Prepare index positions for itertuples (fast)
    col_positions = {c: i for i, c in enumerate(deals_df.columns)}

    def get_val(t: Tuple, col: Optional[str]):
        if not col:
            return ""
        return t[col_positions[col]]

    with session_scope() as session:
        # Preload companies (domain/name maps)
        existing_by_domain: Dict[str, Company] = {}
        existing_by_norm_name: Dict[str, Company] = {}
        buckets: Dict[str, List[Company]] = {}

        # This is one DB query (fine)
        for company in session.query(Company).all():
            if company.domain:
                existing_by_domain[company.domain.lower()] = company
            if company.normalized_name:
                key = company.normalized_name.lower()
                existing_by_norm_name[key] = company
                # bucket by first character to cut fuzzy comparisons drastically
                b = key[:1]
                buckets.setdefault(b, []).append(company)

        # Preload existing pitchbook FundingSignals + SourceMatches (avoid 1.3M * DB queries)
        logger.info("Preloading existing PitchBook FundingSignal keys...")
        existing_fs_keys = set()
        q_fs = (
            session.query(FundingSignal.company_id, FundingSignal.deal_date, FundingSignal.round_type)
            .filter(FundingSignal.source == "pitchbook")
        )
        for cid, ddate, rtype in q_fs.yield_per(50000):
            existing_fs_keys.add((cid, ddate, rtype or ""))

        logger.info("Preloading existing SourceMatch keys...")
        existing_sm_keys = set()
        q_sm = session.query(SourceMatch.company_id, SourceMatch.pitchbook_id)
        for cid, pbid in q_sm.yield_per(50000):
            if pbid:
                existing_sm_keys.add((cid, str(pbid)))

        # Batch buffers for inserts
        fs_buffer: List[FundingSignal] = []
        sm_buffer: List[SourceMatch] = []

        def flush_buffers():
            nonlocal fs_buffer, sm_buffer
            if fs_buffer:
                session.bulk_save_objects(fs_buffer)
                fs_buffer = []
            if sm_buffer:
                session.bulk_save_objects(sm_buffer)
                sm_buffer = []
            session.flush()

        # Iterate deals quickly
        for i, t in enumerate(deals_df.itertuples(index=False, name=None), start=1):
            company_name = get_val(t, col_company_name)
            if not company_name:
                continue

            domain_raw = get_val(t, col_company_domain)
            round_type = get_val(t, col_round_type)
            deal_id = get_val(t, col_deal_id)
            pb_company_id = get_val(t, col_pb_id)
            country = get_val(t, col_country)

            # Dates / sizes can be non-string
            deal_date_raw = t[col_positions[col_deal_date]] if col_deal_date else None
            deal_size_raw = t[col_positions[col_deal_size]] if col_deal_size else None

            # Parse deal date
            deal_date = None
            if col_deal_date and deal_date_raw is not None and not pd.isna(deal_date_raw):
                try:
                    deal_date = pd.Timestamp(deal_date_raw).to_pydatetime()
                except Exception:
                    deal_date = None

            # Parse deal size
            deal_size = None
            if col_deal_size and deal_size_raw is not None and not pd.isna(deal_size_raw):
                try:
                    deal_size = float(deal_size_raw)
                except (ValueError, TypeError):
                    deal_size = None

            # Investors for deal (already limited to 5)
            deal_investors = investors_by_deal.get(deal_id, [])

            matched_company = None
            match_method = None

            # Strategy 1: domain match
            canon_domain = canonicalize_domain(domain_raw) if domain_raw else None
            if canon_domain:
                mc = existing_by_domain.get(canon_domain.lower())
                if mc:
                    matched_company = mc
                    match_method = MatchMethod.domain
                    stats["matched_by_domain"] += 1

            # Strategy 2: name match
            if not matched_company:
                norm_name = normalize_company_name(company_name)
                if norm_name:
                    key = norm_name.lower()
                    mc = existing_by_norm_name.get(key)
                    if mc:
                        matched_company = mc
                        match_method = MatchMethod.name_strict
                        stats["matched_by_name"] += 1
                    else:
                        # fuzzy only within bucket
                        b = key[:1]
                        candidates = buckets.get(b, [])
                        best_score = 0.0
                        best_company = None
                        for comp in candidates:
                            score = fuzzy_name_match(company_name, comp.name)
                            if score >= PB_NAME_MATCH_THRESHOLD and score > best_score:
                                if country and comp.country and country.lower() != comp.country.lower():
                                    continue
                                best_score = score
                                best_company = comp
                        if best_company:
                            matched_company = best_company
                            match_method = MatchMethod.name_strict
                            stats["matched_by_name"] += 1

            if not matched_company:
                stats["unmatched"] += 1
                continue

            # Update verification status
            if matched_company.verification_status == VerificationStatus.verified_cb:
                matched_company.verification_status = VerificationStatus.verified_cb_pb
            elif matched_company.verification_status == VerificationStatus.emerging_github:
                matched_company.verification_status = VerificationStatus.verified_pb

            # Update startup score
            startup_score = compute_startup_score(
                domain=matched_company.domain,
                has_funding=True,
                has_cb_record=(matched_company.verification_status in (
                    VerificationStatus.verified_cb, VerificationStatus.verified_cb_pb
                )),
            )
            if startup_score > (matched_company.startup_score or 0):
                matched_company.startup_score = startup_score

            # Update location from SiteLocation if company has none
            if not matched_company.country and country:
                pb_country, pb_city = parse_pitchbook_location(country)
                if pb_country:
                    matched_company.country = pb_country
                    matched_company.city = pb_city
                    matched_company.location_source = LocationSource.pitchbook
                    stats["locations_updated"] += 1

            matched_company.updated_at = datetime.now(UTC)

            # FundingSignal idempotency via set (NO DB query per row)
            fs_key = (matched_company.id, deal_date, round_type or "")
            if fs_key not in existing_fs_keys:
                fs_buffer.append(FundingSignal(
                    company_id=matched_company.id,
                    source="pitchbook",
                    deal_date=deal_date,
                    round_type=round_type,
                    deal_size=deal_size,
                    investors=deal_investors if deal_investors else None,
                    raw_metadata={
                        "deal_id": deal_id,
                        "pb_company_id": pb_company_id,
                        "company_name": company_name,
                    },
                ))
                existing_fs_keys.add(fs_key)
                stats["funding_signals_created"] += 1

            # SourceMatch idempotency via set
            pitchbook_key = (pb_company_id or deal_id or "")
            if pitchbook_key:
                sm_key = (matched_company.id, str(pitchbook_key))
                if sm_key not in existing_sm_keys:
                    sm_buffer.append(SourceMatch(
                        company_id=matched_company.id,
                        pitchbook_id=str(pitchbook_key),
                        match_method=match_method,
                        match_confidence=1.0 if match_method == MatchMethod.domain else 0.95,
                    ))
                    existing_sm_keys.add(sm_key)

            # Flush periodically to keep memory stable
            if (len(fs_buffer) + len(sm_buffer)) >= BATCH_SIZE:
                flush_buffers()

            # Optional progress log
            if i % 200000 == 0:
                logger.info(f"Processed {i:,} deals... (created FS: {stats['funding_signals_created']:,})")

        # Final flush
        flush_buffers()

    return stats


# ── CLI ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Import PitchBook deals and match to companies (fast)")
    parser.add_argument("--deal", required=True, help="Path to deal.parquet")
    parser.add_argument("--relation", default=None, help="Path to deal_investor_relation.parquet")
    parser.add_argument("--init-db", action="store_true", help="Create DB tables before running")
    args = parser.parse_args()

    if args.init_db:
        init_db()

    if not os.path.exists(args.deal):
        logger.error(f"File not found: {args.deal}")
        sys.exit(1)

    logger.info("Starting PitchBook import (fast)...")
    stats = import_pitchbook(args.deal, args.relation)

    logger.info("=" * 60)
    logger.info("PitchBook Import Complete!")
    logger.info(f"  Total deals:             {stats['total_deals']}")
    logger.info(f"  Matched by domain:       {stats['matched_by_domain']}")
    logger.info(f"  Matched by name:         {stats['matched_by_name']}")
    logger.info(f"  Unmatched:               {stats['unmatched']}")
    logger.info(f"  Funding signals created: {stats['funding_signals_created']}")
    logger.info(f"  Locations updated:       {stats['locations_updated']}")
    logger.info("=" * 60)
    return stats


if __name__ == "__main__":
    main()
