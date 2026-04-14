"""
Rice Alliance OwlSpark Scraper — fetches alliance.rice.edu/owlspark/ventures
and parses all cohort companies from the static server-rendered HTML.

Why BeautifulSoup (no API):
  Single page, all classes in one HTML payload. An accordion widget groups
  companies by class. No JavaScript rendering required — all content is in
  the initial HTML response.

Structure:
  Class header : span.item-title  (e.g. "Class 13 | May 15 - August 1, 2025")
  Panel        : div.accordion-panel > ul > li
  Name         : <strong> tag within each li
  Description  : full li text (includes name + description sentence)

Older classes (pre-2023) lack descriptions — name extracted from link text
or plain text; description set to None.
"""

import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.db import bulk_upsert, get_connection, get_stats, init_db

URL = "https://alliance.rice.edu/owlspark/ventures"
SOURCE = "rice_owlspark"
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


def fetch_page() -> BeautifulSoup:
    response = requests.get(URL, headers=HEADERS, timeout=20)
    response.raise_for_status()
    print(f"  Downloaded {len(response.text):,} bytes")
    return BeautifulSoup(response.text, "html.parser")


def parse_cohort_year(header_text: str) -> int | None:
    """Extract 4-digit year from header like 'Class 13 | May 15 - August 1, 2025'."""
    m = re.search(r"\b(20\d{2})\b", header_text)
    return int(m.group(1)) if m else None


def parse_batch(header_text: str) -> str:
    """Extract the class label, e.g. 'Class 13' or 'Class 11, Class 2'."""
    parts = header_text.split("|", 1)
    return parts[0].strip()


def parse_li(li) -> tuple[str | None, str | None]:
    """
    Return (name, description) from a single <li> element.

    Handles three formats found on the page:
      1. <li><p><strong>Name</strong><span> description</span></p></li>
      2. <li><span lang="EN"><strong>Name</strong> description</span></li>
      3. <li><a href="...">Name</a></li>  (older classes — no description)
      4. <li>Name</li>                    (older classes — no description)
    """
    strong = li.find("strong")
    if strong:
        name = strong.get_text(strip=True)
        # Full li text is the complete sentence (name + description together)
        full_text = li.get_text(" ", strip=True)
        # Normalize whitespace
        full_text = re.sub(r"\s+", " ", full_text).strip()
        description = full_text if full_text else None
        return name, description

    # Fallback: link text only
    a = li.find("a")
    if a:
        return a.get_text(strip=True), None

    # Plain text
    name = li.get_text(strip=True)
    return (name, None) if name else (None, None)


def parse_companies(soup: BeautifulSoup) -> list[dict]:
    companies = []

    # Each accordion item is a <li> containing a button + accordion-panel
    accordion_items = soup.select("li:has(button.accordion-trigger)")

    for item in accordion_items:
        header_el = item.select_one("span.item-title")
        if not header_el:
            continue
        header_text = header_el.get_text(strip=True)
        batch = parse_batch(header_text)
        cohort_year = parse_cohort_year(header_text)

        panel = item.select_one("div.accordion-panel")
        if not panel:
            continue

        for li in panel.select("ul > li"):
            name, description = parse_li(li)
            if not name:
                continue
            companies.append({
                "name": name,
                "description": description,
                "batch": batch,
                "cohort_year": cohort_year,
            })

    return companies


def detect_ai(company: dict) -> bool:
    text = company.get("description") or company.get("name") or ""
    return any(
        re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE)
        for kw in AI_KEYWORDS
    )


def normalize(company: dict) -> dict:
    return {
        "name": company["name"],
        "description": company.get("description"),
        "founded_year": None,
        "batch": company.get("batch"),
        "website": None,
        "uses_ai": detect_ai(company),
        "tags": [],
        "industries": [],
        "location": None,
        "team_size": None,
        "status": None,
        "stage": None,
        "source": SOURCE,
        "extra": {"cohort_year": company.get("cohort_year")},
    }


def main():
    print(f"Fetching {URL} ...")
    soup = fetch_page()

    print("Parsing companies ...")
    raw = parse_companies(soup)
    print(f"  Found {len(raw)} companies across all classes")

    if not raw:
        print("No companies found. Exiting.")
        sys.exit(0)

    companies = [normalize(c) for c in raw]

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
