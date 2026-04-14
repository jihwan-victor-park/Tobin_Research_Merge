"""
Techstars Scraper — queries the Techstars Typesense API for all accelerator
portfolio companies and upserts them into the shared SQLite database.

Why Typesense instead of scraping HTML:
  Techstars' portfolio page is JS-rendered. Their search is powered by
  Typesense, which returns clean structured JSON — no HTML parsing needed.

API discovery:
  Found via browser DevTools Network tab. Filter by 'typesense' to see
  the search requests and extract the base URL and API key.
"""

import json
import re
import sys
import time
from pathlib import Path

import requests

# Allow importing db from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.db import get_connection, get_stats, init_db, insert_company

# --- Config ---
TYPESENSE_URL = "https://8gbms7c94riane0lp-1.a1.typesense.net/collections/companies/documents/search"
TYPESENSE_HEADERS = {
    "x-typesense-api-key": "0QKFSu4mIDX9UalfCNQN4qjg2xmukDE0",
}
PER_PAGE = 250
SOURCE = "techstars"

# Reused from yc_scraper — word-boundary matched to avoid false positives
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


def fetch_page(page: int) -> dict:
    """Fetch one page of Techstars accelerator companies from Typesense."""
    params = {
        "q": "",
        "query_by": "company_name,brief_description",
        "filter_by": "is_accelerator_company:=true",
        "per_page": PER_PAGE,
        "page": page,
    }
    response = requests.get(TYPESENSE_URL, headers=TYPESENSE_HEADERS, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def fetch_all_companies() -> list[dict]:
    """Paginate through all Typesense results until no hits are returned."""
    all_hits = []
    page = 1  # Typesense pages are 1-indexed

    while True:
        print(f"  Fetching page {page} ...")
        data = fetch_page(page)
        hits = [h["document"] for h in data.get("hits", [])]

        if not hits:
            print(f"  No hits on page {page} — pagination complete.")
            break

        all_hits.extend(hits)
        print(f"  Got {len(hits)} hits (total so far: {len(all_hits)} of {data.get('found', '?')})")

        # Stop if we've collected everything
        if len(all_hits) >= data.get("found", 0):
            break

        page += 1
        time.sleep(0.3)  # be polite

    return all_hits


def detect_ai(doc: dict) -> bool:
    """
    Return True if any AI keyword appears in brief_description or industry_vertical.
    Uses word-boundary matching to avoid false positives (e.g. 'nlp' in 'help').
    """
    text = " ".join(filter(None, [
        doc.get("brief_description", ""),
        " ".join(doc.get("industry_vertical", [])),
    ]))

    return any(
        re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE)
        for kw in AI_KEYWORDS
    )


def extract_founded_year(doc: dict) -> int | None:
    """
    Attempt to extract founding year from brief_description.
    Returns None if no reliable match — a null is honest, a wrong date corrupts data.
    """
    description = doc.get("brief_description", "") or ""
    match = re.search(
        r"(?:founded|incorporated|established|started|launched)\b.{0,40}?\b((?:19|20)\d{2})\b",
        description,
        re.IGNORECASE,
    )
    return int(match.group(1)) if match else None


def normalize_hit(doc: dict) -> dict:
    """Map a raw Typesense document to our shared schema."""
    # Combine city + country for location
    location_parts = filter(None, [doc.get("city"), doc.get("country")])
    location = ", ".join(location_parts) or None

    return {
        "name": doc.get("company_name"),
        "description": doc.get("brief_description"),
        "founded_year": extract_founded_year(doc),
        "batch": str(doc["first_session_year"]) if doc.get("first_session_year") else None,
        "website": doc.get("website"),
        "uses_ai": detect_ai(doc),
        "tags": doc.get("industry_vertical", []),
        "industries": doc.get("program_names", []),
        "location": location,
        "team_size": None,   # not available in Typesense data
        "status": None,      # not available in Typesense data
        "stage": None,       # not available in Typesense data
        "source": SOURCE,
        # Source-specific bonus fields stored as JSON
        "extra": {
            k: doc[k]
            for k in ("crunchbase_url", "linkedin_url", "twitter_url", "worldregion", "worldsubregion")
            if doc.get(k)
        },
    }


def main():
    # Step 1: Fetch all companies from Typesense (paginated)
    print("Fetching Techstars companies from Typesense API ...")
    raw_docs = fetch_all_companies()
    print(f"\n  Total raw companies fetched: {len(raw_docs)}")

    if not raw_docs:
        print("No companies returned. Exiting.")
        sys.exit(0)

    # Step 2: Normalize each doc with direct Python field mapping
    print("Normalizing records ...")
    companies = [normalize_hit(d) for d in raw_docs]

    # Step 3: Upsert into the shared database
    print("Writing to database ...")
    conn = get_connection()
    init_db(conn)
    for company in companies:
        insert_company(conn, company)
    conn.commit()
    conn.close()
    print(f"  Upserted {len(companies):,} records into data/startups.db")

    # Step 4: Print summary stats
    ai_count = sum(1 for c in companies if c["uses_ai"])
    print(f"\n  Fetched  : {len(raw_docs):,}")
    print(f"  Upserted : {len(companies):,}")
    print(f"  Uses AI  : {ai_count:,} ({ai_count / len(companies) * 100:.1f}%)")

    # Step 5: Print 3 sample uses_ai=True records for sanity check
    samples = [c for c in companies if c["uses_ai"]][:3]
    print("\n--- 3 sample uses_ai=True companies ---")
    for s in samples:
        print(json.dumps(s, indent=2))

    # Step 6: Full database stats across all sources
    conn = get_connection()
    get_stats(conn)
    conn.close()


if __name__ == "__main__":
    main()
