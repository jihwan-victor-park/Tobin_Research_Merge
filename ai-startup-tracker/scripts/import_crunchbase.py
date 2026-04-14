#!/usr/bin/env python3
"""
Crunchbase Import & Matching Script
=====================================
Load organizations.parquet + category_groups.parquet,
compute AI flag, match to existing companies by domain.

Usage:
    python scripts/import_crunchbase.py \
        --path data/organizations.parquet \
        --categories data/category_groups.parquet
"""
import argparse
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Set

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.db.connection import session_scope, init_db
from backend.db.models import (
    Company, SourceMatch, VerificationStatus, LocationSource, MatchMethod,
)
from backend.utils.domain import canonicalize_domain
from backend.utils.normalize import normalize_company_name
from backend.utils.scoring import compute_ai_score, compute_startup_score

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("import_crunchbase")


# ── AI category detection ──────────────────────────────────────────────

AI_CATEGORY_KEYWORDS = {
    "artificial intelligence", "machine learning", "deep learning",
    "computer vision", "natural language processing", "nlp",
    "generative ai", "neural network", "robotics", "autonomous",
    "speech recognition", "image recognition", "data science",
    "predictive analytics", "intelligent systems",
}

AI_DESCRIPTION_KEYWORDS = [
    "machine learning", "deep learning", "artificial intelligence",
    "neural network", "llm", "large language model", "computer vision",
    "nlp", "natural language", "generative ai", "transformer",
    "inference", "fine-tuning", "reinforcement learning",
]


def compute_cb_ai_flag(categories: str, description: str) -> bool:
    """Determine if a Crunchbase org is AI-related."""
    # Check categories
    if categories:
        cats_lower = categories.lower()
        for kw in AI_CATEGORY_KEYWORDS:
            if kw in cats_lower:
                return True

    # Check description
    if description:
        desc_lower = description.lower()
        match_count = sum(1 for kw in AI_DESCRIPTION_KEYWORDS if kw in desc_lower)
        if match_count >= 2:
            return True

    return False


# ── Parquet loading ────────────────────────────────────────────────────

def load_organizations(path: str) -> pd.DataFrame:
    """Load organizations.parquet and inspect columns."""
    logger.info(f"Loading organizations from {path}")
    df = pd.read_parquet(path)
    logger.info(f"  Rows: {len(df)}, Columns: {list(df.columns)}")
    return df


def load_category_groups(path: str) -> pd.DataFrame:
    """Load category_groups.parquet."""
    logger.info(f"Loading category_groups from {path}")
    df = pd.read_parquet(path)
    logger.info(f"  Rows: {len(df)}, Columns: {list(df.columns)}")
    return df


def detect_column(df: pd.DataFrame, candidates: List[str], fallback: Optional[str] = None) -> Optional[str]:
    """Find the first matching column name from a list of candidates."""
    cols_lower = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in cols_lower:
            return cols_lower[c.lower()]
    return fallback


# ── Main import logic ──────────────────────────────────────────────────

