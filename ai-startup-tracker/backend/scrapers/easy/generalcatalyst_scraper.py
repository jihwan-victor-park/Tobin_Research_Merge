"""
General Catalyst Scraper — BeautifulSoup, single page (Webflow).

Why HTML (not API):
  generalcatalyst.com is built on Webflow and server-renders the portfolio
  carousel in HTML. All visible companies are in anchor elements with class
  c-company-card-overlay-style (Webflow inline-block links), each containing
  an h3 with the company name. The href links to the GC company profile.

Card structure (per company):
  a.c-company-card-overlay-style.w-inline-block[href=/companies/SLUG/]
    h3.c-company-card-overlay-style__heading  → company name
"""
import logging
from typing import List

import requests
from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SOURCE_URL = "https://www.generalcatalyst.com/portfolio"
BASE_URL = "https://www.generalcatalyst.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


class GeneralCatalystScraper(BaseScraper):
    name = "generalcatalyst"
    domain = "generalcatalyst.com"
    difficulty = "easy"
    source_url = SOURCE_URL

    def scrape(self) -> List[ScrapedCompany]:
        r = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Company cards: anchor elements with Webflow class containing h3 company name
        cards = soup.select("a.c-company-card-overlay-style")
        logger.info("General Catalyst: found %d company cards", len(cards))

        seen: set[str] = set()
        results = []
        for card in cards:
            name_el = card.find("h3")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or name in seen:
                continue
            seen.add(name)

            href = card.get("href", "")
            profile_url = (BASE_URL + href) if href.startswith("/") else (href or SOURCE_URL)

            is_ai = self.detect_ai(name, keyword_only=True)

            results.append(ScrapedCompany(
                name=name,
                description=None,
                website_url=None,
                profile_url=profile_url,
                program="General Catalyst",
                source_url=SOURCE_URL,
                is_ai_startup=is_ai,
                confidence=0.85,
            ))

        logger.info("General Catalyst: parsed %d companies", len(results))
        return results
