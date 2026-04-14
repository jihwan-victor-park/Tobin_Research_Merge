"""
YC Scraper — queries the YC Algolia API directly and maps fields in Python.

Why Algolia instead of scraping HTML:
  YC's companies page is JavaScript-rendered, so requests only returns an
  empty shell. YC uses Algolia for their search — querying it directly gives
  us clean, structured JSON without any HTML parsing.

Why no Claude for normalization:
  Algolia already returns structured data. Direct Python mapping is faster,
  cheaper, and more reliable than asking an LLM to reformat clean JSON.
  Claude is reserved for tasks that actually need language understanding
  (e.g. classifying ambiguous descriptions).

Pagination strategy:
  Algolia caps results at 1000 per query regardless of hitsPerPage.
  To get all 4000+ companies we query per-batch (e.g. "Winter 2024"),
  collect results, then deduplicate by company name.
"""

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

# Allow importing db from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.db import get_connection, init_db, insert_company, get_stats

# --- Config ---
# Credentials passed as query parameters (not headers) as required by this endpoint
ALGOLIA_URL = (
    "https://45bwzj1sgc-dsn.algolia.net/1/indexes/*/queries"
    "?x-algolia-application-id=45BWZJ1SGC"
    "&x-algolia-api-key=NzllNTY5MzJiZGM2OTY2ZTQwMDEzOTNhYWZiZGRjODlhYzVkNjBmOGRjNzJiMWM4ZTU0ZDlhYTZjOTJiMjlhMWFuYWx5dGljc1RhZ3M9eWNkYyZyZXN0cmljdEluZGljZXM9WUNDb21wYW55X3Byb2R1Y3Rpb24lMkNZQ0NvbXBhbnlfQnlfTGF1bmNoX0RhdGVfcHJvZHVjdGlvbiZ0YWdGaWx0ZXJzPSU1QiUyMnljZGNfcHVibGljJTIyJTVE"
)
ALGOLIA_HEADERS = {
    "Content-Type": "application/json",
}
HITS_PER_PAGE = 1000
OUTPUT_FILE = "yc_companies.json"

# Tightened keyword list — word-boundary matched to avoid false positives
# e.g. "ml" removed because it matches "marketplace", "model", etc.
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
    "ai",
]

# Map Algolia's full season names to short batch codes e.g. "Winter 2009" → "W09"
SEASON_PREFIX = {
    "winter": "W",
    "spring": "Sp",
    "summer": "S",
    "fall": "F",
}

# All YC batch seasons and year range to query
SEASONS = ["Winter", "Summer"]
BATCH_YEAR_START = 2005
BATCH_YEAR_END = 2026  # update annually as new batches are added


def fetch_batch(batch_name: str) -> list[dict]:
    """
    Query Algolia filtered to a single batch e.g. "Winter 2024".
    Algolia filter syntax: filters=batch:"Winter 2024"
    """
    encoded_filter = quote(f'batch:"{batch_name}"')
    params = f"hitsPerPage={HITS_PER_PAGE}&page=0&filters={encoded_filter}"
    body = {
        "requests": [
            {
                "indexName": "YCCompany_production",
                "params": params,
            }
        ]
    }
    response = requests.post(ALGOLIA_URL, headers=ALGOLIA_HEADERS, json=body, timeout=15)
    response.raise_for_status()
    data = response.json()
    return data["results"][0]["hits"]


def fetch_all_companies() -> list[dict]:
    """
    Fetch all YC companies by querying each batch individually.
    Deduplicates by objectID (Algolia's unique company identifier).
    """
    seen_ids: set[str] = set()
    all_hits: list[dict] = []

    batches = [
        f"{season} {year}"
        for year in range(BATCH_YEAR_START, BATCH_YEAR_END + 1)
        for season in SEASONS
    ]

    for batch_name in batches:
        hits = fetch_batch(batch_name)
        if not hits:
            continue  # batch doesn't exist or is empty — skip silently

        new_hits = [h for h in hits if h["objectID"] not in seen_ids]
        seen_ids.update(h["objectID"] for h in new_hits)
        all_hits.extend(new_hits)
        print(f"  {batch_name}: {len(hits)} hits, {len(new_hits)} new (total: {len(all_hits)})")

        # Be polite — small delay between requests
        time.sleep(0.3)

    return all_hits


