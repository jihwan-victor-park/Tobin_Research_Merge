"""
ERA NYC Scraper — fetches all portfolio companies from
eranyc.com/portfolio using BeautifulSoup.

Why BeautifulSoup:
  All companies are rendered in the initial HTML as li.p1 list items.
  Each item is a plain anchor tag with the company name as text.

Selectors (confirmed from HTML inspection):
  Company items : li.p1 a  → text = name, href = press/news article
  Note: hrefs are press articles, not company websites — stored as
  profile_url only, not website_url.
"""

import logging
from typing import List

import requests
from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SOURCE_URL = "https://www.eranyc.com/portfolio"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class ERANYCScraper(BaseScraper):
    name = "era_nyc"
    domain = "eranyc.com"
    difficulty = "easy"
    source_url = SOURCE_URL

    def scrape(self) -> List[ScrapedCompany]:
        logger.info(f"Fetching {SOURCE_URL}")
        response = requests.get(SOURCE_URL, headers=HEADERS, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        items = soup.select("li.p1")
        logger.info(f"Found {len(items)} company entries")

        results: List[ScrapedCompany] = []
        seen = set()
        for item in items:
            name = item.get_text(strip=True)
            if not name or name in seen:
                continue
            seen.add(name)

            # Some items have an <a> linking to a press article — store as profile_url
            link = item.select_one("a[href]")
            press_url = link["href"] if link else None

            results.append(ScrapedCompany(
                name=name,
                profile_url=press_url,
                program="ERA NYC",
                source_url=SOURCE_URL,
            ))

        return results
