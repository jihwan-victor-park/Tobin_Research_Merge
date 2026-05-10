#!/usr/bin/env python3
"""
Crunchbase Bulk Import (v2)
============================
Import AI-related companies from a Crunchbase data dump and merge them into
our `companies` table. **Critical change vs v1**: previously this script
ONLY updated existing companies on a domain match and silently dropped any
unmatched Crunchbase row. v2 now also INSERTS new AI companies as fresh
`Company` rows (verification_status = verified_cb).

Inputs (any subset):
  data/crunchbase/organizations.parquet              [required]
  data/crunchbase/category_groups.parquet            [optional, for AI tag enrichment]
  data/crunchbase/organization_descriptions.parquet  [optional, long descriptions]
  data/crunchbase/funding_rounds.parquet             [optional, FundingSignal rows]

Default behaviour (no flags):
  - Filters Crunchbase orgs to AI-related ones via category_groups_list
    + category_list keyword match → ~80K rows out of 3.8M.
  - Joins long description from organization_descriptions.parquet when
    available; uses short_description otherwise.
  - For each AI org:
      * If a `companies` row matches by canonical domain: enrich it
        (verification_status, country/city, ai_score, ai_tags, description).
      * Otherwise: INSERT a new `companies` row.
  - Records a SourceMatch per matched / inserted company.

Run:
  # Dry-run estimate first
  python scripts/import_crunchbase.py --dry-run

  # Full import (orgs + descriptions)
  python scripts/import_crunchbase.py

  # Also pull funding rounds
  python scripts/import_crunchbase.py --funding-rounds

  # Custom paths
  python scripts/import_crunchbase.py \\
      --orgs data/crunchbase/organizations.parquet \\
      --descriptions data/crunchbase/organization_descriptions.parquet \\
      --categories data/crunchbase/category_groups.parquet \\
      --funding-rounds-path data/crunchbase/funding_rounds.parquet
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.db.connection import init_db, session_scope  # noqa: E402
from backend.db.models import (  # noqa: E402
    Company,
    FundingSignal,
    LocationSource,
    MatchMethod,
    SourceMatch,
    VerificationStatus,
)
from backend.utils.domain import canonicalize_domain  # noqa: E402
from backend.utils.normalize import normalize_company_name  # noqa: E402

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_DIR / "import_crunchbase.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("import_crunchbase")


DEFAULT_BASE = PROJECT_ROOT / "data" / "crunchbase"


# ── AI filter ──────────────────────────────────────────────────────────
# Crunchbase top-level group "Artificial Intelligence (AI)" is the strongest
# signal; combined with explicit category-list keywords we capture orgs that
# slipped into adjacent groups (e.g. autonomous vehicles → Transportation).

AI_CATEGORY_KEYWORDS = (
    "artificial intelligence",
    "machine learning",
    "computer vision",
    "natural language",
    "deep learning",
    "neural network",
    "generative ai",
    "robotic",
    "autonomous vehicle",
    "speech recognition",
    "predictive analytic",
    "intelligent system",
    "image recognition",
    "data science",
    "ml ops",
    "mlops",
    "voice recognition",
)

# AI-related canonical tags written into Company.ai_tags (subset of category_list).
AI_TAG_NORMALIZATION = {
    "artificial intelligence (ai)": "artificial-intelligence",
    "artificial intelligence": "artificial-intelligence",
    "machine learning": "machine-learning",
    "deep learning": "deep-learning",
    "computer vision": "computer-vision",
    "natural language processing": "nlp",
    "generative ai": "generative-ai",
    "neural networks": "neural-networks",
    "robotics": "robotics",
    "robotic process automation (rpa)": "rpa",
    "predictive analytics": "predictive-analytics",
    "intelligent systems": "intelligent-systems",
    "speech recognition": "speech-recognition",
    "autonomous vehicles": "autonomous-vehicles",
    "image recognition": "image-recognition",
    "data science": "data-science",
    "big data": "big-data",
}


def _ai_mask(orgs: pd.DataFrame) -> pd.Series:
    """Vectorised AI filter — returns boolean Series same length as input."""
    cl = orgs["category_list"].fillna("").str.lower()
    cgl = orgs["category_groups_list"].fillna("").str.lower()
    mask = cgl.str.contains("artificial intelligence", regex=False, na=False)
    for kw in AI_CATEGORY_KEYWORDS:
        mask = mask | cl.str.contains(kw, regex=False, na=False)
    return mask


def _extract_ai_tags(category_list: str) -> List[str]:
    """Pick AI-relevant categories out of the comma-separated list and
    normalise them to short kebab-case tags."""
    if not category_list:
        return []
    out: List[str] = []
    seen: Set[str] = set()
    for raw in str(category_list).split(","):
        cat = raw.strip().lower()
        if not cat:
            continue
        norm = AI_TAG_NORMALIZATION.get(cat)
        if not norm:
            # tolerant match for anything that mentions an AI keyword
            if any(kw in cat for kw in AI_CATEGORY_KEYWORDS):
                norm = cat.replace(" ", "-").replace("(", "").replace(")", "")
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def _ai_score_from_categories(category_list: str, category_groups_list: str) -> float:
    """High score if the org is in the AI top-level group, slightly lower if
    only matched by category keyword. Used for new-row insertion only — we
    never *lower* an existing company's score."""
    cgl = (category_groups_list or "").lower()
    cl = (category_list or "").lower()
    if "artificial intelligence" in cgl:
        return 0.9
    if any(kw in cl for kw in AI_CATEGORY_KEYWORDS):
        return 0.75
    return 0.6


