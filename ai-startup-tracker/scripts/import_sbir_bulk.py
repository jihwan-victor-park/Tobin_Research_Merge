"""
Import and enrich from the full SBIR/STTR award file (all US agencies).

sbir.gov's JSON API returns 403, but the same data is published as a single
bulk CSV, and it is the richest free source we have found: 207k awards carrying
company name, website, abstract, award year, city/state, employee count, and
the contact and principal investigator with their job titles.

Two distinct jobs, because the file is valuable for both:

  discovery   awards whose *title* matches the AI standard used by the other
              grant importers become new hidden companies
  enrichment  any company already in the database that appears anywhere in the
              file — AI award or not — gets the fields we are missing. This is
              the larger half: it reaches ~17.5k existing companies and supplies
              named people for nearly all of them, against 4% founder coverage
              from every other method combined.

Named people are the contact/PI on the award, not necessarily founders, so the
title is stored with the name and the source is recorded as sbir_award. All of
it is public federal award data.

    python scripts/import_sbir_bulk.py --dry-run
    python scripts/import_sbir_bulk.py --mode enrich
    python scripts/import_sbir_bulk.py --mode all
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Dict

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from sqlalchemy import text  # noqa: E402

from backend.db.connection import get_engine  # noqa: E402
from backend.utils.normalize import normalize_company_name  # noqa: E402
from scripts.import_gov_grants import _hostname, _looks_ai  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("import_sbir_bulk")

CSV_URL = "https://data.www.sbir.gov/awarddatapublic/award_data.csv"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BATCH = 300   # Railway round-trips cost ~175ms each, so never write row by row


def ensure_local(path: str) -> str:
    if os.path.exists(path) and os.path.getsize(path) > 10_000_000:
        return path
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    logger.info(f"downloading {CSV_URL} (~350MB)")
    with requests.get(CSV_URL, stream=True, timeout=1800,
                      headers={"User-Agent": UA}) as r:
        r.raise_for_status()
        with open(path, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    return path


def _clean_person(name: str) -> str:
    return " ".join((name or "").split()).strip(" ,.")


def read_awards(path: str) -> Dict[str, dict]:
    """One record per company, merged across all of its awards."""
    csv.field_size_limit(10 ** 9)
    comp: Dict[str, dict] = {}
    n = 0
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        for r in csv.DictReader(f):
            n += 1
            name = (r.get("Company") or "").strip()
            norm = normalize_company_name(name) if name else None
            if not norm:
                continue
            c = comp.setdefault(norm, {
                "name": name.title() if name.isupper() else name,
                "domain": None, "year": None, "city": None, "state": None,
                "employees": None, "description": None, "people": {},
                "ai": False, "agencies": set(),
            })
            if _looks_ai(r.get("Award Title", "")):
                c["ai"] = True
                if not c["description"]:
                    c["description"] = (r.get("Award Title") or "").strip()[:300]
            c["domain"] = c["domain"] or _hostname(r.get("Company Website") or "")
            year = (r.get("Award Year") or "").strip()
            if year.isdigit():
                y = int(year)
                if 1980 <= y <= 2030 and (c["year"] is None or y < c["year"]):
                    c["year"] = y
            c["city"] = c["city"] or (r.get("City") or "").strip() or None
            c["state"] = c["state"] or (r.get("State") or "").strip() or None
            emp = (r.get("Number Employees") or "").strip()
            if emp.isdigit() and c["employees"] is None:
                c["employees"] = int(emp)
            if not c["description"]:
                c["description"] = (r.get("Award Title") or "").strip()[:300] or None
            ag = (r.get("Agency") or "").strip()
            if ag:
                c["agencies"].add(ag)
            for nm_key, ti_key in (("Contact Name", "Contact Title"), ("PI Name", "PI Title")):
                person = _clean_person(r.get(nm_key, ""))
                if not person or len(person) > 80:
                    continue
                title = " ".join((r.get(ti_key) or "").split())[:60]
                prev = c["people"].get(person.lower())
                if prev is None or (not prev["title"] and title):
                    c["people"][person.lower()] = {"name": person, "title": title}
    logger.info(f"{n:,} awards -> {len(comp):,} unique companies "
                f"({sum(1 for c in comp.values() if c['ai']):,} with an AI-titled award)")
    return comp


def _desc_for(c: dict) -> str:
    agency = sorted(c["agencies"])[0] if c["agencies"] else "a federal agency"
    base = f"SBIR/STTR awardee, {agency} (first award {c['year']})."
    return f"{base} Project: {c['description'][:180]}" if c["description"] else base


def run(comp: Dict[str, dict], mode: str, dry_run: bool) -> dict:
    engine = get_engine()
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT id, normalized_name, domain, description, team_size, city, country
            FROM companies WHERE normalized_name IS NOT NULL
        """)).all()
    by_norm = {(r[1] or "").lower(): r for r in rows}
    # companies.domain is UNIQUE, and the query above is filtered to rows that
    # have a normalized_name — so it cannot see a domain held by a company
    # without one. Ask for every domain separately or the insert hits the
    # constraint on the first such collision.
    with engine.connect() as c:
        taken_domains = {
            (d or "").lower()
            for (d,) in c.execute(text("SELECT domain FROM companies WHERE domain IS NOT NULL"))
        }

    stats = {"enriched": 0, "people": 0, "domains": 0, "team": 0, "new": 0}
    updates, people_rows, inserts = [], [], []

    for norm, c in comp.items():
        row = by_norm.get(norm.lower())
        if row is None:
            # Discovery is restricted to the AI standard; enrichment is not,
            # because a company we already track is in scope whatever this
            # particular award was about.
            if mode in ("discover", "all") and c["ai"]:
                inserts.append((norm, c))
            continue
        if mode not in ("enrich", "all"):
            continue
        cid, _, dom, desc, team, city, country = row
        fields = {}
        if c["domain"] and not dom and c["domain"] not in taken_domains:
            fields["domain"] = c["domain"]
            taken_domains.add(c["domain"])
            stats["domains"] += 1
        if c["employees"] and not team:
            fields["team_size"] = c["employees"]
            stats["team"] += 1
        if not desc:
            fields["description"] = _desc_for(c)
        if not city and c["city"]:
            fields["city"] = c["city"]
        if not country:
            fields["country"] = "United States"
        if fields:
            updates.append((cid, fields))
            stats["enriched"] += 1
        if c["people"]:
            people_rows.append((cid, list(c["people"].values())[:6]))
            stats["people"] += 1

    stats["new"] = len(inserts)
    if dry_run:
        return stats

    now = datetime.now(timezone.utc)
    for i in range(0, len(updates), BATCH):
        with engine.begin() as conn:
            for cid, fields in updates[i:i + BATCH]:
                sets = ", ".join(f"{k} = :{k}" for k in fields)
                conn.execute(text(f"UPDATE companies SET {sets}, updated_at = now() WHERE id = :cid"),
                             {**fields, "cid": cid})
        if i % (BATCH * 10) == 0:
            logger.info(f"  companies updated: {min(i + BATCH, len(updates)):,}/{len(updates):,}")

    src = json.dumps({"founders": {"source": "sbir_award", "confidence": 0.85,
                                   "note": "award contact / principal investigator, with title"}})
    for i in range(0, len(people_rows), BATCH):
        with engine.begin() as conn:
            for cid, ppl in people_rows[i:i + BATCH]:
                conn.execute(text("""
                    INSERT INTO company_enrichment (company_id, founders, sources, enriched_at)
                    VALUES (:cid, CAST(:f AS jsonb), CAST(:s AS jsonb), now())
                    ON CONFLICT (company_id) DO UPDATE SET
                        founders = COALESCE(company_enrichment.founders, EXCLUDED.founders),
                        sources  = company_enrichment.sources || EXCLUDED.sources,
                        enriched_at = now()
                """), {"cid": cid, "f": json.dumps(ppl), "s": src})
        if i % (BATCH * 10) == 0:
            logger.info(f"  people written: {min(i + BATCH, len(people_rows)):,}/{len(people_rows):,}")

    for i in range(0, len(inserts), BATCH):
        with engine.begin() as conn:
            for norm, c in inserts[i:i + BATCH]:
                dom = c["domain"] if c["domain"] and c["domain"] not in taken_domains else None
                if dom:
                    taken_domains.add(dom)
                conn.execute(text("""
                    INSERT INTO companies
                      (name, normalized_name, domain, country, city, description,
                       team_size, ai_mentioned, grant_first_award_year,
                       verification_status, source_domain,
                       first_seen_at, last_seen_at, created_at, updated_at)
                    VALUES (:name, :norm, :dom, 'United States', :city, :desc,
                            :team, true, :year, 'emerging_github', 'sbir.gov',
                            :now, :now, :now, :now)
                """), {"name": c["name"][:255], "norm": norm, "dom": dom,
                       "city": c["city"], "desc": _desc_for(c), "team": c["employees"],
                       "year": c["year"], "now": now})
        if i % (BATCH * 10) == 0:
            logger.info(f"  new companies: {min(i + BATCH, len(inserts)):,}/{len(inserts):,}")
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["discover", "enrich", "all"], default="all")
    ap.add_argument("--path", default="data/sbir/award_data.csv")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    comp = read_awards(ensure_local(a.path))
    logger.info(f"Done: {run(comp, a.mode, a.dry_run)}")


if __name__ == "__main__":
    main()
