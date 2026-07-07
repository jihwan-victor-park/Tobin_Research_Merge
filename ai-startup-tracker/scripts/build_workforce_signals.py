"""
Build workforce_signals table from Revelio individual_positions shards.

Join chain:
  our companies (domain) → company_mapping (url→rcid) → positions (rcid→user_id)

Stores one row per person-position at a company in our DB with seniority >= 4.
user_id is retained so we can join to individual_user / individual_user_education
files when they become available.

Run:
  python3 scripts/build_workforce_signals.py [--dry-run] [--shard 000083]
"""
from __future__ import annotations

import os
import re
import sys
import argparse
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

def _db_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("RAILWAY_URL")
    if not url:
        raise RuntimeError("Set DATABASE_URL or RAILWAY_URL env var")
    return url

COMPANY_MAPPING_FILES = [
    "/Users/alastairpage/Downloads/revelio_company_mapping-000000.parquet",
    "/Users/alastairpage/Downloads/revelio_company_mapping-000001.parquet",
    "/Users/alastairpage/Downloads/revelio_company_mapping-000002.parquet",
]

POSITIONS_FILES = [
    "/Users/alastairpage/Downloads/revelio_individual_positions-000075.parquet",
    "/Users/alastairpage/Downloads/revelio_individual_positions-000078.parquet",
    "/Users/alastairpage/Downloads/revelio_individual_positions-000083.parquet",
    "/Users/alastairpage/Downloads/revelio_individual_positions-000093.parquet",
    "/Users/alastairpage/Downloads/revelio_individual_positions-000110.parquet",
]

# Keep positions at or above senior individual contributor level
MIN_SENIORITY = 4

DDL = """
CREATE TABLE IF NOT EXISTS workforce_signals (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT       NOT NULL,
    rcid            BIGINT       NOT NULL,
    company_domain  VARCHAR(255) NOT NULL,
    role_k1500      VARCHAR(100),
    seniority       SMALLINT,
    startdate       DATE,
    enddate         DATE,
    country         VARCHAR(100),
    shard           VARCHAR(20)  NOT NULL,
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ws_domain  ON workforce_signals (company_domain);
CREATE INDEX IF NOT EXISTS ws_user    ON workforce_signals (user_id);
CREATE INDEX IF NOT EXISTS ws_rcid    ON workforce_signals (rcid);
CREATE UNIQUE INDEX IF NOT EXISTS ws_uniq ON workforce_signals (user_id, rcid, shard, COALESCE(startdate, '1900-01-01'));
"""


def clean_domain(u) -> str | None:
    if pd.isna(u):
        return None
    u = str(u).lower().strip()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.split("/")[0].strip() or None


def build_rcid_lookup(our_domains: set[str]) -> dict[int, str]:
    """Return {rcid: domain} for rcids whose URL matches one of our domains."""
    print("Loading company_mapping shards...")
    chunks = []
    for path in COMPANY_MAPPING_FILES:
        df = pd.read_parquet(path, columns=["rcid", "url"])
        df["domain_clean"] = df["url"].apply(clean_domain)
        df = df[df["domain_clean"].isin(our_domains) & df["rcid"].notna()].copy()
        chunks.append(df)
        print(f"  {path.split('/')[-1]}: {len(df):,} matched")

    combined = pd.concat(chunks, ignore_index=True)
    # One rcid can appear multiple times (child/parent); keep first
    combined = combined.drop_duplicates("rcid")
    lookup = dict(zip(combined["rcid"].astype(int), combined["domain_clean"]))
    print(f"  → {len(lookup):,} unique rcids mapped to our companies\n")
    return lookup


def ensure_table(engine):
    with engine.begin() as conn:
        conn.execute(text(DDL))
    print("workforce_signals table ready.")


