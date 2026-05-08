"""
Union Square Ventures Scraper — BeautifulSoup, single page.

Why HTML (not API):
  usv.com has no portfolio CPT in WordPress REST. All 210 companies are
  server-rendered in div.m__list-row elements (one per company). Each row
  contains an external company website link, stage/series text, and a
  short description excerpt.

Card structure:
  div.m__list-row (skip div.m__list-row.m__list-row--mobile duplicates)
    div.m__list-row__col [0] → logo img
    div.m__list-row__col [1] → a[href=company_website] with company name
                              + span.exit-detail (optional exit info)
    div.m__list-row__col [2] → plain text stage (e.g. "Series A, 2024")
    div.m__list-row__col [3] → div.m__list-row__excerpt (description)
"""
import logging
from typing import List

import requests
from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SOURCE_URL = "https://www.usv.com/companies/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


class USVScraper(BaseScraper):
    name = "usv"
    domain = "usv.com"
    difficulty = "easy"
    source_url = SOURCE_URL

    def scrape(self) -> List[ScrapedCompany]:
        r = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Skip mobile-duplicate rows (class list contains m__list-row--mobile)
        rows = [
            div for div in soup.find_all("div", class_="m__list-row")
            if "m__list-row--mobile" not in div.get("class", [])
        ]
        logger.info("USV: found %d company rows", len(rows))

        results = []
        for row in rows:
            cols = row.find_all("div", class_="m__list-row__col", recursive=False)
            if len(cols) < 2:
                continue

            # Company name + external website from column 2
            name_col = cols[1]
            a = name_col.find("a", href=True)
            if not a:
                continue
            name = a.get_text(strip=True)
            website = a["href"] if a["href"].startswith("http") else None
            if not name:
                continue

            # Stage from column 3
            batch = cols[2].get_text(strip=True) if len(cols) > 2 else None

            # Description from column 4 (excerpt div)
            desc_el = row.find(class_="m__list-row__excerpt")
            description = desc_el.get_text(strip=True) if desc_el else None

            is_ai = self.detect_ai(f"{name} {description or ''}")

            results.append(ScrapedCompany(
                name=name,
                description=description,
                website_url=website,
                profile_url=SOURCE_URL,
                batch=batch,
                program="Union Square Ventures",
                source_url=SOURCE_URL,
                is_ai_startup=is_ai,
                confidence=0.9,
            ))

        logger.info("USV: parsed %d companies", len(results))
        return results
