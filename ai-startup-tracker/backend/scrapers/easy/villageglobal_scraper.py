"""
Village Global Scraper — fetches all portfolio companies from
villageglobal.com/portfolio using BeautifulSoup.

Why BeautifulSoup:
  All 75 companies are in the initial HTML payload as Webflow
  a.company-details elements — no pagination or JavaScript needed.

Selectors (confirmed from HTML inspection):
  Card link    : a.company-details[href]  → company website
  Company name : img.company-logo[alt]   → name from logo alt text
"""

import logging
from typing import List

import requests
from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SOURCE_URL = "https://www.villageglobal.com/portfolio"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class VillageGlobalScraper(BaseScraper):
    name = "village_global"
    domain = "villageglobal.com"
    difficulty = "easy"
    source_url = SOURCE_URL

    def scrape(self) -> List[ScrapedCompany]:
        logger.info(f"Fetching {SOURCE_URL}")
        response = requests.get(SOURCE_URL, headers=HEADERS, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        cards = soup.select("a.company-details")
        logger.info(f"Found {len(cards)} company cards")

        results: List[ScrapedCompany] = []
        for card in cards:
            img = card.select_one("img.company-logo")
            name = img.get("alt", "").strip() if img else None
            if not name:
                continue

            website = card.get("href") or None

            results.append(ScrapedCompany(
                name=name,
                website_url=website,
                profile_url=SOURCE_URL,
                program="Village Global",
                source_url=SOURCE_URL,
            ))

        return results