def already_loaded_shards(engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT DISTINCT shard FROM workforce_signals")).fetchall()
    return {r[0] for r in rows}


def process_shard(path: str, rcid_lookup: dict[int, str], engine, dry_run: bool) -> int:
    shard_name = path.split("/")[-1].replace(".parquet", "").split("-")[-1]
    print(f"\nProcessing shard {shard_name}...")

    df = pd.read_parquet(path, columns=[
        "user_id", "rcid", "role_k1500", "seniority",
        "startdate", "enddate", "country",
    ])
    print(f"  Loaded {len(df):,} rows")

    # Filter to seniority >= MIN_SENIORITY
    df = df[df["seniority"] >= MIN_SENIORITY].copy()
    print(f"  After seniority>={MIN_SENIORITY}: {len(df):,} rows")

    # Filter to our companies
    df = df[df["rcid"].notna()].copy()
    df["rcid_int"] = df["rcid"].astype(int)
    df = df[df["rcid_int"].isin(rcid_lookup)].copy()
    print(f"  After rcid filter (our companies): {len(df):,} rows")

    if df.empty:
        print("  Nothing to insert.")
        return 0

    df["company_domain"] = df["rcid_int"].map(rcid_lookup)
    df["shard"] = shard_name
    df["user_id"] = df["user_id"].astype("Int64")

    # Normalise dates
    for col in ["startdate", "enddate"]:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    records = df[[
        "user_id", "rcid_int", "company_domain",
        "role_k1500", "seniority", "startdate", "enddate", "country", "shard",
    ]].rename(columns={"rcid_int": "rcid"}).to_dict(orient="records")

    if dry_run:
        print(f"  DRY RUN — would insert {len(records):,} rows")
        print("  Sample:")
        for r in records[:3]:
            print(f"    {r}")
        return len(records)

    # Batch upsert in chunks of 5000
    BATCH = 5_000
    inserted = 0
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TEMP TABLE _ws_stage ("
            "  user_id BIGINT, rcid BIGINT, company_domain VARCHAR(255),"
            "  role_k1500 VARCHAR(100), seniority SMALLINT,"
            "  startdate DATE, enddate DATE, country VARCHAR(100), shard VARCHAR(20)"
            ") ON COMMIT DROP"
        ))
        for i in range(0, len(records), BATCH):
            batch = records[i:i + BATCH]
            conn.execute(text(
                "INSERT INTO _ws_stage VALUES "
                "(:user_id,:rcid,:company_domain,:role_k1500,:seniority,"
                ":startdate,:enddate,:country,:shard)"
            ), batch)

        result = conn.execute(text("""
            INSERT INTO workforce_signals
                (user_id, rcid, company_domain, role_k1500, seniority,
                 startdate, enddate, country, shard)
            SELECT user_id, rcid, company_domain, role_k1500, seniority,
                   startdate, enddate, country, shard
            FROM _ws_stage
            ON CONFLICT (user_id, rcid, shard, COALESCE(startdate, '1900-01-01'))
            DO NOTHING
        """))
        inserted = result.rowcount

    print(f"  Inserted {inserted:,} rows (skipped {len(records)-inserted:,} duplicates)")
    return inserted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--shard", help="Process only this shard number (e.g. 000083)")
    args = parser.parse_args()

    engine = create_engine(_db_url())

    if not args.dry_run:
        ensure_table(engine)
        done_shards = already_loaded_shards(engine)
        if done_shards:
            print(f"Already loaded shards: {done_shards}")
    else:
        done_shards = set()

    # Pull our company domains in pages to avoid proxy timeout on 978K row fetch
    print("Fetching our company domains from Railway...")
    our_domains: set[str] = set()
    PAGE = 50_000
    offset = 0
    with engine.connect() as conn:
        while True:
            rows = conn.execute(text(
                f"SELECT domain FROM companies WHERE domain IS NOT NULL "
                f"ORDER BY id LIMIT {PAGE} OFFSET {offset}"
            )).fetchall()
            if not rows:
                break
            our_domains.update(r[0].lower().strip() for r in rows)
            offset += PAGE
            print(f"  fetched {offset:,}...")
    print(f"  {len(our_domains):,} domains in our DB\n")

    rcid_lookup = build_rcid_lookup(our_domains)

    files = POSITIONS_FILES
    if args.shard:
        files = [f for f in files if args.shard in f]
        if not files:
            print(f"No shard matching '{args.shard}' found in POSITIONS_FILES")
            sys.exit(1)

    total = 0
    for path in files:
        shard_name = path.split("/")[-1].replace(".parquet", "").split("-")[-1]
        if shard_name in done_shards:
            print(f"Skipping {shard_name} (already loaded)")
            continue
        total += process_shard(path, rcid_lookup, engine, dry_run=args.dry_run)

    print(f"\n✓ Done. Total rows inserted: {total:,}")

    if not args.dry_run:
        with engine.connect() as conn:
            n = conn.execute(text("SELECT COUNT(*) FROM workforce_signals")).scalar()
            domains = conn.execute(text("SELECT COUNT(DISTINCT company_domain) FROM workforce_signals")).scalar()
        print(f"  workforce_signals total: {n:,} rows across {domains:,} companies")


if __name__ == "__main__":
    main()
