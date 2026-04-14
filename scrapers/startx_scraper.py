"""
StartX Scraper — fetches web.startx.com/community and parses all portfolio
companies from the Webflow CMS pages using Finsweet list pagination.

Why this URL (not startx.com/companies):
  startx.com/companies is an Angular SPA — requests returns an empty shell
  and API endpoint probing (/api/companies, /companies.json) returns 404.
  The actual portfolio data lives on web.startx.com, a separate Webflow site,
  which is fully server-rendered.

Pagination:
  Finsweet CMS List uses a hashed query param: ?6a151520_page=N
  Increment N from 1 until the response contains no div.comn-list-item elements.

Selectors (all use Finsweet fs-list-field data attributes):
  Container   : div.comn-list-item
  Name        : [fs-list-field='title']
  Description : p[fs-list-field='description']
  Batch       : [fs-list-field='session']
  Industry    : [fs-list-field='industry']  (may be multiple per company)
  Year        : [fs-list-field='year']
  Website     : a.comn-list-link[href]
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

BASE_URL = "https://web.startx.com/community"
PAGE_PARAM = "6a151520_page"
SOURCE = "startx"
RATE_LIMIT = 2  # seconds between requests

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


def fetch_page(page: int) -> BeautifulSoup:
    """Fetch one paginated community page and return a BeautifulSoup object."""
    url = f"{BASE_URL}?{PAGE_PARAM}={page}"
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def parse_companies(soup: BeautifulSoup) -> list[dict]:
    """Parse all div.comn-list-item elements from a page."""
    items = soup.select("div.comn-list-item")
    companies = []
    for item in items:
        name_el = item.select_one("[fs-list-field='title']")
        name = name_el.get_text(strip=True) if name_el else None
        if not name:
            continue

        desc_el = item.select_one("p[fs-list-field='description']")
        description = desc_el.get_text(strip=True) if desc_el else None

        batch_el = item.select_one("[fs-list-field='session']")
        batch = batch_el.get_text(strip=True) if batch_el else None

        # Industry may appear on multiple elements per company
        industry_els = item.select("[fs-list-field='industry']")
        tags = [el.get_text(strip=True) for el in industry_els if el.get_text(strip=True)]

        year_el = item.select_one("[fs-list-field='year']")
        year_text = year_el.get_text(strip=True) if year_el else None
        founded_year = None
        if year_text:
            m = re.search(r"\b(19|20)\d{2}\b", year_text)
            if m:
                founded_year = int(m.group())

        link_el = item.select_one("a.comn-list-link[href]")
        website = link_el["href"] if link_el else None

        companies.append({
            "name": name,
            "description": description,
            "batch": batch,
            "tags": tags,
            "founded_year": founded_year,
            "website": website,
        })

    return companies


def detect_ai(company: dict) -> bool:
    """Word-boundary keyword check on description and industry tags."""
    text = " ".join(filter(None, [
        company.get("description", ""),
        " ".join(company.get("tags", [])),
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
        "founded_year": company.get("founded_year"),
        "batch": company.get("batch"),
        "website": company.get("website"),
        "uses_ai": detect_ai(company),
        "tags": company.get("tags", []),
        "industries": [],
        "location": None,
        "team_size": None,
        "status": None,
        "stage": None,
        "source": SOURCE,
        "extra": {},
    }


def main():
    print(f"Fetching {BASE_URL} (Finsweet paginated) ...")

    all_companies = []
    page = 1

    while True:
        print(f"  Page {page} ...", end=" ", flush=True)
        soup = fetch_page(page)
        companies = parse_companies(soup)
        print(f"{len(companies)} companies")

        if not companies:
            print("  No more results — stopping.")
            break

        all_companies.extend(companies)
        page += 1
        time.sleep(RATE_LIMIT)

    print(f"\nTotal fetched: {len(all_companies)}")

    if not all_companies:
        print("No companies found. Exiting.")
        sys.exit(0)

    normalized = [normalize(c) for c in all_companies]

    print("Writing to database ...")
    conn = get_connection()
    init_db(conn)
    for company in normalized:
        insert_company(conn, company)
    conn.commit()
    conn.close()
    print(f"  Upserted {len(normalized):,} records into data/startups.db")

    ai_count = sum(1 for c in normalized if c["uses_ai"])
    print(f"\n  Total fetched  : {len(all_companies)}")
    print(f"  Total upserted : {len(normalized)}")
    print(f"  Uses AI        : {ai_count} ({ai_count / len(normalized) * 100:.1f}%)")

    print("\n--- 3 sample records ---")
    for s in normalized[:3]:
        print(json.dumps(s, indent=2))

    conn = get_connection()
    get_stats(conn)
    conn.close()


if __name__ == "__main__":
    main()
