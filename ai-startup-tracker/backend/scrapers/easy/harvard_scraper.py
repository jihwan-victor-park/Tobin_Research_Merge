"""
Harvard Innovation Labs Scraper — fetches innovationlabs.harvard.edu/ventures
and parses all portfolio companies from server-rendered HTML across paginated pages.

Ported from Alastair branch (standalone script) to BaseScraper class.

Why BeautifulSoup (no API):
  Algolia meta tag is present but DevTools confirms no XHR calls fire — all data
  is server-rendered in the initial HTML payload. Pages are at /ventures/p2, /ventures/p3
  etc. Each page has 100 companies; final page has fewer. ~814 total across ~9 pages.

Selectors:
  Card       : a.venture-card
  Name       : h3.venture-card__title
  Description: p.venture-card__description
  Lab/program: second CSS class on a.venture-card (e.g. 'student-i-lab', 'launch-lab')
"""

import logging
import time
from typing import List

import requests
from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://innovationlabs.harvard.edu/ventures"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
RATE_LIMIT = 2  # seconds between page requests
PAGE_SIZE = 100  # stop when a page returns fewer cards than this


class HarvardScraper(BaseScraper):
    name = "harvard_innovationlabs"
    domain = "innovationlabs.harvard.edu"
    difficulty = "easy"
    source_url = "https://innovationlabs.harvard.edu/ventures"

    def scrape(self) -> List[ScrapedCompany]:
        all_raw = []
        page_num = 1

        while True:
            soup = self._fetch_page(page_num)
            cards = self._parse_cards(soup)
            logger.info(f"Page {page_num}: {len(cards)} cards")

            if not cards:
                logger.info("Empty page -- stopping.")
                break

            all_raw.extend(cards)

            if len(cards) < PAGE_SIZE:
                logger.info(
                    f"Last page ({len(cards)} < {PAGE_SIZE}) -- stopping."
                )
                break

            page_num += 1
            time.sleep(RATE_LIMIT)

        logger.info(f"Total parsed: {len(all_raw)} companies across {page_num} pages")

        results: List[ScrapedCompany] = []
        for company in all_raw:
            text = " ".join(filter(None, [
                company.get("description", ""),
                company.get("lab", ""),
            ]))
            is_ai = self.detect_ai(text)

            results.append(ScrapedCompany(
                name=company["name"],
                description=company.get("description"),
                profile_url=self.source_url,
                is_ai_startup=is_ai,
                batch=company.get("lab"),
                program="Harvard Innovation Labs",
                country="US",
                city="Cambridge",
                source_url=self.source_url,
            ))

        return results

    def _page_url(self, page_num: int) -> str:
        """Return the URL for a given page number (1-indexed)."""
        if page_num == 1:
            return BASE_URL
        return f"{BASE_URL}/p{page_num}"

    def _fetch_page(self, page_num: int) -> BeautifulSoup:
        url = self._page_url(page_num)
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        logger.info(f"Page {page_num}: {url} -- {len(response.text):,} bytes")
        return BeautifulSoup(response.text, "html.parser")

    def _parse_cards(self, soup: BeautifulSoup) -> list[dict]:
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

            # Lab/program affiliation -- second CSS class on the <a> tag
            css_classes = card.get("class", [])
            lab = next((c for c in css_classes if c != "venture-card"), None)

            companies.append({
                "name": name,
                "description": description,
                "lab": lab,
            })

        return companies
