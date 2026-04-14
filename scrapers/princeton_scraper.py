"""
Princeton Keller Center eLab Scraper — fetches all eLab portfolio companies
from a Drupal server-rendered site and upserts them into the shared SQLite DB.

Why BeautifulSoup (no API):
  Drupal CMS with fully server-rendered HTML. No XHR calls fire on page load —
  all company data is in the initial HTML payload. Paginated via &page=N query
  param, pages 0-8 (9 total).

Two-pass approach:
  Pass 1 — listing pages: extract name, short description, program track,
            cohort year, and detail page slug.
  Pass 2 — detail pages: fetch each company's detail page to get the full
            description (much longer than the listing snippet).

Selectors (confirmed from HTML inspection):
  Container    : div.view-content
  Year header  : h2.group-title (precedes each cohort group — not inside the card)
  Card wrapper : div.views-row > div.node--type-startup-team
  Name         : div.field--name-node-title p
  Program track: div.field--name-startup-team-program
  Short desc   : div.field--name-field-subtitle a (text)
  Detail URL   : div.field--name-field-subtitle a href (relative)
"""

import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.db import bulk_upsert, get_connection, init_db

# --- Config ---
BASE_LISTING_URL = (
    "https://kellercenter.princeton.edu/people/teams-startups-filtered"
    "?program-filter%5B18%5D=18"
)
DETAIL_BASE = "https://kellercenter.princeton.edu"
TOTAL_PAGES = 9   # pages 0-8
SOURCE = "princeton_keller"
RATE_LIMIT = 1.5  # seconds between requests — be polite to the university server

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


def listing_url(page: int) -> str:
    """Return the URL for a given listing page (0-indexed)."""
    if page == 0:
        return BASE_LISTING_URL
    return f"{BASE_LISTING_URL}&page={page}"


def fetch(url: str) -> BeautifulSoup:
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def parse_listing_page(soup: BeautifulSoup) -> list[dict]:
    """
    Extract company cards from a listing page.

    The cohort year is carried by h2.group-title elements that appear as
    siblings of div.views-row inside div.view-content — not inside each card.
    We iterate children of div.view-content, updating current_year whenever
    we hit an h2.group-title, and collecting card data from each div.views-row.
    """
    companies = []

    view_content = soup.select_one("div.view-content")
    if not view_content:
        return companies

    current_year = None
    for child in view_content.children:
        # Skip NavigableString (whitespace text nodes)
        if not hasattr(child, "name"):
            continue

        # Year header — update running year tracker
        if child.name == "h2" and "group-title" in child.get("class", []):
            m = re.search(r"(20\d{2})", child.get_text())
            current_year = m.group(1) if m else child.get_text(strip=True)
            continue

        # Cards are wrapped in div.group-status — iterate rows inside it
        if child.name == "div" and "group-status" in child.get("class", []):
            for row in child.find_all("div", class_="views-row"):
                card = row.select_one("div.node--type-startup-team")
                if not card:
                    continue

                # Name
                name_el = card.select_one("div.field--name-node-title p")
                name = name_el.get_text(strip=True) if name_el else None
                if not name:
                    continue

                # Program track (eLab Accelerator / eLab Incubator)
                track_el = card.select_one("div.field--name-startup-team-program")
                program_track = track_el.get_text(strip=True) if track_el else None

                # Short description + detail URL — both from the same <a> tag
                subtitle_link = card.select_one("div.field--name-field-subtitle a")
                short_desc = subtitle_link.get_text(strip=True) if subtitle_link else None
                detail_path = subtitle_link.get("href", "") if subtitle_link else ""
                detail_url = urljoin(DETAIL_BASE, detail_path) if detail_path else None

                companies.append({
                    "name": name,
                    "short_desc": short_desc,
                    "program_track": program_track,
                    "cohort_year": current_year,
                    "detail_url": detail_url,
                })

    return companies


