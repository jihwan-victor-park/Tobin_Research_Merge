#!/usr/bin/env python3
"""
Enrich the hidden (non-CB/PB) population from data we already scraped — free,
no external calls. Two independent enrichments:

  1. cohort_year   — decode incubator_signals.batch (e.g. Techstars '2019',
     YC 'W26'/'S23', 'Spring 2026') into a year. This is a FOUNDING-YEAR PROXY:
     a company is founded, then joins an accelerator, so the cohort year runs
     slightly after true founding. Stored in companies.cohort_year, kept
     separate from founded_year (analysis can COALESCE with that caveat).
     Batch values that aren't years ('Batch 20', 'Class 11', 'student-i-lab')
     are left alone.

  2. country (TLD) — infer country from high-confidence ccTLDs for companies
     with country=NULL and a domain. Reuses the TLD map from
     infer_country_from_tld.py but writes the canonical FULL country name via
     backend.utils.country.normalize_country (the existing script writes raw
     ISO codes, which would re-introduce the un-normalized values we cleaned).

Runs directly against the target DB (RAILWAY_DATABASE_URL if --railway, else
DATABASE_URL). Self-contained by company id — no cross-DB id matching. Scoped
to non-CB/PB companies. Reconnect-and-retry on Railway proxy drops.

Usage:
    python scripts/enrich_hidden_from_scraped.py --dry-run
    python scripts/enrich_hidden_from_scraped.py            # local
    python scripts/enrich_hidden_from_scraped.py --railway  # Railway (canonical)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from backend.utils.country import normalize_country  # noqa: E402
from scripts.infer_country_from_tld import TLD_TO_COUNTRY, extract_tld  # noqa: E402

NON_CB_PB = "verification_status NOT IN ('verified_cb', 'verified_pb', 'verified_cb_pb')"

# ISO code (what TLD_TO_COUNTRY yields) -> canonical full name via the shared
# normalizer, so TLD-inferred country matches everything else in the DB.
_ISO_TO_NAME = {iso: normalize_country(iso) for iso in set(TLD_TO_COUNTRY.values())}


def decode_batch_year(batch: str) -> int | None:
    """Decode an accelerator batch label into a 4-digit year, or None.

    Handles: plain '2019'; 'Spring 2026' / 'Fall 2019'; YC 'W26'/'S23'/'W2021'.
    Rejects year-less labels ('Batch 20', 'Class 11', 'student-i-lab').
    """
    if not batch:
        return None
    b = batch.strip()
    # YC-style: W/S + 2-digit (W26 -> 2026) or 4-digit (W2021 -> 2021)
    m = re.fullmatch(r"[WSwsFf](\d{2}|\d{4})", b)
    if m:
        y = m.group(1)
        return int(y) if len(y) == 4 else 2000 + int(y)
    # Any explicit 4-digit year in the string (covers '2019', 'Spring 2026')
    m = re.search(r"(19|20)\d{2}", b)
    if m:
        return int(m.group(0))
    return None


def connect(url: str):
    return psycopg2.connect(url, connect_timeout=20)


def ensure_column(conn) -> None:
    cur = conn.cursor()
    for col in ("cohort_year", "grant_first_award_year"):
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='companies' AND column_name=%s", (col,)
        )
        if cur.fetchone() is None:
            cur.execute(f"ALTER TABLE companies ADD COLUMN {col} INTEGER")
            conn.commit()
            print(f"  Added column companies.{col}")


def write_batches(url, rows, sql, template, label, batch_size=2000, max_retries=6):
    if not rows:
        print(f"  {label}: nothing to write")
        return
    conn = connect(url); cur = conn.cursor()
    i = 0
    while i < len(rows):
        chunk = rows[i:i + batch_size]
        for attempt in range(1, max_retries + 1):
            try:
                psycopg2.extras.execute_values(cur, sql, chunk, template=template)
                conn.commit(); break
            except psycopg2.OperationalError as e:
                print(f"  [{label}] drop at {i} (retry {attempt}/{max_retries}): {e}")
                try: conn.close()
                except Exception: pass
                time.sleep(3); conn = connect(url); cur = conn.cursor()
        else:
            sys.exit(f"[{label}] gave up at row {i}")
        i += batch_size
    conn.close()
    print(f"  {label}: wrote {len(rows):,}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--railway", action="store_true", help="Target Railway (else local DATABASE_URL)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    url = os.getenv("RAILWAY_DATABASE_URL") if args.railway else os.getenv("DATABASE_URL")
    if not url:
        sys.exit("target DB URL not set")
    print(f"Target: {'RAILWAY' if args.railway else 'LOCAL'}")

    conn = connect(url); cur = conn.cursor()

    # ── 1. cohort_year from batch ──────────────────────────────────────
    cur.execute(f"""
        SELECT c.id, array_agg(s.batch)
        FROM companies c
        JOIN incubator_signals s ON s.company_id = c.id
        WHERE {NON_CB_PB} AND c.founded_year IS NULL AND s.batch IS NOT NULL
        GROUP BY c.id
    """)
    cohort_updates = []
    for cid, batches in cur.fetchall():
        years = [y for y in (decode_batch_year(b) for b in batches) if y and 1990 <= y <= 2026]
        if years:
            cohort_updates.append((cid, min(years)))  # earliest cohort ~ closest to founding
    print(f"\n1. cohort_year: {len(cohort_updates):,} companies get a decoded cohort year")

    # ── 2. country from TLD ────────────────────────────────────────────
    cur.execute(f"""
        SELECT id, domain FROM companies
        WHERE {NON_CB_PB} AND country IS NULL AND domain IS NOT NULL
    """)
    country_updates = []
    by_country = {}
    for cid, domain in cur.fetchall():
        tld = extract_tld(domain)
        if not tld:
            continue
        name = _ISO_TO_NAME.get(TLD_TO_COUNTRY[tld])
        if name:
            country_updates.append((cid, name))
            by_country[name] = by_country.get(name, 0) + 1
    print(f"2. country (TLD): {len(country_updates):,} companies get an inferred country")
    top = sorted(by_country.items(), key=lambda x: -x[1])[:8]
    print(f"   top: {top}")

    # ── 3. grant_first_award_year from SBIR/STTR descriptions ──────────
    # Victor's import_gov_grants.py writes "SBIR/STTR awardee (first award YYYY)."
    # First-award year is a founding-year PROXY for deep-tech grant firms (they
    # typically win their first SBIR grant near founding). Priority below
    # cohort_year in the COALESCE.
    cur.execute(f"""
        SELECT id, description FROM companies
        WHERE {NON_CB_PB} AND founded_year IS NULL AND cohort_year IS NULL
          AND source_domain IN ('nih.gov', 'nsf.gov') AND description IS NOT NULL
    """)
    grant_updates = []
    for cid, desc in cur.fetchall():
        m = re.search(r"first award\D{0,6}((19|20)\d{2})", desc, re.I)
        if m:
            y = int(m.group(1))
            if 1990 <= y <= 2026:
                grant_updates.append((cid, y))
    print(f"3. grant_first_award_year: {len(grant_updates):,} SBIR/STTR firms get a first-award year")
    conn.close()

    if args.dry_run:
        print("\n(dry-run — no writes)")
        return

    conn = connect(url); ensure_column(conn); conn.close()
    write_batches(url, cohort_updates,
        "UPDATE companies AS c SET cohort_year = v.yr FROM (VALUES %s) AS v(id, yr) "
        "WHERE c.id = v.id AND c.founded_year IS NULL",
        "(%s, %s)", "cohort_year")
    write_batches(url, grant_updates,
        "UPDATE companies AS c SET grant_first_award_year = v.yr FROM (VALUES %s) AS v(id, yr) "
        "WHERE c.id = v.id AND c.founded_year IS NULL AND c.cohort_year IS NULL",
        "(%s, %s)", "grant_first_award_year")
    write_batches(url, country_updates,
        "UPDATE companies AS c SET country = v.ctry FROM (VALUES %s) AS v(id, ctry) "
        "WHERE c.id = v.id AND c.country IS NULL",
        "(%s, %s)", "country")
    print("\nDone.")


if __name__ == "__main__":
    main()