def import_crunchbase(orgs_path: str, cats_path: Optional[str] = None) -> Dict[str, int]:
    """
    Import Crunchbase data and match to existing companies.

    Returns stats dict.
    """
    stats = {"total_orgs": 0, "ai_orgs": 0, "matched": 0, "unmatched_ai": 0}

    # Load data
    orgs_df = load_organizations(orgs_path)
    stats["total_orgs"] = len(orgs_df)

    # Load category groups if provided (for category enrichment)
    cat_group_lookup: Dict[str, str] = {}
    if cats_path and os.path.exists(cats_path):
        cats_df = load_category_groups(cats_path)
        # Build lookup: try to map category UUID/name to group
        cat_name_col = detect_column(cats_df, ["name", "category_name", "group_name"])
        if cat_name_col:
            for _, row in cats_df.iterrows():
                cat_group_lookup[str(row.get(cat_name_col, "")).lower()] = str(row.get(cat_name_col, ""))

    # Detect column names in organizations
    col_name = detect_column(orgs_df, ["name", "company_name", "organization_name", "cb_name"])
    col_domain = detect_column(orgs_df, [
        "domain", "homepage_url", "homepage_domain", "cb_url", "website_url", "website",
    ])
    col_desc = detect_column(orgs_df, [
        "short_description", "description", "cb_description",
    ])
    col_country = detect_column(orgs_df, ["country_code", "country", "headquarters_country"])
    col_city = detect_column(orgs_df, ["city", "headquarters_city"])
    col_categories = detect_column(orgs_df, [
        "category_list", "categories", "category_groups_list", "category_names",
    ])
    col_uuid = detect_column(orgs_df, ["uuid", "cb_uuid", "organization_id", "id"])
    col_founded = detect_column(orgs_df, ["founded_on", "founded_date", "founded_year"])

    logger.info(f"Column mapping: name={col_name}, domain={col_domain}, desc={col_desc}")
    logger.info(f"  country={col_country}, city={col_city}, cats={col_categories}, uuid={col_uuid}")

    if not col_name:
        logger.error("Cannot find 'name' column in organizations.parquet. Aborting.")
        return stats

    # Process each organization
    with session_scope() as session:
        # Pre-load existing companies indexed by domain for fast lookup
        existing_by_domain: Dict[str, Company] = {}
        for company in session.query(Company).filter(Company.domain.isnot(None)).all():
            if company.domain:
                existing_by_domain[company.domain.lower()] = company

        for idx, row in orgs_df.iterrows():
            name = str(row.get(col_name, "")).strip() if col_name else ""
            if not name:
                continue

            domain_raw = str(row.get(col_domain, "")).strip() if col_domain else ""
            description = str(row.get(col_desc, "")).strip() if col_desc else ""
            categories = str(row.get(col_categories, "")).strip() if col_categories else ""
            country = str(row.get(col_country, "")).strip() if col_country else ""
            city = str(row.get(col_city, "")).strip() if col_city else ""
            cb_uuid = str(row.get(col_uuid, "")).strip() if col_uuid else ""

            # Clean NaN values
            for var_name in ["domain_raw", "description", "categories", "country", "city", "cb_uuid"]:
                val = locals()[var_name]
                if val == "nan" or val == "None" or val == "NaN":
                    locals()[var_name] = ""
            # Re-assign after cleaning
            domain_raw = "" if domain_raw in ("nan", "None", "NaN") else domain_raw
            description = "" if description in ("nan", "None", "NaN") else description
            categories = "" if categories in ("nan", "None", "NaN") else categories
            country = "" if country in ("nan", "None", "NaN") else country
            city = "" if city in ("nan", "None", "NaN") else city
            cb_uuid = "" if cb_uuid in ("nan", "None", "NaN") else cb_uuid

            # Compute AI flag
            ai_flag = compute_cb_ai_flag(categories, description)
            if not ai_flag:
                continue  # Only process AI-related orgs

            stats["ai_orgs"] += 1

            # Canonicalize domain
            canon_domain = canonicalize_domain(domain_raw) if domain_raw else None

            # Try to match to existing company
            matched_company = None
            if canon_domain and canon_domain.lower() in existing_by_domain:
                matched_company = existing_by_domain[canon_domain.lower()]

            if matched_company:
                stats["matched"] += 1

                # Update verification status
                if matched_company.verification_status == VerificationStatus.verified_pb:
                    matched_company.verification_status = VerificationStatus.verified_cb_pb
                elif matched_company.verification_status == VerificationStatus.emerging_github:
                    matched_company.verification_status = VerificationStatus.verified_cb

                # Fill location from CB if empty
                if country and not matched_company.country:
                    matched_company.country = country
                    matched_company.location_source = LocationSource.crunchbase
                if city and not matched_company.city:
                    matched_company.city = city

                # Update scores
                ai_score = compute_ai_score(
                    topics=matched_company.ai_tags,
                    description=description,
                    cb_ai_flag=True,
                )
                startup_score = compute_startup_score(
                    domain=matched_company.domain,
                    description=description,
                    has_cb_record=True,
                )
                if ai_score > (matched_company.ai_score or 0):
                    matched_company.ai_score = ai_score
                if startup_score > (matched_company.startup_score or 0):
                    matched_company.startup_score = startup_score

                matched_company.updated_at = datetime.utcnow()

                # Record source match (avoid duplicates)
                existing_match = session.query(SourceMatch).filter(
                    SourceMatch.company_id == matched_company.id,
                    SourceMatch.crunchbase_id == cb_uuid,
                ).first()
                if not existing_match:
                    sm = SourceMatch(
                        company_id=matched_company.id,
                        crunchbase_id=cb_uuid if cb_uuid else None,
                        match_method=MatchMethod.domain,
                        match_confidence=1.0,
                    )
                    session.add(sm)
            else:
                stats["unmatched_ai"] += 1

    return stats


# ── CLI ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Import Crunchbase organizations and match to companies")
    parser.add_argument("--path", required=True, help="Path to organizations.parquet")
    parser.add_argument("--categories", default=None, help="Path to category_groups.parquet")
    parser.add_argument("--init-db", action="store_true", help="Create DB tables before running")
    args = parser.parse_args()

    if args.init_db:
        init_db()

    if not os.path.exists(args.path):
        logger.error(f"File not found: {args.path}")
        sys.exit(1)

    logger.info("Starting Crunchbase import...")
    stats = import_crunchbase(args.path, args.categories)

    logger.info("=" * 60)
    logger.info("Crunchbase Import Complete!")
    logger.info(f"  Total orgs in parquet:  {stats['total_orgs']}")
    logger.info(f"  AI-related orgs:        {stats['ai_orgs']}")
    logger.info(f"  Matched to companies:   {stats['matched']}")
    logger.info(f"  Unmatched AI orgs:      {stats['unmatched_ai']}")
    logger.info("=" * 60)

    return stats


if __name__ == "__main__":
    main()
