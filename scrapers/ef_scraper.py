"""
Entrepreneur First (EF) Scraper — fetches portfolio companies via the
WordPress AJAX filter endpoint and upserts them into the shared SQLite DB.

Why AJAX endpoint instead of scraping HTML:
  EF's portfolio page loads companies dynamically via a WordPress AJAX
  action. POSTing to admin-ajax.php with the right params returns paginated
  HTML fragments containing all company tiles — no JS rendering needed.

API discovery:
  Found via DevTools Network tab → filter by 'admin-ajax' to see the POST
  request, then inspect the form data payload.
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

# --- Config ---
AJAX_URL = "https://www.joinef.com/wp-admin/admin-ajax.php"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
# Company IDs excluded by EF's own frontend (placeholder/admin entries)
EXCLUDED_IDS = [
    12720,12721,12722,12723,12724,12725,12727,12728,12729,12730,
    12731,12732,12733,12734,12735,12736,12737,12738,12739,12740,
    12741,12742,12743,13192,
]
POSTS_PER_PAGE = 24
SOURCE = "entrepreneur_first"

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
    """POST to the WordPress AJAX endpoint for one page of companies."""
    query = json.dumps({
        "post_type": "company",
        "paged": page,
        "post_status": "publish",
        "post__not_in": EXCLUDED_IDS,
        "orderby": "menu_order",
        "order": "ASC",
        "posts_per_page": POSTS_PER_PAGE,
    })
    response = requests.post(
        AJAX_URL,
        headers=HEADERS,
        data={"action": "filter", "query": query},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def parse_tiles(html_content: str) -> list[dict]:
    """Parse company tiles from the HTML fragment returned by the AJAX endpoint."""
    soup = BeautifulSoup(html_content, "html.parser")
    companies = []

    for tile in soup.select("div.tile--company"):
        # Name — prefer the h4 heading, fall back to data attribute
        name_el = tile.select_one("h4.tile__name")
        name = name_el.get_text(strip=True) if name_el else None
        if not name:
            link_el = tile.select_one("div.tile__link[data-companyname]")
            name = link_el["data-companyname"] if link_el else None

        # Description
        desc_el = tile.select_one("div.tile__description")
        description = desc_el.get_text(strip=True) if desc_el else None

        # Founded year — structured in meta__row: label div says "Founded",
        # value is the adjacent sibling div in the same row
        founded_year = None
        for row in tile.select("div.meta__row"):
            cols = row.select("div.col")
            if len(cols) == 2:
                label = cols[0].get_text(strip=True)
                value = cols[1].get_text(strip=True)
                if label == "Founded" and re.match(r"^\d{4}$", value):
                    founded_year = int(value)
                    break

        # Location
        loc_el = tile.select_one("a.locationtag")
        location = loc_el.get_text(strip=True) if loc_el else None

        # Industry tags
        tags = [el.get_text(strip=True) for el in tile.select("a.categorytag")]

        companies.append({
            "name": name,
            "description": description,
            "founded_year": founded_year,
            "location": location,
            "tags": tags,
        })

    return companies


def fetch_all_companies() -> list[dict]:
    """Paginate through all AJAX pages using max_page from the first response."""
    # Fetch page 1 first to get max_page
    print("  Fetching page 1 ...")
    data = fetch_page(1)
    max_page = data.get("max_page", 1)
    found_posts = data.get("found_posts", 0)
    print(f"  Found {found_posts} companies across {max_page} pages")

    all_companies = parse_tiles(data.get("content", ""))
    print(f"  Page 1: {len(all_companies)} companies parsed")

    for page in range(2, max_page + 1):
        print(f"  Fetching page {page}/{max_page} ...")
        data = fetch_page(page)
        content = data.get("content", "")
        if not content:
            print(f"  Empty content on page {page} — stopping.")
            break
        batch = parse_tiles(content)
        all_companies.extend(batch)
        print(f"  Page {page}: {len(batch)} companies (total: {len(all_companies)})")
        time.sleep(0.5)

    return all_companies


def detect_ai(company: dict) -> bool:
    """Word-boundary keyword check on description and tags."""
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
        "batch": None,      # EF doesn't publish cohort batch labels
        "website": None,    # not included in the listing tiles
        "uses_ai": detect_ai(company),
        "tags": company.get("tags", []),
        "industries": [],
        "location": company.get("location"),
        "team_size": None,
        "status": None,
        "stage": None,
        "source": SOURCE,
        "extra": {},
    }


def main():
    # Step 1: Fetch all companies via paginated AJAX calls
    print("Fetching Entrepreneur First companies ...")
    raw_companies = fetch_all_companies()
    print(f"\n  Total parsed: {len(raw_companies)}")

    if not raw_companies:
        print("No companies found. Exiting.")
        sys.exit(0)

    # Step 2: Normalize to shared schema
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

    # Step 6: Full DB stats across all sources
    conn = get_connection()
    get_stats(conn)
    conn.close()


if __name__ == "__main__":
    main()
