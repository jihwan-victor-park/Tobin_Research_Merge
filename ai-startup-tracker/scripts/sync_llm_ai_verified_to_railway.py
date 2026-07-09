"""Push `companies.llm_ai_verified` values from local -> Railway.

Companion to diff_sync_companies_to_railway.py, but for UPDATEing an existing
column on rows that already exist on both DBs, rather than inserting new rows.
The classify_pb_ai_with_llm.py batch job wrote its verdicts to the local DB
only — Railway's production DB is separate and needs this to pick them up.

Match key: domain (UNIQUE on both DBs, same convention as diff_sync).

Run:
  export RAILWAY_DATABASE_URL="$(railway variables --service Postgres --kv \
    | grep '^DATABASE_PUBLIC_URL=' | cut -d= -f2-)"
  python3 scripts/sync_llm_ai_verified_to_railway.py            # dry-run (counts only)
  python3 scripts/sync_llm_ai_verified_to_railway.py --apply    # actually update
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

LOCAL_URL = os.getenv("DATABASE_URL")
RAILWAY_URL = os.getenv("RAILWAY_DATABASE_URL")


def _guard(url: str | None, label: str) -> str:
    if not url:
        sys.exit(f"{label} not set")
    if "localhost" in url or "127.0.0.1" in url:
        if label == "RAILWAY_DATABASE_URL":
            sys.exit("RAILWAY_DATABASE_URL looks like localhost — paste the Railway URL")
    if "railway.internal" in url:
        sys.exit("Use DATABASE_PUBLIC_URL, not the internal URL")
    return url


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Update (default: dry-run)")
    ap.add_argument("--batch", type=int, default=5000, help="Update batch size")
    args = ap.parse_args()

    local_url = _guard(LOCAL_URL, "DATABASE_URL")
    railway_url = _guard(RAILWAY_URL, "RAILWAY_DATABASE_URL")

    lconn = psycopg2.connect(local_url)
    rconn = psycopg2.connect(railway_url)
    lcur = lconn.cursor()
    rcur = rconn.cursor()

    # Confirm the column exists on Railway (it should — init_db() migrates it
    # on deploy) before doing anything else.
    rcur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'companies' AND column_name = 'llm_ai_verified'"
    )
    if rcur.fetchone() is None:
        sys.exit("Railway companies table has no llm_ai_verified column — deploy hasn't migrated yet?")

    print("Reading local llm_ai_verified values (domain-keyed)…", flush=True)
    lcur.execute(
        "SELECT domain, llm_ai_verified FROM companies "
        "WHERE llm_ai_verified IS NOT NULL AND domain IS NOT NULL"
    )
    rows = [(domain.lower(), is_ai) for domain, is_ai in lcur.fetchall()]
    no_domain = lcur.rowcount  # will refine below
    lcur.execute(
        "SELECT COUNT(*) FROM companies WHERE llm_ai_verified IS NOT NULL AND domain IS NULL"
    )
    skipped_no_domain = lcur.fetchone()[0]

    print(f"  local rows with llm_ai_verified set: {len(rows) + skipped_no_domain:,}")
    print(f"  domain-matchable: {len(rows):,}   skipped (no domain): {skipped_no_domain:,}")

    if not args.apply:
        # Dry-run: report how many of those domains actually exist on Railway
        # and how many already have a matching value (no-op) vs would change.
        rcur.execute("SELECT domain, llm_ai_verified FROM companies WHERE domain IS NOT NULL")
        rail_map = {d.lower(): v for d, v in rcur.fetchall()}
        matched = sum(1 for d, _ in rows if d in rail_map)
        would_change = sum(1 for d, v in rows if d in rail_map and rail_map[d] != v)
        print(f"  domains found on Railway: {matched:,}")
        print(f"  rows that would actually change a value: {would_change:,}")
        print("(dry-run — re-run with --apply to update)")
        return

    print(f"\nUpdating Railway in batches of {args.batch}…", flush=True)
    update_sql = """
        UPDATE companies AS c
        SET llm_ai_verified = v.is_ai
        FROM (VALUES %s) AS v(domain, is_ai)
        WHERE c.domain = v.domain
    """
    updated = 0
    for i in range(0, len(rows), args.batch):
        chunk = rows[i : i + args.batch]
        psycopg2.extras.execute_values(rcur, update_sql, chunk, template="(%s, %s)")
        rconn.commit()
        updated += rcur.rowcount if rcur.rowcount and rcur.rowcount > 0 else len(chunk)
        print(f"  synced ~{min(i + args.batch, len(rows)):,}/{len(rows):,}", flush=True)

    rcur.execute("SELECT COUNT(*) FROM companies WHERE llm_ai_verified IS NOT NULL")
    print(f"\nRailway companies with llm_ai_verified set now: {rcur.fetchone()[0]:,}")

    lcur.close(); rcur.close(); lconn.close(); rconn.close()


if __name__ == "__main__":
    main()
