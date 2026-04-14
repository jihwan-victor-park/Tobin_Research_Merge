"""
Antler Portfolio Scraper — fetches all portfolio companies from
antler.co/portfolio and upserts them into the shared SQLite DB.

Why BeautifulSoup (not Playwright):
  The site uses Webflow CMS with Finsweet cmslist pagination, which exposes
  a clean GET-based page parameter. Each page is fully server-rendered HTML —
  no JavaScript execution required. Pagination works via ?{hash}_page=N.

Pagination:
  The hash key (e.g. 0b933bfd) is Webflow-generated and could change.
  We detect it from the 'a.w-pagination-next' link on the current page
  rather than hardcoding it. We stop when no next-page link is present.

Selectors (confirmed from HTML inspection):
  Card container : div.portco_card (inside div.portco_cms_wrap)
  Name           : p[fs-cmsfilter-field="name"]
  Description    : p[fs-cmsfilter-field="description"]
  Location       : div.tag_small_wrap (the one whose fs-cmsfilter-field is
                   not "sector" or "year") → div.tag_small_text text
  Sector         : div.tag_small_wrap[fs-cmsfilter-field="sector"] .tag_small_text
  Year           : div.tag_small_wrap[fs-cmsfilter-field="year"] .tag_small_text
  Website        : a.clickable_link[href]
"""

import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.db import bulk_upsert, get_connection, init_db

BASE_URL = "https://www.antler.co/portfolio"
SOURCE = "antler"
RATE_LIMIT = 1  # seconds between page requests

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


def fetch(url: str) -> BeautifulSoup:
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def detect_next_page(soup: BeautifulSoup) -> str | None:
    """Return the href of the next-page link, or None if on the last page."""
    link = soup.select_one("a.w-pagination-next[href]")
    return link["href"] if link else None


def build_page_url(next_href: str, page: int) -> str:
    """
    Extract the hash key from a next-page href like '?0b933bfd_page=2'
    and build the URL for the requested page number.
    """
    # href is a relative query string: ?{hash}_page=N
    qs = next_href.lstrip("?")
    # key looks like "0b933bfd_page"
    for key in parse_qs(qs):
        if key.endswith("_page"):
            return f"{BASE_URL}?{key}={page}"
    # Fallback: use the href as-is with the page number substituted
    return f"{BASE_URL}?{qs.rsplit('=', 1)[0]}={page}"


def parse_cards(soup: BeautifulSoup) -> list[dict]:
    """Parse all div.portco_card elements from a page."""
    cards = soup.select("div.portco_cms_wrap div.portco_card")
    companies = []

    for card in cards:
        name_el = card.select_one('p[fs-cmsfilter-field="name"]')
        name = name_el.get_text(strip=True) if name_el else None
        if not name:
            continue

        desc_el = card.select_one('p[fs-cmsfilter-field="description"]')
        description = desc_el.get_text(strip=True) if desc_el else None

        # Tags: location, sector, year — distinguished by fs-cmsfilter-field on the wrap
        location = None
        sector = None
        year_text = None
        for wrap in card.select("div.tag_small_wrap"):
            field = wrap.get("fs-cmsfilter-field", "")
            text_el = wrap.select_one("div.tag_small_text")
            text = text_el.get_text(strip=True) if text_el else None
            if not text:
                continue
            if field == "sector":
                sector = text
            elif field == "year":
                year_text = text
            else:
                location = text  # fs-cmsfilter-field equals the location value itself

        founded_year = None
        if year_text:
            m = re.search(r"\b(19|20)\d{2}\b", year_text)
            if m:
                founded_year = int(m.group())

        website_el = card.select_one("a.clickable_link[href]")
        website = website_el["href"] if website_el else None

        companies.append({
            "name": name,
            "description": description,
            "location": location,
            "sector": sector,
            "founded_year": founded_year,
            "website": website,
        })

    return companies


def detect_ai(company: dict) -> bool:
    text = " ".join(filter(None, [
        company.get("description", ""),
        company.get("sector", ""),
    ]))
    return any(
        re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE)
        for kw in AI_KEYWORDS
    )


def normalize(company: dict) -> dict:
    return {
        "name": company["name"],
        "description": company.get("description"),
        "founded_year": company.get("founded_year"),
        "batch": None,
        "website": company.get("website"),
        "uses_ai": detect_ai(company),
        "tags": [company["sector"]] if company.get("sector") else [],
        "industries": [],
        "location": company.get("location"),
        "team_size": None,
        "status": None,
        "stage": None,
        "source": SOURCE,
        "extra": {},
    }


def main():
    print(f"Fetching {BASE_URL} ...")

    all_companies = []
    page = 1
    hash_key_href = None  # detected from first page's next link

    while True:
        if page == 1:
            url = BASE_URL
        else:
            url = build_page_url(hash_key_href, page)

        print(f"  Page {page}: {url}", end=" ... ", flush=True)
        soup = fetch(url)
        companies = parse_cards(soup)
        print(f"{len(companies)} companies")

        if not companies:
            print("  No cards found — stopping.")
            break

        all_companies.extend(companies)

        next_href = detect_next_page(soup)
        if not next_href:
            print("  No next-page link — reached last page.")
            break

        # Capture the hash key from the first next-page link we see
        if hash_key_href is None:
            hash_key_href = next_href

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
    count = bulk_upsert(conn, normalized)
    conn.commit()
    conn.close()

    ai_count = sum(1 for c in normalized if c["uses_ai"])
    print(f"\n  Upserted {count:,} companies into data/startups.db")
    print(f"  Uses AI : {ai_count:,} ({ai_count / len(normalized) * 100:.1f}%)")


if __name__ == "__main__":
    main()