# ── Field parsing ──────────────────────────────────────────────────────
_NAN_TOKENS = {"nan", "none", "null", ""}


def _clean(val) -> str:
    if val is None:
        return ""
    if isinstance(val, float) and pd.isna(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() in _NAN_TOKENS else s


def _parse_year(date_str: str) -> Optional[int]:
    s = _clean(date_str)
    if not s:
        return None
    m = re.match(r"^(\d{4})", s)
    if not m:
        return None
    try:
        y = int(m.group(1))
        if 1900 <= y <= 2100:
            return y
    except ValueError:
        pass
    return None


_EMPLOYEE_RANGE_RE = re.compile(r"(\d+)")


def _parse_employee_count(raw: str) -> Optional[int]:
    """'51-100' -> 51, '10000+' -> 10000, '1-10' -> 1, '' -> None."""
    s = _clean(raw)
    if not s:
        return None
    m = _EMPLOYEE_RANGE_RE.search(s)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


_OPERATING_STATUS_MAP = {
    "operating": "operating",
    "acquired": "acquired",
    "closed": "closed",
    "ipo": "operating",  # post-IPO companies are still operating
}


def _extract_domain(domain: str, homepage: str) -> Optional[str]:
    """Prefer Crunchbase 'domain' field; fallback to canonicalising
    homepage_url. Returns None if neither yields a clean domain."""
    d = _clean(domain)
    if d:
        canon = canonicalize_domain(d)
        if canon:
            return canon
    h = _clean(homepage)
    if h:
        canon = canonicalize_domain(h)
        if canon:
            return canon
    return None


# ── Description merge ─────────────────────────────────────────────────


def _build_description_lookup(
    descriptions_path: Optional[str], ai_uuids: Set[str]
) -> Dict[str, str]:
    """Load organization_descriptions.parquet (1.66M rows) but only keep
    the rows whose uuid is in our AI subset, to control memory."""
    if not descriptions_path or not os.path.exists(descriptions_path):
        return {}
    logger.info(f"Loading long descriptions from {descriptions_path}")
    df = pd.read_parquet(descriptions_path, columns=["uuid", "description"])
    df = df[df["uuid"].isin(ai_uuids)]
    out: Dict[str, str] = {}
    for uuid, desc in zip(df["uuid"], df["description"]):
        s = _clean(desc)
        if s:
            out[str(uuid)] = s[:4000]
    logger.info(f"  -> {len(out)} long descriptions kept for AI orgs")
    return out


# ── Main org import ───────────────────────────────────────────────────


def import_orgs(
    orgs_path: str,
    descriptions_path: Optional[str],
    dry_run: bool,
    insert_new: bool,
    chunk_commit: int = 2000,
) -> Dict[str, int]:
    stats: Dict[str, int] = {
        "total_orgs": 0,
        "ai_orgs": 0,
        "matched": 0,
        "inserted": 0,
        "updated": 0,
        "skipped_no_domain_no_name": 0,
    }

    logger.info(f"Loading {orgs_path}")
    orgs = pd.read_parquet(orgs_path)
    stats["total_orgs"] = len(orgs)
    logger.info(f"  rows={len(orgs):,}")

    mask = _ai_mask(orgs)
    ai_orgs = orgs[mask].reset_index(drop=True)
    stats["ai_orgs"] = len(ai_orgs)
    logger.info(f"AI-filtered: {len(ai_orgs):,} of {len(orgs):,} orgs")

    desc_lookup = _build_description_lookup(
        descriptions_path, set(ai_orgs["uuid"].astype(str).tolist())
    )

    if dry_run:
        logger.info("DRY-RUN — counting only, no DB writes")
        # Estimate matched vs new without touching writes
        with session_scope() as session:
            existing_domains: Set[str] = {
                r[0].lower()
                for r in session.query(Company.domain).filter(Company.domain.isnot(None)).all()
                if r[0]
            }
        match_n = 0
        no_dom_or_name = 0
        for _, row in ai_orgs.iterrows():
            name = _clean(row.get("name"))
            dom = _extract_domain(row.get("domain"), row.get("homepage_url"))
            if not name and not dom:
                no_dom_or_name += 1
                continue
            if dom and dom in existing_domains:
                match_n += 1
        stats["matched"] = match_n
        stats["inserted"] = stats["ai_orgs"] - match_n - no_dom_or_name if insert_new else 0
        stats["skipped_no_domain_no_name"] = no_dom_or_name
        return stats

    # Real run
    with session_scope() as session:
        # Pre-load existing companies indexed by domain (for matching).
        existing_by_domain: Dict[str, Company] = {}
        for company in session.query(Company).filter(Company.domain.isnot(None)).all():
            if company.domain:
                existing_by_domain[company.domain.lower()] = company
        logger.info(f"Pre-loaded {len(existing_by_domain):,} existing companies by domain")

        # Track new domains added in this run so we don't insert dupes when
        # multiple Crunchbase rows share a domain (rare but happens).
        seen_new_domains: Set[str] = set()

        commit_count = 0
        for i, row in enumerate(ai_orgs.itertuples(index=False), start=1):
            row_d = row._asdict()
            name = _clean(row_d.get("name"))
            dom = _extract_domain(row_d.get("domain"), row_d.get("homepage_url"))
            if not name and not dom:
                stats["skipped_no_domain_no_name"] += 1
                continue

            uuid = _clean(row_d.get("uuid"))
            categories = _clean(row_d.get("category_list"))
            cat_groups = _clean(row_d.get("category_groups_list"))
            short_desc = _clean(row_d.get("short_description"))
            long_desc = desc_lookup.get(uuid, "")
            description = long_desc or short_desc
            country = _clean(row_d.get("country_code"))
            city = _clean(row_d.get("city"))
            status = _clean(row_d.get("status")).lower()
            founded_year = _parse_year(row_d.get("founded_on"))
            team_size = _parse_employee_count(row_d.get("employee_count"))
            ai_score = _ai_score_from_categories(categories, cat_groups)
            ai_tags = _extract_ai_tags(categories)
            operating_status = _OPERATING_STATUS_MAP.get(status)

            company: Optional[Company] = None
            if dom and dom in existing_by_domain:
                company = existing_by_domain[dom]
                stats["matched"] += 1
                # Update verification (escalate, never downgrade)
                if company.verification_status == VerificationStatus.verified_pb:
                    company.verification_status = VerificationStatus.verified_cb_pb
                elif company.verification_status == VerificationStatus.emerging_github:
                    company.verification_status = VerificationStatus.verified_cb
                # Fill blanks
                if country and not company.country:
                    company.country = country
                    company.location_source = LocationSource.crunchbase
                if city and not company.city:
                    company.city = city
                if description and not company.description:
                    company.description = description[:4000]
                if founded_year and not company.founded_year:
                    company.founded_year = founded_year
                if team_size and not company.team_size:
                    company.team_size = team_size
                if operating_status and not company.operating_status:
                    company.operating_status = operating_status
                # Update ai_score upward only
                if (company.ai_score or 0) < ai_score:
                    company.ai_score = ai_score
                # Merge ai_tags
                merged = list(company.ai_tags or [])
                for t in ai_tags:
                    if t not in merged:
                        merged.append(t)
                if merged:
                    company.ai_tags = merged
                company.updated_at = datetime.utcnow()
                stats["updated"] += 1
            elif insert_new:
                # New company
                if dom and dom in seen_new_domains:
                    # Same domain encountered twice in this Crunchbase batch;
                    # skip to keep `companies.domain` unique-ish.
                    continue
                if dom:
                    seen_new_domains.add(dom)
                company = Company(
                    name=name or (dom or "(unknown)"),
                    domain=dom,
                    normalized_name=normalize_company_name(name) if name else None,
                    country=country or None,
                    city=city or None,
                    location_source=LocationSource.crunchbase if (country or city) else LocationSource.unknown,
                    verification_status=VerificationStatus.verified_cb,
                    description=description[:4000] if description else None,
                    founded_year=founded_year,
                    team_size=team_size,
                    operating_status=operating_status,
                    ai_score=ai_score,
                    ai_tags=ai_tags or None,
                    first_seen_at=datetime.utcnow(),
                    last_seen_at=datetime.utcnow(),
                )
                session.add(company)
                stats["inserted"] += 1
                # Need flush so company.id is available for SourceMatch.
                if stats["inserted"] % 200 == 0:
                    session.flush()
            else:
                # Skip unmatched (legacy behaviour)
                continue

            # Record source match (idempotent on (company_id, crunchbase_id))
            if company is not None and uuid:
                # company.id may still be None for inserts before flush;
                # SQLAlchemy will resolve on commit. For lookups we rely on
                # the relationship instead.
                if company.id is not None:
                    existing_match = (
                        session.query(SourceMatch)
                        .filter(
                            SourceMatch.company_id == company.id,
                            SourceMatch.crunchbase_id == uuid,
                        )
                        .first()
                    )
                else:
                    existing_match = None
                if not existing_match:
                    session.add(
                        SourceMatch(
                            company=company,
                            crunchbase_id=uuid,
                            match_method=MatchMethod.domain if dom else MatchMethod.name_strict,
                            match_confidence=1.0 if dom else 0.6,
                        )
                    )

            commit_count += 1
            if commit_count >= chunk_commit:
                session.flush()
                session.commit()
                commit_count = 0
                logger.info(
                    f"  progress {i:,}/{len(ai_orgs):,} | "
                    f"matched={stats['matched']:,} inserted={stats['inserted']:,} "
                    f"updated={stats['updated']:,}"
                )

    return stats


# ── Funding rounds ────────────────────────────────────────────────────


def import_funding_rounds(funding_path: str, only_for_inserted_uuids: bool = False) -> Dict[str, int]:
    """Import funding rounds for any company we have in DB (matched by
    SourceMatch.crunchbase_id == funding_round.org_uuid). Adds at most one
    row per (company, deal_uuid)."""
    stats = {"funding_rows": 0, "added": 0, "skipped_no_company": 0}
    if not os.path.exists(funding_path):
        logger.warning(f"Funding rounds file not found: {funding_path}")
        return stats

    logger.info(f"Loading funding rounds from {funding_path}")
    fr = pd.read_parquet(
        funding_path,
        columns=[
            "uuid",
            "investment_type",
            "announced_on",
            "raised_amount_usd",
            "org_uuid",
        ],
    )
    stats["funding_rows"] = len(fr)
    logger.info(f"  funding_rows={len(fr):,}")

    with session_scope() as session:
        # Build org_uuid -> company_id from SourceMatch
        uuid_to_cid: Dict[str, int] = {}
        for cid, cb_uuid in (
            session.query(SourceMatch.company_id, SourceMatch.crunchbase_id)
            .filter(SourceMatch.crunchbase_id.isnot(None))
            .all()
        ):
            if cb_uuid:
                uuid_to_cid[str(cb_uuid)] = cid

        if not uuid_to_cid:
            logger.warning("No SourceMatch rows with crunchbase_id; nothing to attach funding to.")
            return stats

        # Filter funding rounds to only those for our companies
        fr["org_uuid"] = fr["org_uuid"].astype(str)
        fr_relevant = fr[fr["org_uuid"].isin(uuid_to_cid.keys())]
        logger.info(f"  relevant funding rounds: {len(fr_relevant):,}")

        # Pre-load existing FundingSignal raw_metadata uuid set per company
        # to avoid duplicates.
        existing_keys: Set[Tuple[int, str]] = set()
        for cid, raw_md in (
            session.query(FundingSignal.company_id, FundingSignal.raw_metadata)
            .filter(FundingSignal.source == "crunchbase")
            .all()
        ):
            if isinstance(raw_md, dict) and raw_md.get("cb_round_uuid"):
                existing_keys.add((cid, str(raw_md["cb_round_uuid"])))

        commit_n = 0
        for row in fr_relevant.itertuples(index=False):
            r = row._asdict()
            org_uuid = str(r.get("org_uuid", ""))
            cid = uuid_to_cid.get(org_uuid)
            if not cid:
                stats["skipped_no_company"] += 1
                continue
            round_uuid = _clean(r.get("uuid"))
            if (cid, round_uuid) in existing_keys:
                continue
            announced = _clean(r.get("announced_on"))
            try:
                deal_date = (
                    datetime.fromisoformat(announced[:10]) if announced else None
                )
            except ValueError:
                deal_date = None
            try:
                amount = float(r.get("raised_amount_usd") or 0) or None
            except (TypeError, ValueError):
                amount = None
            session.add(
                FundingSignal(
                    company_id=cid,
                    source="crunchbase",
                    deal_date=deal_date,
                    round_type=_clean(r.get("investment_type")) or None,
                    deal_size=amount,
                    raw_metadata={"cb_round_uuid": round_uuid, "cb_org_uuid": org_uuid},
                )
            )
            existing_keys.add((cid, round_uuid))
            stats["added"] += 1
            commit_n += 1
            if commit_n >= 5000:
                session.commit()
                commit_n = 0
                logger.info(f"  funding progress added={stats['added']:,}")

    return stats


# ── CLI ────────────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(description="Import Crunchbase AI companies into DB")
    p.add_argument(
        "--orgs",
        default=str(DEFAULT_BASE / "organizations.parquet"),
        help="Path to organizations.parquet",
    )
    p.add_argument(
        "--descriptions",
        default=str(DEFAULT_BASE / "organization_descriptions.parquet"),
        help="Path to organization_descriptions.parquet (optional, for richer descriptions)",
    )
    p.add_argument(
        "--categories",
        default=str(DEFAULT_BASE / "category_groups.parquet"),
        help="Path to category_groups.parquet (currently unused by the AI mask)",
    )
    p.add_argument(
        "--funding-rounds",
        action="store_true",
        help="Also import funding_rounds.parquet into FundingSignal",
    )
    p.add_argument(
        "--funding-rounds-path",
        default=str(DEFAULT_BASE / "funding_rounds.parquet"),
        help="Override path to funding_rounds.parquet",
    )
    p.add_argument(
        "--no-insert-new",
        action="store_true",
        help="Match-only mode: don't insert unmatched AI orgs (legacy v1 behaviour)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Estimate matched / new counts without writing to DB",
    )
    p.add_argument("--init-db", action="store_true", help="Create DB tables before running")
    p.add_argument(
        "--chunk-commit",
        type=int,
        default=2000,
        help="Commit every N processed rows (default 2000)",
    )
    args = p.parse_args()

    if args.init_db:
        init_db()

    if not os.path.exists(args.orgs):
        logger.error(f"organizations.parquet not found at {args.orgs}")
        sys.exit(1)

    started = time.time()
    logger.info(
        f"START: orgs={args.orgs} descriptions={args.descriptions} "
        f"insert_new={not args.no_insert_new} dry_run={args.dry_run}"
    )

    stats = import_orgs(
        orgs_path=args.orgs,
        descriptions_path=args.descriptions if os.path.exists(args.descriptions) else None,
        dry_run=args.dry_run,
        insert_new=not args.no_insert_new,
        chunk_commit=args.chunk_commit,
    )

    elapsed = time.time() - started
    logger.info("=" * 64)
    logger.info(f"Crunchbase org import complete in {elapsed:.0f}s")
    logger.info(f"  total orgs in parquet:        {stats['total_orgs']:,}")
    logger.info(f"  AI-related orgs:              {stats['ai_orgs']:,}")
    logger.info(f"  matched (existing companies): {stats['matched']:,}")
    logger.info(f"  updated (matched + enriched): {stats['updated']:,}")
    logger.info(f"  inserted (new rows):          {stats['inserted']:,}")
    logger.info(f"  skipped (no name/domain):     {stats['skipped_no_domain_no_name']:,}")
    logger.info("=" * 64)

    if args.funding_rounds and not args.dry_run:
        logger.info("Importing funding rounds...")
        f_stats = import_funding_rounds(args.funding_rounds_path)
        logger.info(f"Funding rounds: added={f_stats['added']:,} of {f_stats['funding_rows']:,}")


if __name__ == "__main__":
    main()
