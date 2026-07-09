"""
Import SBIR/STTR grant-winning firms from NIH RePORTER and NSF award APIs.

These are the most "hidden" startups we can source for free: tiny deep-tech
companies that won a federal SBIR/STTR grant, often years before appearing
in Crunchbase/PitchBook (if ever). Both APIs are public, keyless bulk data.

  NIH RePORTER : activity codes R41/R42 (STTR) + R43/R44 (SBIR)
  NSF          : award search, keyword SBIR / STTR

Dedup follows import_pitchbook_companies.py: by domain (none here) then by
normalized company name. New firms get verification_status=emerging_github
(the non-CB/PB bucket) and source_domain nih.gov / nsf.gov.

Usage:
    python scripts/import_gov_grants.py --dry-run          # count only
    python scripts/import_gov_grants.py                    # full import
    python scripts/import_gov_grants.py --source nih       # one source
    python scripts/import_gov_grants.py --since-year 2010  # recent firms only
"""
import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Optional

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from backend.db.connection import session_scope, init_db  # noqa: E402
from backend.db.models import Company, VerificationStatus  # noqa: E402
from backend.utils.normalize import normalize_company_name  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("import_gov_grants")

NIH_URL = "https://api.reporter.nih.gov/v2/projects/search"
NSF_URL = "https://api.nsf.gov/services/v1/awards.json"

AI_TITLE_KEYWORDS = (
    "artificial intelligence", " ai ", "ai-", "machine learning", "deep learning",
    "neural network", "computer vision", "natural language", "llm",
    "generative", "autonomous",
)


def _looks_ai(title: str) -> bool:
    t = f" {title.lower()} "
    return any(k in t for k in AI_TITLE_KEYWORDS)


# ── NIH RePORTER ─────────────────────────────────────────────────────

def fetch_nih(since_year: int) -> Dict[str, dict]:
    """One record per firm: {norm_name: {...}}. Partitioned by fiscal year
    because RePORTER caps any single search at ~15K records."""
    firms: Dict[str, dict] = {}
    this_year = datetime.now(timezone.utc).year
    for fy in range(since_year, this_year + 1):
        offset, total = 0, None
        while True:
            payload = {
                "criteria": {"activity_codes": ["R41", "R42", "R43", "R44"],
                             "fiscal_years": [fy]},
                "limit": 500, "offset": offset,
                "include_fields": ["Organization", "FiscalYear", "ProjectTitle",
                                   "AwardAmount", "ActivityCode"],
            }
            for attempt in range(4):
                try:
                    r = requests.post(NIH_URL, json=payload, timeout=60)
                    r.raise_for_status()
                    break
                except Exception as e:
                    if attempt == 3:
                        raise
                    wait = 5 * (2 ** attempt)
                    logger.warning(f"NIH FY{fy} offset {offset}: {e} — retry in {wait}s")
                    time.sleep(wait)
            body = r.json()
            total = body["meta"]["total"]
            for rec in body.get("results", []):
                org = rec.get("organization") or {}
                name = (org.get("org_name") or "").strip()
                if not name:
                    continue
                norm = normalize_company_name(name)
                if not norm:
                    continue
                title = rec.get("project_title") or ""
                f = firms.setdefault(norm, {
                    "name": name.title() if name.isupper() else name,
                    "city": (org.get("org_city") or "").strip() or None,
                    "state": org.get("org_state"),
                    "country": "United States",
                    "first_year": rec.get("fiscal_year"),
                    "titles": [], "source": "nih.gov", "ai": False,
                })
                fy_rec = rec.get("fiscal_year")
                if fy_rec and (f["first_year"] is None or fy_rec < f["first_year"]):
                    f["first_year"] = fy_rec
                if len(f["titles"]) < 2 and title:
                    f["titles"].append(title)
                f["ai"] = f["ai"] or _looks_ai(title)
            offset += 500
            if offset >= total or offset >= 14500:
                break
            time.sleep(0.5)
        logger.info(f"NIH FY{fy}: {total} awards, {len(firms):,} unique firms so far")
    return firms


# ── NSF ──────────────────────────────────────────────────────────────

