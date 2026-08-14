"""
Attach named company leadership from NIH RePORTER award records.

Founder data is the field we have least of (4% of hidden companies) and the one
an LLM is most likely to invent, because obscure companies are exactly where a
model has nothing to recall and will produce a plausible name anyway. NIH avoids
that entirely: every SBIR/STTR award names its principal investigators, with
titles, in the public record. SBIR rules require the PI to be primarily employed
by the small business, so these are the company's own people, not academic
collaborators.

A PI is not necessarily a *founder* — it is verified leadership at the time of
the award — so the title is stored alongside the name and the source is recorded
as nih_reporter, which lets the distinction survive into any analysis.

The names are public federal award records, the same data already published on
reporter.nih.gov.

    python scripts/import_grant_people.py --dry-run
    python scripts/import_grant_people.py --since-year 2010
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from sqlalchemy import text  # noqa: E402

from backend.db.connection import get_engine  # noqa: E402
from backend.utils.normalize import normalize_company_name  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("import_grant_people")

NIH_URL = "https://api.reporter.nih.gov/v2/projects/search"
SBIR_CODES = ["R41", "R42", "R43", "R44"]

# Titles that indicate the person runs the company rather than a lab bench.
LEADERSHIP = ("ceo", "chief executive", "cto", "chief technology", "coo",
              "chief operating", "president", "founder", "co-founder",
              "cso", "chief scientific", "cfo", "chief financial",
              "managing director", "principal", "owner", "partner")


def _is_leadership(title: str) -> bool:
    return any(k in (title or "").lower() for k in LEADERSHIP)


def fetch_people(since_year: int) -> Dict[str, list]:
    """{normalized_company_name: [{name, title}, ...]} from SBIR/STTR awards."""
    people: Dict[str, dict] = {}
    this_year = datetime.now(timezone.utc).year
    for fy in range(since_year, this_year + 1):
        offset = 0
        while True:
            payload = {
                "criteria": {"activity_codes": SBIR_CODES, "fiscal_years": [fy]},
                "limit": 500, "offset": offset,
                "include_fields": ["Organization", "FiscalYear",
                                   "PrincipalInvestigators", "ContactPiName"],
            }
            for attempt in range(4):
                try:
                    r = requests.post(NIH_URL, json=payload, timeout=90)
                    r.raise_for_status()
                    break
                except Exception as e:
                    if attempt == 3:
                        logger.warning(f"NIH FY{fy} offset {offset}: giving up ({e})")
                        return people_as_lists(people)
                    wait = 5 * (2 ** attempt)
                    logger.warning(f"NIH FY{fy} offset {offset}: {e} — retry in {wait}s")
                    time.sleep(wait)
            body = r.json()
            total = body["meta"]["total"]
            for rec in body.get("results", []):
                org = (rec.get("organization") or {}).get("org_name") or ""
                norm = normalize_company_name(org.strip()) if org.strip() else None
                if not norm:
                    continue
                bucket = people.setdefault(norm, {})
                for pi in rec.get("principal_investigators") or []:
                    name = " ".join((pi.get("full_name") or "").split())
                    if not name:
                        continue
                    title = (pi.get("title") or "").strip()
                    # Keep the most informative title seen for a person: a later
                    # award may name them CEO where an earlier one said nothing.
                    prev = bucket.get(name.lower())
                    if prev is None or (not prev["title"] and title):
                        bucket[name.lower()] = {"name": name, "title": title}
            offset += 500
            if offset >= total or offset >= 14500:
                break
            time.sleep(0.4)
        logger.info(f"NIH FY{fy}: {total:,} awards — {len(people):,} companies with named people")
    return people_as_lists(people)


def people_as_lists(people: Dict[str, dict]) -> Dict[str, list]:
    out = {}
    for norm, bucket in people.items():
        # Leadership first, then anyone else, capped so one company cannot
        # dominate the column.
        ppl = sorted(bucket.values(), key=lambda p: (not _is_leadership(p["title"]), p["name"]))
        out[norm] = ppl[:6]
    return out


def write(people: Dict[str, list], dry_run: bool) -> dict:
    engine = get_engine()
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT id, normalized_name FROM companies
            WHERE normalized_name IS NOT NULL
              AND source_domain IN ('nih.gov', 'nsf.gov')
        """)).all()
    by_norm = {(n or "").lower(): cid for cid, n in rows}
    logger.info(f"{len(by_norm):,} grant-sourced companies in the database")

    matched = {norm: by_norm[norm.lower()] for norm in people if norm.lower() in by_norm}
    with_leader = sum(
        1 for norm in matched if any(_is_leadership(p["title"]) for p in people[norm])
    )
    stats = {"companies_matched": len(matched), "with_named_leader": with_leader,
             "people_total": sum(len(people[n]) for n in matched)}
    if dry_run:
        return stats

    written = 0
    with engine.begin() as c:
        for norm, cid in matched.items():
            ppl = people[norm]
            if not ppl:
                continue
            c.execute(text("""
                INSERT INTO company_enrichment (company_id, founders, sources, enriched_at)
                VALUES (:cid, CAST(:f AS jsonb), CAST(:s AS jsonb), now())
                ON CONFLICT (company_id) DO UPDATE SET
                    founders = COALESCE(company_enrichment.founders, EXCLUDED.founders),
                    sources  = company_enrichment.sources || EXCLUDED.sources,
                    enriched_at = now()
            """), {"cid": cid, "f": json.dumps(ppl),
                   "s": json.dumps({"founders": {"source": "nih_reporter",
                                                 "confidence": 0.9,
                                                 "note": "principal investigator at award time"}})})
            written += 1
    stats["written"] = written
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since-year", type=int, default=2000)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    people = fetch_people(a.since_year)
    logger.info(f"Fetched named people for {len(people):,} awardee organisations")
    logger.info(f"Done: {write(people, a.dry_run)}")


if __name__ == "__main__":
    main()
