"""
Enrich companies table from Revelio company_mapping parquet files.

Adds/fills:
  - founded_year  (where NULL in our DB and Revelio has a reasonable value)
  - naics_code    (new column, added if missing)

Matches on domain (cleaned URL). Only updates; never inserts new companies.
"""
from __future__ import annotations
import os
import re
import sys
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

def _db_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("RAILWAY_URL")
    if not url:
        raise RuntimeError("Set DATABASE_URL or RAILWAY_URL env var")
    return url
REVELIO_FILES = [
    "/Users/alastairpage/Downloads/revelio_company_mapping-000000.parquet",
    "/Users/alastairpage/Downloads/revelio_company_mapping-000001.parquet",
    "/Users/alastairpage/Downloads/revelio_company_mapping-000002.parquet",
]
YEAR_MIN, YEAR_MAX = 1900, 2025


def clean_domain(u) -> str | None:
    if pd.isna(u):
        return None
    u = str(u).lower().strip()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.split("/")[0].strip() or None


def load_revelio() -> pd.DataFrame:
    print("Loading Revelio company_mapping shards...")
    dfs = []
    for path in REVELIO_FILES:
        df = pd.read_parquet(path, columns=["url", "year_founded", "naics_code"])
        dfs.append(df)
        print(f"  {path.split('/')[-1]}: {len(df):,} rows")
    combined = pd.concat(dfs, ignore_index=True)

    # Decode any bytes columns
    for col in ["year_founded", "naics_code"]:
        combined[col] = combined[col].apply(
            lambda x: x.decode() if isinstance(x, bytes) else x
        )

    combined["year_founded"] = pd.to_numeric(combined["year_founded"], errors="coerce")
    combined["domain_clean"] = combined["url"].apply(clean_domain)

    # Filter to rows that have at least one useful field
    useful = combined[
        combined["domain_clean"].notna()
        & (combined["year_founded"].notna() | combined["naics_code"].notna())
    ].copy()

    # Reasonable year range only
    mask_yr = useful["year_founded"].notna()
    useful.loc[mask_yr & ~useful["year_founded"].between(YEAR_MIN, YEAR_MAX), "year_founded"] = None

    # Deduplicate by domain — prefer rows with more data
    useful["_score"] = useful["year_founded"].notna().astype(int) + useful["naics_code"].notna().astype(int)
    useful = (
        useful.sort_values("_score", ascending=False)
        .drop_duplicates("domain_clean", keep="first")
        .drop(columns=["_score", "url"])
    )

    print(f"Revelio: {len(useful):,} unique domains with data "
          f"({useful['year_founded'].notna().sum():,} have year, "
          f"{useful['naics_code'].notna().sum():,} have NAICS)")
    return useful


def ensure_naics_column(conn):
    exists = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='companies' AND column_name='naics_code'"
    )).scalar()
    if not exists:
        conn.execute(text("ALTER TABLE companies ADD COLUMN naics_code VARCHAR(10)"))
        print("Added naics_code column to companies table.")


NON_CB_PB_FILTER = (
    "verification_status NOT IN ('verified_cb', 'verified_pb', 'verified_cb_pb')"
)