def fetch_nsf(since_year: int) -> Dict[str, dict]:
    firms: Dict[str, dict] = {}
    for kw in ("SBIR", "STTR"):
        offset = 1  # NSF API is 1-indexed
        while True:
            params = {
                "keyword": kw,
                "printFields": "awardeeName,awardeeCity,awardeeStateCode,awardeeCountryCode,date,title",
                "offset": offset, "rpp": 25,
                "dateStart": f"01/01/{since_year}",
            }
            for attempt in range(4):
                try:
                    r = requests.get(NSF_URL, params=params, timeout=60)
                    r.raise_for_status()
                    break
                except Exception as e:
                    if attempt == 3:
                        raise
                    wait = 5 * (2 ** attempt)
                    logger.warning(f"NSF {kw} offset {offset}: {e} — retry in {wait}s")
                    time.sleep(wait)
            awards = (r.json().get("response") or {}).get("award") or []
            if not awards:
                break
            for rec in awards:
                name = (rec.get("awardeeName") or "").strip()
                if not name:
                    continue
                norm = normalize_company_name(name)
                if not norm:
                    continue
                title = rec.get("title") or ""
                year = None
                date = rec.get("date") or ""
                if len(date) >= 10:  # MM/DD/YYYY
                    try:
                        year = int(date[-4:])
                    except ValueError:
                        pass
                f = firms.setdefault(norm, {
                    "name": name.title() if name.isupper() else name,
                    "city": (rec.get("awardeeCity") or "").strip().title() or None,
                    "state": rec.get("awardeeStateCode"),
                    "country": "United States",
                    "first_year": year,
                    "titles": [], "source": "nsf.gov", "ai": False,
                })
                if year and (f["first_year"] is None or year < f["first_year"]):
                    f["first_year"] = year
                if len(f["titles"]) < 2 and title:
                    f["titles"].append(title)
                f["ai"] = f["ai"] or _looks_ai(title)
            if len(awards) < 25:
                break
            offset += 25
            if offset % 2500 == 1:
                logger.info(f"NSF {kw}: {offset - 1} awards scanned, {len(firms):,} unique firms")
            time.sleep(0.3)
        logger.info(f"NSF {kw} done: {len(firms):,} unique firms total")
    return firms


# ── Import ───────────────────────────────────────────────────────────

def import_firms(firms: Dict[str, dict], dry_run: bool) -> Dict[str, int]:
    stats = {"new": 0, "enriched": 0, "already_known": 0}
    now = datetime.now(timezone.utc)
    if dry_run:
        stats["new"] = len(firms)
        return stats

    with session_scope() as db:
        existing_norm: Dict[str, int] = {}
        for c in db.query(Company.id, Company.normalized_name).all():
            if c.normalized_name:
                existing_norm[c.normalized_name.lower()] = c.id

        total = len(firms)
        for i, (norm, f) in enumerate(firms.items()):
            if i % 2000 == 0:
                logger.info(f"  Progress: {i:,}/{total:,}")
            desc = f"SBIR/STTR awardee (first award {f['first_year']}). " \
                   f"Project: {f['titles'][0][:180]}" if f["titles"] else \
                   f"SBIR/STTR awardee (first award {f['first_year']})."

            existing_id = existing_norm.get(norm.lower())
            if existing_id:
                existing = db.query(Company).get(existing_id)
                changed = False
                if not existing.description:
                    existing.description = desc
                    changed = True
                if not existing.city and f["city"]:
                    existing.city = f["city"]
                    changed = True
                if f["ai"] and not existing.ai_mentioned:
                    existing.ai_mentioned = True
                    changed = True
                if changed:
                    existing.updated_at = now
                    stats["enriched"] += 1
                else:
                    stats["already_known"] += 1
                continue

            db.add(Company(
                name=f["name"],
                normalized_name=norm,
                country=f["country"],
                city=f["city"],
                description=desc,
                ai_mentioned=f["ai"],
                verification_status=VerificationStatus.emerging_github,
                source_domain=f["source"],
                first_seen_at=now, last_seen_at=now,
                created_at=now, updated_at=now,
            ))
            existing_norm[norm.lower()] = -1  # guard against dupes within run
            stats["new"] += 1
            if stats["new"] % 5000 == 0:
                db.flush()
    return stats


def main():
    ap = argparse.ArgumentParser(description="Import SBIR/STTR firms from NIH + NSF")
    ap.add_argument("--source", choices=["nih", "nsf", "all"], default="all")
    ap.add_argument("--since-year", type=int, default=2000)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    init_db()
    firms: Dict[str, dict] = {}
    if args.source in ("nih", "all"):
        firms.update(fetch_nih(args.since_year))
    if args.source in ("nsf", "all"):
        nsf = fetch_nsf(args.since_year)
        for norm, f in nsf.items():  # NIH record wins on collision
            firms.setdefault(norm, f)

    logger.info(f"Fetched {len(firms):,} unique grant-winning firms "
                f"({sum(1 for f in firms.values() if f['ai']):,} AI-flagged)")
    stats = import_firms(firms, args.dry_run)
    logger.info(f"Done: {stats}")


if __name__ == "__main__":
    main()