def fetch_detail_description(detail_url: str, debug: bool = False) -> str | None:
    """
    Fetch a company detail page and return the full description text.

    Tries selectors in order of specificity:
      1. div.field--name-field-description  (most specific)
      2. div.field--name-body
      3. article.node--type-startup-team — all <p> tags, skipping boilerplate

    Guard: returns None if text starts with "Princeton University" or is < 30 chars.
    """
    try:
        soup = fetch(detail_url)

        # Selector 1: text-long field used for body copy on detail pages
        content = soup.select_one("div.field--name-field-text")

        # Selector 2: dedicated description field
        if not content:
            content = soup.select_one("div.field--name-field-description")

        # Selector 3: body field
        if not content:
            content = soup.select_one("div.field--name-body")

        if content:
            text = " ".join(p.get_text(strip=True) for p in content.find_all("p") if p.get_text(strip=True))
            if not text:
                text = content.get_text(strip=True)
        else:
            # Fallback: all <p> tags in main, filtered for boilerplate
            paragraphs = [
                p.get_text(strip=True)
                for p in soup.select("main p")
                if p.get_text(strip=True)
                and "Princeton University" not in p.get_text()
                and not p.find_parent(["nav", "footer"])
            ]
            text = " ".join(paragraphs)

        if debug:
            print(f"    [debug] Raw extracted text: {text[:300]!r}")

        # Guard against boilerplate
        if not text or len(text) < 30 or text.startswith("Princeton University"):
            return None

        return text

    except Exception as e:
        print(f"    [warn] Detail page failed ({detail_url}): {e}")
        return None


def detect_ai(text: str) -> bool:
    if not text:
        return False
    return any(
        re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE)
        for kw in AI_KEYWORDS
    )


def normalize(raw: dict) -> dict:
    description = raw.get("full_desc") or raw.get("short_desc")
    return {
        "name": raw["name"],
        "description": description,
        "founded_year": None,   # not available on this site
        "batch": raw.get("cohort_year"),
        "website": None,        # not available on this site
        "uses_ai": detect_ai(description),
        "tags": [],
        "industries": [],
        "location": None,       # not available on this site
        "team_size": None,
        "status": None,
        "stage": None,
        "source": SOURCE,
        "extra": {
            k: v for k, v in {
                "program_track": raw.get("program_track"),
                "detail_url": raw.get("detail_url"),
            }.items() if v
        },
    }


def main():
    # --- Pass 1: listing pages ---
    print(f"Fetching {TOTAL_PAGES} listing pages ...")
    all_raw = []
    for page in range(TOTAL_PAGES):
        url = listing_url(page)
        print(f"  Page {page}: {url}")
        soup = fetch(url)
        cards = parse_listing_page(soup)
        print(f"    {len(cards)} cards")
        all_raw.extend(cards)
        if page < TOTAL_PAGES - 1:
            time.sleep(RATE_LIMIT)

    print(f"\nTotal from listing pages: {len(all_raw)}")

    if not all_raw:
        print("No companies found on listing pages. Exiting.")
        sys.exit(0)

    # --- Pass 2: detail pages ---
    print(f"\nFetching {len(all_raw)} detail pages for full descriptions ...")
    for i, raw in enumerate(all_raw):
        if not raw.get("detail_url"):
            continue
        print(f"  [{i + 1}/{len(all_raw)}] {raw['name']}")
        raw["full_desc"] = fetch_detail_description(raw["detail_url"])
        time.sleep(RATE_LIMIT)

    # --- Normalize and upsert ---
    companies = [normalize(r) for r in all_raw]

    print("\nWriting to database ...")
    conn = get_connection()
    init_db(conn)
    count = bulk_upsert(conn, companies)
    conn.commit()
    conn.close()

    ai_count = sum(1 for c in companies if c["uses_ai"])
    print(f"\n  Upserted {count:,} companies into data/startups.db")
    print(f"  Uses AI : {ai_count:,} ({ai_count / len(companies) * 100:.1f}%)")


if __name__ == "__main__":
    main()
