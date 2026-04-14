"""
Seedcamp Scraper — fetches seedcamp.com/companies/ and parses all portfolio
companies from the server-rendered WordPress HTML in a single request.

Why BeautifulSoup (no API, no Claude):
  The page loads all 550+ companies in one ~441KB HTML payload.
  Category filters (AI, Climate, Fintech, etc.) are purely client-side —
  no separate requests are made. All data is in the initial HTML.
  Each company is a div.company__item with clean, consistent selectors.

Selectors:
  Name        : span.company__item__name
  Year        : h6.company__item__year
  Description : div.company__item__description__content
  Website     : a.company__item__link[href]
  Sector tags : CSS classes on div.company__item (e.g. 'ai', 'climate')
"""

import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.db import get_connection, get_stats, init_db, insert_company

URL = "https://seedcamp.com/companies/"
SOURCE = "seedcamp"
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

# CSS classes on div.company__item that indicate AI — used to supplement keyword matching
AI_SECTOR_CLASSES = {"ai"}


def fetch_page() -> BeautifulSoup:
    """Fetch the Seedcamp companies page and return a BeautifulSoup object."""
    response = requests.get(URL, headers=HEADERS, timeout=20)
    response.raise_for_status()
    print(f"  Downloaded {len(response.text):,} bytes")
    return BeautifulSoup(response.text, "html.parser")


def parse_companies(soup: BeautifulSoup) -> list[dict]:
    """Parse all company__item divs from the page."""
    items = soup.select("div.company__item")
    print(f"  Found {len(items)} company__item elements")

    companies = []
    for item in items:
        # Name
        name_el = item.select_one("span.company__item__name")
        name = name_el.get_text(strip=True) if name_el else None
        if not name:
            continue

        # Year of investment (stored as batch)
        year_el = item.select_one("h6.company__item__year")
        batch = year_el.get_text(strip=True) if year_el else None

        # Description
        desc_el = item.select_one("div.company__item__description__content")
        description = desc_el.get_text(strip=True) if desc_el else None

        # Website — the primary anchor link
        link_el = item.select_one("a.company__item__link[href]")
        website = link_el["href"] if link_el else None

        # Sector tags from CSS classes — filter out structural class names
        structural_classes = {"company__item", "mix"}
        raw_classes = set(item.get("class", []))
        sector_tags = sorted(raw_classes - structural_classes)

        companies.append({
            "name": name,
            "description": description,
            "batch": batch,
            "website": website,
            "sector_tags": sector_tags,
        })

    return companies


def detect_ai(company: dict) -> bool:
    """
    Word-boundary keyword check on description + sector tags.
    Also flags if the 'ai' CSS class is present on the company div.
    """
    # Direct AI sector class match
    if AI_SECTOR_CLASSES & set(company.get("sector_tags", [])):
        return True

    text = " ".join(filter(None, [
        company.get("description", ""),
        " ".join(company.get("sector_tags", [])),
    ]))
    return any(
        re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE)
        for kw in AI_KEYWORDS
    )


def normalize(company: dict) -> dict:
    """Map parsed fields to the shared schema."""
    return {
        "name": company["name"],
        "description": company.get("description"),
        "founded_year": None,   # not available on listing page
        "batch": company.get("batch"),
        "website": company.get("website"),
        "uses_ai": detect_ai(company),
        "tags": company.get("sector_tags", []),
        "industries": [],
        "location": None,       # not available on listing page
        "team_size": None,
        "status": None,
        "stage": None,
        "source": SOURCE,
        "extra": {},
    }


def main():
    # Step 1: Fetch and parse
    print(f"Fetching {URL} ...")
    soup = fetch_page()

    print("Parsing companies ...")
    raw_companies = parse_companies(soup)
    print(f"  Parsed {len(raw_companies)} companies")

    if not raw_companies:
        print("No companies found. Exiting.")
        sys.exit(0)

    # Step 2: Normalize
    companies = [normalize(c) for c in raw_companies]

    # Step 3: Upsert into database
    print("Writing to database ...")
    conn = get_connection()
    init_db(conn)
    for company in companies:
        insert_company(conn, company)
    conn.commit()
    conn.close()
    print(f"  Upserted {len(companies):,} records into data/startups.db")

    # Step 4: Summary
    ai_count = sum(1 for c in companies if c["uses_ai"])
    print(f"\n  Total fetched  : {len(raw_companies)}")
    print(f"  Total upserted : {len(companies)}")
    print(f"  Uses AI        : {ai_count} ({ai_count / len(companies) * 100:.1f}%)")

    # Step 5: 3 sample records
    print("\n--- 3 sample records ---")
    for s in companies[:3]:
        print(json.dumps(s, indent=2))

    # Step 6: Full DB stats
    conn = get_connection()
    get_stats(conn)
    conn.close()


if __name__ == "__main__":
    main()
