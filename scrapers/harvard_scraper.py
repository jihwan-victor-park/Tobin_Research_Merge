"""
Harvard Innovation Labs Scraper — fetches innovationlabs.harvard.edu/ventures
and parses all portfolio companies from server-rendered HTML across paginated pages.

Why BeautifulSoup (no API):
  Algolia meta tag is present but DevTools confirms no XHR calls fire — all data
  is server-rendered in the initial HTML payload. Pages are at /ventures/p2, /ventures/p3
  etc. Each page has 100 companies; final page has fewer. ~814 total across ~9 pages.

Selectors:
  Card       : a.venture-card
  Name       : h3.venture-card__title
  Description: p.venture-card__description
  Lab/program: second CSS class on a.venture-card (e.g. 'student-i-lab', 'launch-lab')
  Industry   : not available in listing view — tags derived from lab affiliation only
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

BASE_URL = "https://innovationlabs.harvard.edu/ventures"
SOURCE = "harvard_innovationlabs"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
RATE_LIMIT = 2  # seconds between page requests
PAGE_SIZE = 100  # stop when a page returns fewer cards than this

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


def page_url(page_num: int) -> str:
    """Return the URL for a given page number (1-indexed)."""
    if page_num == 1:
        return BASE_URL
    return f"{BASE_URL}/p{page_num}"


def fetch_page(page_num: int) -> BeautifulSoup:
    url = page_url(page_num)
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    print(f"  Page {page_num}: {url} — {len(response.text):,} bytes")
    return BeautifulSoup(response.text, "html.parser")


def parse_cards(soup: BeautifulSoup) -> list[dict]:
    """Parse all a.venture-card elements from a page."""
    cards = soup.find_all("a", class_="venture-card")
    companies = []
    for card in cards:
        # Name
        name_el = card.select_one("h3.venture-card__title")
        name = name_el.get_text(strip=True) if name_el else None
        if not name:
            continue

        # Description
        desc_el = card.select_one("p.venture-card__description")
        description = desc_el.get_text(strip=True) if desc_el else None

        # Lab/program affiliation — second CSS class on the <a> tag
        # e.g. ['venture-card', 'student-i-lab'] → 'student-i-lab'
        css_classes = card.get("class", [])
        lab = next((c for c in css_classes if c != "venture-card"), None)

        companies.append({
            "name": name,
            "description": description,
            "lab": lab,
        })

    return companies


def detect_ai(company: dict) -> bool:
    text = " ".join(filter(None, [
        company.get("description", ""),
        company.get("lab", ""),
    ]))
    return any(
        re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE)
        for kw in AI_KEYWORDS
    )


def normalize(company: dict) -> dict:
    return {
        "name": company["name"],
        "description": company.get("description"),
        "founded_year": None,
        "batch": company.get("lab"),       # lab affiliation stored as batch
        "website": None,
        "uses_ai": detect_ai(company),
        "tags": [],
        "industries": [],
        "location": None,
        "team_size": None,
        "status": None,
        "stage": None,
        "source": SOURCE,
        "extra": {"lab": company.get("lab")},
    }


def main():
    all_raw = []
    page_num = 1

    print(f"Fetching {BASE_URL} (paginated at /ventures/pN) ...")
    while True:
        soup = fetch_page(page_num)
        cards = parse_cards(soup)
        print(f"    {len(cards)} cards on page {page_num}")

        if not cards:
            print("  Empty page — stopping.")
            break

        all_raw.extend(cards)

        if len(cards) < PAGE_SIZE:
            print(f"  Last page ({len(cards)} < {PAGE_SIZE}) — stopping.")
            break

        page_num += 1
        time.sleep(RATE_LIMIT)

    print(f"\nTotal parsed: {len(all_raw)} companies across {page_num} pages")

    if not all_raw:
        print("No companies found. Exiting.")
        sys.exit(0)

    # Print raw HTML of first card for selector confirmation
    print("\n--- First card raw fields ---")
    print(json.dumps(all_raw[0], indent=2))

    # Normalize
    companies = [normalize(c) for c in all_raw]

    # Upsert
    print("\nWriting to database ...")
    conn = get_connection()
    init_db(conn)
    for company in companies:
        insert_company(conn, company)
    conn.commit()
    conn.close()
    print(f"  Upserted {len(companies):,} records into data/startups.db")

    # Summary
    ai_count = sum(1 for c in companies if c["uses_ai"])
    print(f"\n  Total fetched  : {len(all_raw)}")
    print(f"  Total upserted : {len(companies)}")
    print(f"  Uses AI        : {ai_count} ({ai_count / len(companies) * 100:.1f}%)")

    print("\n--- 3 sample records ---")
    for s in companies[:3]:
        print(json.dumps(s, indent=2))

    conn = get_connection()
    get_stats(conn)
    conn.close()


if __name__ == "__main__":
    main()
