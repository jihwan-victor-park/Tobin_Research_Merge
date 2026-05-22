"""Non-destructive differential sync of `companies` from local → Railway.

Unlike scripts/sync_db_to_railway.sh (which does pg_restore --clean and REPLACES
the whole Railway DB), this only INSERTS companies that exist locally but not on
Railway. Railway-only rows (e.g. a collaborator's site_health / companies synced
from another machine) are left untouched.

Match key (mirrors the app's dedup):
  - if local.domain is non-null → match on domain (which is UNIQUE on both DBs)
  - else → match on normalized_name

Run:
  export RAILWAY_DATABASE_URL="$(railway variables --service Postgres --kv \
    | grep '^DATABASE_PUBLIC_URL=' | cut -d= -f2-)"
  python3 scripts/diff_sync_companies_to_railway.py            # dry-run (counts only)
  python3 scripts/diff_sync_companies_to_railway.py --apply    # actually insert
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

# Columns we copy. id/created_at are intentionally excluded so Railway assigns
# its own PK and timestamps (avoids PK collisions with Railway-only rows).
COLS = [
    "name", "domain", "normalized_name", "country", "city",
    "latitude", "longitude", "description", "founded_year", "team_size",
    "stage", "operating_status", "ai_score", "startup_score",
    "first_seen_at", "last_seen_at", "incubator_source",
    # These are NOT NULL on both DBs but the model defaults are Python-side
    # (not DB defaults), so a raw INSERT must carry them explicitly. We copy the
    # local values rather than re-stamping — preserves true first-seen history.
    "verification_status", "created_at", "updated_at",
]


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
    ap.add_argument("--apply", action="store_true", help="Insert (default: dry-run)")
    ap.add_argument("--batch", type=int, default=1000, help="Insert batch size")
    args = ap.parse_args()

    local_url = _guard(LOCAL_URL, "DATABASE_URL")
    railway_url = _guard(RAILWAY_URL, "RAILWAY_DATABASE_URL")

    lconn = psycopg2.connect(local_url)
    rconn = psycopg2.connect(railway_url)
    lcur = lconn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    rcur = rconn.cursor()

    # 1. Existing Railway keys.
    print("Reading Railway keys…", flush=True)
    rcur.execute("SELECT domain, normalized_name FROM companies;")
    rail_domains: set[str] = set()
    rail_names: set[str] = set()
    for domain, norm in rcur.fetchall():
        if domain:
            rail_domains.add(domain.lower())
        elif norm:
            rail_names.add(norm.lower())
    print(f"  Railway: {len(rail_domains):,} domains, {len(rail_names):,} domainless names")

    # 2. Local rows, stream, filter to those missing on Railway.
    print("Scanning local companies…", flush=True)
    lcur.execute(f"SELECT {', '.join(COLS)} FROM companies;")
    to_insert = []
    seen_new_domains: set[str] = set()
    seen_new_names: set[str] = set()
    for row in lcur:
        domain = (row.get("domain") or "").lower() or None
        norm = (row.get("normalized_name") or "").lower() or None
        if domain:
            if domain in rail_domains or domain in seen_new_domains:
                continue
            seen_new_domains.add(domain)
        elif norm:
            if norm in rail_names or norm in seen_new_names:
                continue
            seen_new_names.add(norm)
        else:
            continue  # no key at all — skip
        to_insert.append(tuple(row[c] for c in COLS))

    print(f"\nLocal-only companies to insert: {len(to_insert):,}")
    if not args.apply:
        print("(dry-run — re-run with --apply to insert)")
        return

    # 3. Batched insert. ON CONFLICT (domain) DO NOTHING guards the UNIQUE
    #    domain constraint against any race / case we missed.
    placeholders = "(" + ", ".join(["%s"] * len(COLS)) + ")"
    insert_sql = (
        f"INSERT INTO companies ({', '.join(COLS)}) VALUES %s "
        "ON CONFLICT (domain) DO NOTHING"
    )
    inserted = 0
    for i in range(0, len(to_insert), args.batch):
        chunk = to_insert[i : i + args.batch]
        psycopg2.extras.execute_values(rcur, insert_sql, chunk, template=placeholders)
        rconn.commit()
        inserted += len(chunk)
        print(f"  inserted {inserted:,}/{len(to_insert):,}", flush=True)

    # Final count.
    rcur.execute("SELECT COUNT(*) FROM companies;")
    print(f"\nRailway companies now: {rcur.fetchone()[0]:,}")

    lcur.close(); rcur.close(); lconn.close(); rconn.close()


if __name__ == "__main__":
    main()
