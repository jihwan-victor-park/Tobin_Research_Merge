"""
Columbia Entrepreneurship Startup Directory Scraper — queries the public REST
API at startups.columbia.edu for all companies and upserts them into the
shared SQLite database.

Why REST API (no HTML scraping):
  startups.columbia.edu exposes a clean JSON API requiring no authentication.
  Returns structured company data including name, website, founding date, and
  funding information.

API:
  GET /api/organizations?role=company&page_idx=N&sort=latest_update
  Page count available in meta.page_count on first response.
  ~6,200 companies across ~311 pages.
"""

import json
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.db import bulk_upsert, get_connection, get_stats, init_db

BASE_URL = "https://startups.columbia.edu/api/organizations"
SOURCE = "columbia"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

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


def fetch_page(page_idx: int) -> dict:
    params = {
        "role": "company",
        "page_idx": page_idx,
        "sort": "latest_update",
    }
    response = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=20)
    response.raise_for_status()
    return response.json()


def fetch_all_companies() -> list[dict]:
    print("  Fetching page 1 to get page count ...")
    first = fetch_page(1)
    meta = first.get("meta", {})
    page_count = meta.get("page_count", 1)
    total = meta.get("total", "?")
    print(f"  {total} companies across {page_count} pages")

    all_orgs = list(first.get("organizations", []))
    print(f"  Page 1: {len(all_orgs)} companies")

    for page in range(2, page_count + 1):
        time.sleep(1)
        data = fetch_page(page)
        orgs = data.get("organizations", [])
        if not orgs:
            print(f"  Page {page}: empty — stopping early")
            break
        all_orgs.extend(orgs)
        if page % 25 == 0 or page == page_count:
            print(f"  Page {page}/{page_count}: {len(all_orgs):,} total so far")

    return all_orgs


def detect_ai(org: dict) -> bool:
    text = org.get("name") or ""
    return any(
        re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE)
        for kw in AI_KEYWORDS
    )


def parse_founded_year(org: dict) -> int | None:
    founded_on = org.get("founded_on")
    if not founded_on:
        return None
    m = re.match(r"(\d{4})", str(founded_on))
    return int(m.group(1)) if m else None


def normalize(org: dict) -> dict:
    extra = {}
    if org.get("total_funding_usd"):
        extra["total_funding_usd"] = org["total_funding_usd"]
    if org.get("last_funding_event"):
        extra["last_funding_event"] = org["last_funding_event"]
    if org.get("permalink"):
        extra["permalink"] = org["permalink"]

    return {
        "name": org.get("name"),
        "description": None,           # not available from this endpoint
        "founded_year": parse_founded_year(org),
        "batch": None,                  # no cohort/batch concept
        "website": org.get("homepage_url") or None,
        "uses_ai": detect_ai(org),
        "tags": [],
        "industries": [],
        "location": None,               # not available from this endpoint
        "team_size": None,
        "status": None,
        "stage": org.get("last_funding_event", {}).get("series") if org.get("last_funding_event") else None,
        "source": SOURCE,
        "extra": extra,
    }


def main():
    print("Fetching Columbia Entrepreneurship companies ...")
    raw_orgs = fetch_all_companies()
    print(f"\n  Total fetched: {len(raw_orgs):,}")

    if not raw_orgs:
        print("No companies returned. Exiting.")
        sys.exit(0)

    print("Normalizing records ...")
    companies = [normalize(o) for o in raw_orgs]

    print("Writing to database ...")
    conn = get_connection()
    init_db(conn)
    upserted = bulk_upsert(conn, companies)
    conn.commit()

    ai_count = sum(1 for c in companies if c["uses_ai"])
    print(f"  Upserted {upserted:,} companies")
    print(f"  Uses AI : {ai_count} ({ai_count / upserted * 100:.1f}%)")

    print("\n--- 3 sample records ---")
    for s in companies[:3]:
        print(json.dumps(s, indent=2))

    get_stats(conn)
    conn.close()


if __name__ == "__main__":
    main()
