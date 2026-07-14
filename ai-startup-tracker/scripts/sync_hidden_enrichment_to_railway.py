"""Push today's non-CB/PB enrichment (Revelio founded_year/naics, normalized
country, domain-liveness) from local -> Railway. Companion to
sync_llm_ai_verified_to_railway.py — same domain-matched pattern and the
same reconnect-and-retry resilience (Railway's proxy drops long-lived
connections after a few minutes, observed repeatedly earlier this session).

Run:
  python3 scripts/sync_hidden_enrichment_to_railway.py            # dry-run
  python3 scripts/sync_hidden_enrichment_to_railway.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

LOCAL_URL = os.getenv("DATABASE_URL")
RAILWAY_URL = os.getenv("RAILWAY_DATABASE_URL")

NON_CB_PB_FILTER = "verification_status NOT IN ('verified_cb', 'verified_pb', 'verified_cb_pb')"


def _guard(url: str | None, label: str) -> str:
    if not url:
        sys.exit(f"{label} not set")
    if "localhost" in url and label == "RAILWAY_DATABASE_URL":
        sys.exit("RAILWAY_DATABASE_URL looks like localhost — paste the Railway URL")
    if "railway.internal" in url:
        sys.exit("Use DATABASE_PUBLIC_URL, not the internal URL")
    return url


def ensure_railway_columns(rcur, rconn) -> None:
    for col, ddl in [
        ("naics_code", "ALTER TABLE companies ADD COLUMN naics_code VARCHAR(10)"),
        ("domain_status", "ALTER TABLE companies ADD COLUMN domain_status VARCHAR(16)"),
        ("domain_checked_at", "ALTER TABLE companies ADD COLUMN domain_checked_at TIMESTAMP"),
    ]:
        rcur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'companies' AND column_name = %s", (col,)
        )
        if rcur.fetchone() is None:
            rcur.execute(ddl)
            rconn.commit()
            print(f"  Added column companies.{col} on Railway")


def run_batches(railway_url: str, rows: list[tuple], update_sql: str, template: str,
                 label: str, batch_size: int = 3000, max_retries: int = 8) -> None:
    if not rows:
        print(f"  {label}: nothing to sync")
        return
    rconn = psycopg2.connect(railway_url)
    rcur = rconn.cursor()
    i = 0
    while i < len(rows):
        chunk = rows[i:i + batch_size]
        for attempt in range(1, max_retries + 1):
            try:
                psycopg2.extras.execute_values(rcur, update_sql, chunk, template=template)
                rconn.commit()
                break
            except psycopg2.OperationalError as e:
                print(f"  [{label}] connection dropped at row {i:,} (retry {attempt}/{max_retries}): {e}")
                try:
                    rconn.close()
                except Exception:
                    pass
                time.sleep(3)
                rconn = psycopg2.connect(railway_url)
                rcur = rconn.cursor()
        else:
            sys.exit(f"[{label}] giving up after {max_retries} retries at row {i:,}/{len(rows):,}")
        i += batch_size
        print(f"  [{label}] synced ~{min(i, len(rows)):,}/{len(rows):,}", flush=True)
    rcur.close()
    rconn.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    local_url = _guard(LOCAL_URL, "DATABASE_URL")
    railway_url = _guard(RAILWAY_URL, "RAILWAY_DATABASE_URL")

    lconn = psycopg2.connect(local_url)
    lcur = lconn.cursor()

    print("Reading local non-CB/PB enrichment (domain-keyed)...")
    lcur.execute(f"""
        SELECT domain, founded_year, naics_code, country, domain_status, domain_checked_at
        FROM companies
        WHERE {NON_CB_PB_FILTER} AND domain IS NOT NULL
    """)
    all_rows = lcur.fetchall()
    print(f"  candidate rows: {len(all_rows):,}")

    founded_year_rows = [(d.lower(), y) for d, y, *_ in all_rows if y is not None]
    naics_rows = [(d.lower(), n) for d, _, n, *_ in all_rows if n is not None]
    country_rows = [(d.lower(), c) for d, _, _, c, *_ in all_rows if c is not None]
    domain_status_rows = [(d.lower(), s, t) for d, _, _, _, s, t in all_rows if s is not None]

    print(f"  founded_year to sync: {len(founded_year_rows):,}")
    print(f"  naics_code to sync:   {len(naics_rows):,}")
    print(f"  country to sync:      {len(country_rows):,}")
    print(f"  domain_status to sync:{len(domain_status_rows):,}")

    if not args.apply:
        print("(dry-run — re-run with --apply to write to Railway)")
        return

    rconn = psycopg2.connect(railway_url)
    rcur = rconn.cursor()
    ensure_railway_columns(rcur, rconn)
    rcur.close()
    rconn.close()

    run_batches(
        railway_url, founded_year_rows,
        "UPDATE companies AS c SET founded_year = v.yr FROM (VALUES %s) AS v(domain, yr) "
        "WHERE c.domain = v.domain AND c.founded_year IS NULL",
        "(%s, %s)", "founded_year",
    )
    run_batches(
        railway_url, naics_rows,
        "UPDATE companies AS c SET naics_code = v.nc FROM (VALUES %s) AS v(domain, nc) "
        "WHERE c.domain = v.domain AND c.naics_code IS NULL",
        "(%s, %s)", "naics_code",
    )
    run_batches(
        railway_url, country_rows,
        "UPDATE companies AS c SET country = v.ctry FROM (VALUES %s) AS v(domain, ctry) "
        "WHERE c.domain = v.domain",
        "(%s, %s)", "country",
    )
    run_batches(
        railway_url, domain_status_rows,
        "UPDATE companies AS c SET domain_status = v.st, domain_checked_at = v.checked "
        "FROM (VALUES %s) AS v(domain, st, checked) WHERE c.domain = v.domain",
        "(%s, %s, %s)", "domain_status",
    )

    print("\nDone.")


if __name__ == "__main__":
    main()
