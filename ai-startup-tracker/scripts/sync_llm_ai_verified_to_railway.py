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
    # Railway's proxy drops long-lived connections after a few minutes even
    # mid-transfer (observed at both ~70K and ~180K rows in — not a fixed row
    # count, just time-based). Reconnect and retry the current batch rather
    # than dying and forcing a full restart from row 0.
    max_retries = 8
    i = 0
    while i < len(rows):
        chunk = rows[i : i + args.batch]
        for attempt in range(1, max_retries + 1):
            try:
                psycopg2.extras.execute_values(rcur, update_sql, chunk, template="(%s, %s)")
                rconn.commit()
                break
            except psycopg2.OperationalError as e:
                print(f"  connection dropped at row {i:,} (retry {attempt}/{max_retries}): {e}", flush=True)
                try:
                    rconn.close()
                except Exception:
                    pass
                import time
                time.sleep(3)
                rconn = psycopg2.connect(railway_url)
                rcur = rconn.cursor()
        else:
            sys.exit(
                f"Giving up after {max_retries} reconnect attempts at row {i:,}/{len(rows):,}. "
                "Re-run --apply to resume — UPDATEs are idempotent, already-synced rows are a no-op."
            )
        i += args.batch
        print(f"  synced ~{min(i, len(rows)):,}/{len(rows):,}", flush=True)

    rcur.execute("SELECT COUNT(*) FROM companies WHERE llm_ai_verified IS NOT NULL")
    print(f"\nRailway companies with llm_ai_verified set now: {rcur.fetchone()[0]:,}")

    lcur.close(); rcur.close(); lconn.close(); rconn.close()


if __name__ == "__main__":
    main()
