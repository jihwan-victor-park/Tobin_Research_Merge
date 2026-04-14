"""
Crunchbase Bulk Import — filters organizations.parquet and imports matching
companies into data/startups.db.

Filters applied (in order):
  1. roles contains 'company'       — exclude pure investors/funds
  2. status in ['operating', 'ipo'] — exclude closed and acquired companies
  3. founded_on year >= 2015        — emerging startups only
  4. name is not null               — basic data quality
  5. short_description OR total_funding_usd not null — exclude empty shells

After filtering, joins organization_descriptions.parquet on uuid for long
descriptions, then upserts in batches of 10,000 using bulk_upsert().

Does NOT run automatically — prints row count after filtering and asks for
confirmation before writing anything to the database.
"""

import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.db import bulk_upsert, get_connection, get_stats, init_db

ROOT = Path(__file__).resolve().parent.parent
ORGS_PATH = ROOT / "organizations.parquet"
DESCS_PATH = ROOT / "organization_descriptions.parquet"
BATCH_SIZE = 10_000
SOURCE = "crunchbase"

AI_KEYWORDS = [
    "artificial intelligence",
    "machine learning",
    "large language model",
    "llm",
    "generative ai",
    "generative",
    "gpt",
    "neural network",
    "deep learning",
    "nlp",
    "natural language processing",
    "computer vision",
    "data science",
    "autonomous",
    "robotics",
    "predictive",
    "recommendation engine",
]

# Pre-compiled regex pattern — much faster than per-row re.search at 700k rows
AI_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(kw) for kw in AI_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def load_and_filter() -> pd.DataFrame:
    """Load organizations.parquet, apply all filters, return filtered DataFrame."""
    print("Loading organizations.parquet ...")
    df = pd.read_parquet(ORGS_PATH)
    print(f"  Total rows: {len(df):,}")

    # Filter 1: roles contains 'company'
    df = df[df["roles"].str.contains("company", na=False)]
    print(f"  After roles contains 'company'          : {len(df):,}")

    # Filter 2: status operating or ipo
    df = df[df["status"].isin(["operating", "ipo"])]
    print(f"  After status in [operating, ipo]        : {len(df):,}")

    # Filter 3: founded_on year >= 2015
    df["founded_year"] = pd.to_datetime(df["founded_on"], errors="coerce").dt.year
    df = df[df["founded_year"] >= 2015]
    print(f"  After founded_on year >= 2015           : {len(df):,}")

    # Filter 4: name not null
    df = df[df["name"].notna()]
    print(f"  After name not null                     : {len(df):,}")

    # Filter 5: short_description or total_funding_usd not null
    df = df[df["short_description"].notna() | df["total_funding_usd"].notna()]
    print(f"  After desc or funding not null          : {len(df):,}")

    return df


def join_descriptions(df: pd.DataFrame) -> pd.DataFrame:
    """Left-join long descriptions from organization_descriptions.parquet on uuid."""
    print("\nLoading organization_descriptions.parquet ...")
    descs = pd.read_parquet(DESCS_PATH, columns=["uuid", "description"])
    print(f"  Descriptions rows: {len(descs):,}")

    df = df.merge(descs[["uuid", "description"]], on="uuid", how="left")
    matched = df["description"].notna().sum()
    print(f"  Matched long descriptions: {matched:,} / {len(df):,}")
    return df


def detect_ai_vectorized(df: pd.DataFrame) -> pd.Series:
    """
    Vectorized AI detection — combine short_description + category_list into
    one text column and apply a single compiled regex. Much faster than per-row.
    """
    text = (
        df["short_description"].fillna("") + " " +
        df["category_list"].fillna("") + " " +
        df["category_groups_list"].fillna("")
    )
    return text.str.contains(AI_PATTERN, regex=True)


