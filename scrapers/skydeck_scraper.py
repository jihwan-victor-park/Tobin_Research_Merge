"""
Berkeley SkyDeck Scraper — fetches all portfolio companies via a WordPress
AJAX endpoint and upserts them into the shared SQLite database.

Why AJAX endpoint instead of scraping HTML:
  SkyDeck's portfolio page loads companies dynamically via a WordPress AJAX
  action. A single POST to admin-ajax.php with action=company_filtration_query
  returns all 800+ companies as JSON — no pagination, no JS rendering needed.

API discovery:
  Found via DevTools Network tab → filter by 'admin-ajax'. POST payload uses
  duplicate keys (meta[0][], meta[1][], meta[2][]) so must be sent as a list
  of tuples, not a dict. X-Requested-With: XMLHttpRequest header required.
"""

import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.db import bulk_upsert, get_connection, init_db

# --- Config ---
AJAX_URL = "https://skydeck.berkeley.edu/wp-admin/admin-ajax.php"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}
# Duplicate keys require a list of tuples — a dict would silently drop repeats
PAYLOAD = [
    ("action", "company_filtration_query"),
    ("meta[0][]", "main_industry"),
    ("meta[0][]", "all"),
    ("meta[1][]", "classes"),
    ("meta[1][]", "all"),
    ("meta[2][]", "industry"),
    ("meta[2][]", "all"),
    ("search", ""),
]
SOURCE = "skydeck"

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


def fetch_companies() -> list[dict]:
    """POST to the SkyDeck AJAX endpoint and return the raw posts list."""
    response = requests.post(AJAX_URL, data=PAYLOAD, headers=HEADERS, timeout=30)
    response.raise_for_status()
    data = response.json()
    posts = data.get("posts", [])
    print(f"  Received {len(posts)} companies from API")
    return posts


def detect_ai(text: str) -> bool:
    """Return True if any AI keyword appears in text (word-boundary matched)."""
    return any(
        re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE)
        for kw in AI_KEYWORDS
    )


def normalize(post: dict) -> dict:
    """Map a raw SkyDeck post to the shared DB schema."""
    name = post.get("title", "").strip()
    return {
        "name": name,
        "description": None,       # not available from this endpoint
        "founded_year": None,       # not available from this endpoint
        "batch": post.get("class") or None,
        "website": post.get("url") or None,
        "uses_ai": detect_ai(name), # name-only — low confidence, enrichment needed
        "tags": [],
        "industries": [],
        "location": None,           # not available from this endpoint
        "team_size": None,
        "status": None,
        "stage": None,
        "source": SOURCE,
        "extra": {},
    }


def main():
    print("Fetching SkyDeck companies ...")
    raw_posts = fetch_companies()

    if not raw_posts:
        print("No companies returned. Exiting.")
        sys.exit(0)

    print("Normalizing records ...")
    companies = [normalize(p) for p in raw_posts]

    print("Writing to database ...")
    conn = get_connection()
    init_db(conn)
    count = bulk_upsert(conn, companies)
    conn.commit()
    conn.close()

    ai_count = sum(1 for c in companies if c["uses_ai"])
    print(f"  Upserted {count:,} companies into data/startups.db")
    print(f"  Uses AI  : {ai_count:,} ({ai_count / len(companies) * 100:.1f}%) — name-only, low confidence")


if __name__ == "__main__":
    main()