def normalize_batch(raw_batch: str | None) -> str | None:
    """
    Convert Algolia's full batch name to short form.
    "Winter 2009" → "W09", "Summer 2013" → "S13"
    Returns raw value as-is if format is unrecognised.
    """
    if not raw_batch:
        return None
    parts = raw_batch.strip().split()
    if len(parts) != 2:
        return raw_batch
    season, year = parts[0].lower(), parts[1]
    prefix = SEASON_PREFIX.get(season)
    if not prefix or len(year) != 4:
        return raw_batch
    return f"{prefix}{year[2:]}"  # e.g. "W09"


def detect_ai(hit: dict) -> bool:
    """
    Return True if any AI keyword appears in one_liner, long_description, or tags.
    Uses word-boundary matching (\\b) to avoid substring false positives
    e.g. 'ml' matching 'marketplace', 'nlp' matching 'help'.
    """
    text = " ".join(filter(None, [
        hit.get("one_liner", ""),
        hit.get("long_description", ""),
        " ".join(hit.get("tags", [])),
    ]))

    return any(
        re.search(r"\b" + re.escape(keyword) + r"\b", text, re.IGNORECASE)
        for keyword in AI_KEYWORDS
    )


def extract_founded_year(hit: dict) -> int | None:
    """
    Attempt to extract a founding year from long_description using regex.

    Algolia has no dedicated founded_year field — launched_at is the YC profile
    creation date, not the founding date, so it's unreliable. Instead we look for
    year mentions near founding language in the description, e.g.:
      "Founded in August of 2008..."
      "We were founded in 2015..."
      "Started in 2012..."

    Returns None if no confident match is found — a null is honest, a wrong date
    is harmful to the dataset.
    """
    description = hit.get("long_description", "") or ""

    # Look for a 4-digit year (1990–2030) preceded by founding language
    match = re.search(
        r"(?:founded|incorporated|established|started|launched)\b.{0,40}?\b((?:19|20)\d{2})\b",
        description,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1))

    return None


def normalize_hit(hit: dict) -> dict:
    """Map a raw Algolia hit to our schema using direct Python field mapping."""
    founded_year = extract_founded_year(hit)

    return {
        "name": hit.get("name"),
        "description": hit.get("one_liner"),
        "founded_year": founded_year,
        "batch": normalize_batch(hit.get("batch")),
        "website": hit.get("website"),
        "uses_ai": detect_ai(hit),
        # Bonus fields — useful for filtering and enrichment later
        "location": hit.get("all_locations"),
        "team_size": hit.get("team_size"),
        "status": hit.get("status"),
        "stage": hit.get("stage"),
        "tags": hit.get("tags", []),
        "industries": hit.get("industries", []),
        "subindustry": hit.get("subindustry"),
    }


def save_results(companies: list[dict], output_file: str) -> None:
    """Save the list of companies to a JSON file."""
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(companies, f, indent=2, ensure_ascii=False)


def main():
    # Step 1: Fetch all companies from Algolia, paginated by batch
    print("Fetching YC companies from Algolia API (by batch) ...")
    raw_hits = fetch_all_companies()
    print(f"\n  Total unique companies fetched: {len(raw_hits)}")

    if not raw_hits:
        print("No companies returned from Algolia. Exiting.")
        sys.exit(0)

    # Step 2: Normalize each hit with direct Python field mapping
    print("Normalizing records ...")
    companies = [normalize_hit(h) for h in raw_hits]

    # Step 3: Save results to JSON (kept as a flat-file backup)
    save_results(companies, OUTPUT_FILE)
    print(f"Saved JSON backup to {OUTPUT_FILE}")

    # Step 4: Write all companies to the database
    print("Writing to database ...")
    conn = get_connection()
    init_db(conn)
    for company in companies:
        insert_company(conn, {**company, "source": "yc"})
    conn.commit()
    conn.close()
    print(f"  Upserted {len(companies):,} records into data/startups.db")

    # Step 5: Print database stats
    conn = get_connection()
    get_stats(conn)
    conn.close()


if __name__ == "__main__":
    main()