def normalize_row(row) -> dict:
    """Map a single DataFrame row to our shared schema."""
    # Location: city, region, country
    location_parts = [
        str(v) for v in [row.get("city"), row.get("region"), row.get("country_code")]
        if v and str(v) != "nan"
    ]
    location = ", ".join(location_parts) or None

    # Tags: split category_list comma-separated string
    raw_tags = row.get("category_list") or ""
    tags = [t.strip() for t in str(raw_tags).split(",") if t.strip() and raw_tags] if raw_tags else []

    # Industries: split category_groups_list
    raw_industries = row.get("category_groups_list") or ""
    industries = [t.strip() for t in str(raw_industries).split(",") if t.strip() and raw_industries] if raw_industries else []

    # Employee count — Crunchbase stores as range string e.g. "51-100", "10000+"
    team_size_raw = row.get("employee_count")
    team_size = str(team_size_raw) if team_size_raw and str(team_size_raw) != "nan" else None

    # Long description — prefer over short if available
    long_desc = row.get("description")
    short_desc = row.get("short_description")
    description = (str(long_desc) if long_desc and str(long_desc) != "nan" else
                   str(short_desc) if short_desc and str(short_desc) != "nan" else None)

    return {
        "name": row["name"],
        "description": description,
        "founded_year": int(row["founded_year"]) if not pd.isna(row.get("founded_year", float("nan"))) else None,
        "batch": None,
        "website": row.get("homepage_url") if str(row.get("homepage_url", "nan")) != "nan" else None,
        "uses_ai": bool(row.get("uses_ai", False)),
        "tags": tags,
        "industries": industries,
        "location": location,
        "team_size": team_size,
        "status": row.get("status"),
        "stage": None,
        "source": SOURCE,
        "extra": {
            k: str(v) for k, v in {
                "cb_url": row.get("cb_url"),
                "linkedin_url": row.get("linkedin_url"),
                "twitter_url": row.get("twitter_url"),
                "total_funding_usd": row.get("total_funding_usd"),
                "total_funding_currency_code": row.get("total_funding_currency_code"),
                "num_funding_rounds": row.get("num_funding_rounds"),
                "last_funding_on": row.get("last_funding_on"),
                "domain": row.get("domain"),
            }.items()
            if v is not None and str(v) != "nan"
        },
    }


def main():
    # Step 1: Filter
    df = load_and_filter()

    # Step 2: Join descriptions
    df = join_descriptions(df)

    # Step 3: Vectorized AI detection
    print("\nRunning AI detection ...")
    df["uses_ai"] = detect_ai_vectorized(df)
    ai_count = df["uses_ai"].sum()
    print(f"  Uses AI: {ai_count:,} ({ai_count / len(df) * 100:.1f}%)")

    # Step 4: Estimate time and ask for confirmation
    estimated_seconds = len(df) / 10_000 * 2  # rough: ~2s per 10k batch
    print(f"\n{'=' * 50}")
    print(f"  Ready to import")
    print(f"  Rows to import  : {len(df):,}")
    print(f"  Batch size      : {BATCH_SIZE:,}")
    print(f"  Estimated time  : ~{estimated_seconds:.0f}s ({estimated_seconds/60:.1f} min)")
    print(f"  Target database : data/startups.db")
    print(f"{'=' * 50}")

    answer = input("\nProceed with import? [y/N] ").strip().lower()
    if answer != "y":
        print("Import cancelled.")
        sys.exit(0)

    # Step 5: Bulk insert in batches
    print(f"\nImporting {len(df):,} rows in batches of {BATCH_SIZE:,} ...")
    conn = get_connection()
    init_db(conn)

    start = time.time()
    total_inserted = 0
    rows = df.itertuples(index=False)
    batch = []

    for i, row in enumerate(df.itertuples(index=False), 1):
        batch.append(normalize_row(row._asdict()))

        if len(batch) >= BATCH_SIZE:
            bulk_upsert(conn, batch)
            conn.commit()
            total_inserted += len(batch)
            elapsed = time.time() - start
            rate = total_inserted / elapsed
            remaining = (len(df) - total_inserted) / rate if rate else 0
            print(f"  {total_inserted:>8,} / {len(df):,} inserted "
                  f"| {elapsed:.0f}s elapsed | ~{remaining:.0f}s remaining")
            batch = []

    # Final partial batch
    if batch:
        bulk_upsert(conn, batch)
        conn.commit()
        total_inserted += len(batch)

    elapsed = time.time() - start
    conn.close()

    # Step 6: Final summary
    print(f"\n{'=' * 50}")
    print(f"  Import complete")
    print(f"  Rows processed  : {len(df):,}")
    print(f"  Rows inserted   : {total_inserted:,}")
    print(f"  Uses AI         : {ai_count:,} ({ai_count / len(df) * 100:.1f}%)")
    print(f"  Time taken      : {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"{'=' * 50}")

    conn = get_connection()
    get_stats(conn)
    conn.close()


if __name__ == "__main__":
    main()