def main(dry_run: bool = False, non_cb_pb_only: bool = False):
    revelio = load_revelio()
    engine = create_engine(_db_url())

    # Pull our companies that either lack founded_year or lack naics_code
    scope_note = " (scoped to non-CB/PB companies only)" if non_cb_pb_only else ""
    print(f"\nFetching company domains{scope_note}...")
    fetch_sql = "SELECT id, domain, founded_year FROM companies WHERE domain IS NOT NULL"
    if non_cb_pb_only:
        fetch_sql += f" AND {NON_CB_PB_FILTER}"
    with engine.connect() as conn:
        rows = conn.execute(text(fetch_sql)).mappings().all()

    our_df = pd.DataFrame(rows)[["id", "domain", "founded_year"]]
    our_df["domain_lower"] = our_df["domain"].str.lower().str.strip()
    print(f"Our companies with domain: {len(our_df):,}")

    # Check naics_code column existence before merge
    with engine.connect() as conn:
        has_naics = conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='companies' AND column_name='naics_code'"
        )).scalar()

    if has_naics:
        with engine.connect() as conn:
            naics_rows = conn.execute(text(
                "SELECT id, naics_code FROM companies WHERE domain IS NOT NULL"
            )).mappings().all()
        naics_df = pd.DataFrame(naics_rows)
        our_df = our_df.merge(naics_df, on="id", how="left")
    else:
        our_df["naics_code"] = None

    # Join to Revelio
    merged = our_df.merge(
        revelio.rename(columns={
            "year_founded": "rev_year",
            "naics_code": "rev_naics",
        }),
        left_on="domain_lower",
        right_on="domain_clean",
        how="inner",
    )
    print(f"Matched: {len(merged):,} companies")

    # Determine what to update
    to_update_year = merged[
        merged["founded_year"].isna() & merged["rev_year"].notna()
    ][["id", "rev_year"]].copy()

    to_update_naics = merged[
        merged["naics_code"].isna() & merged["rev_naics"].notna()
    ][["id", "rev_naics"]].copy()

    print(f"\nWill update:")
    print(f"  founded_year (NULL -> Revelio value): {len(to_update_year):,}")
    print(f"  naics_code   (NULL -> Revelio value): {len(to_update_naics):,}")

    if dry_run:
        print("\n(dry run — no changes written)")
        if not to_update_year.empty:
            print("Sample year updates:")
            print(to_update_year.head(5).to_string(index=False))
        if not to_update_naics.empty:
            print("Sample NAICS updates:")
            print(to_update_naics.head(5).to_string(index=False))
        return

    with engine.begin() as conn:
        ensure_naics_column(conn)

        # Bulk update founded_year via temp table
        if not to_update_year.empty:
            print(f"\nUpdating {len(to_update_year):,} founded_year values...")
            conn.execute(text(
                "CREATE TEMP TABLE _rev_year (id INTEGER, yr INTEGER) ON COMMIT DROP"
            ))
            conn.execute(
                text("INSERT INTO _rev_year VALUES (:id, :yr)"),
                [{"id": int(r.id), "yr": int(r.rev_year)} for r in to_update_year.itertuples()],
            )
            result = conn.execute(text(
                "UPDATE companies c SET founded_year = t.yr "
                "FROM _rev_year t WHERE c.id = t.id AND c.founded_year IS NULL"
            ))
            print(f"  founded_year: {result.rowcount:,} updated")

        # Bulk update naics_code — batch inserts to avoid proxy timeout
        if not to_update_naics.empty:
            print(f"\nUpdating {len(to_update_naics):,} naics_code values...")
            conn.execute(text(
                "CREATE TEMP TABLE _rev_naics (id INTEGER, nc VARCHAR(10)) ON COMMIT DROP"
            ))
            records = [{"id": int(r.id), "nc": str(r.rev_naics)} for r in to_update_naics.itertuples()]
            BATCH = 2_000
            for i in range(0, len(records), BATCH):
                conn.execute(text("INSERT INTO _rev_naics VALUES (:id, :nc)"), records[i:i + BATCH])
                if i % 20_000 == 0:
                    print(f"  inserted {min(i+BATCH, len(records)):,}/{len(records):,}...")
            result = conn.execute(text(
                "UPDATE companies c SET naics_code = t.nc "
                "FROM _rev_naics t WHERE c.id = t.id AND c.naics_code IS NULL"
            ))
            print(f"  naics_code: {result.rowcount:,} updated")

    # Summary
    base_where = [NON_CB_PB_FILTER] if non_cb_pb_only else []
    def _count(extra: str | None = None) -> int:
        clauses = base_where + ([extra] if extra else [])
        where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with engine.connect() as conn:
            return conn.execute(text(f"SELECT COUNT(*) FROM companies{where_sql}")).scalar()

    has_year = _count("founded_year IS NOT NULL")
    total = _count()
    has_naics = _count("naics_code IS NOT NULL")

    print(f"\n✓ Done.{scope_note}")
    print(f"  founded_year coverage: {has_year:,} / {total:,} ({has_year/total*100:.1f}%)")
    print(f"  naics_code coverage:   {has_naics:,} / {total:,} ({has_naics/total*100:.1f}%)")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    non_cb_pb_only = "--non-cb-pb-only" in sys.argv
    main(dry_run=dry_run, non_cb_pb_only=non_cb_pb_only)
