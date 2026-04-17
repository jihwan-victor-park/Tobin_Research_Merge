"""
Capital Factory Scraper — fetches all portfolio companies from
capitalfactory.com/portfolio using BeautifulSoup.

Why BeautifulSoup:
  All 593 companies are rendered in the initial HTML payload as
  div.startup-item elements. No pagination or JavaScript needed.

Selectors (confirmed from HTML inspection):
  Card container : div.startup-item
  Name           : h4.startup-name
  Profile URL    : a.startup-card[href]
  Industries     : data-industries attribute (space-separated slugs)
  Technologies   : data-technologies attribute (space-separated slugs)
"""

import logging
from typing import List

import requests
from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SOURCE_URL = "https://www.capitalfactory.com/portfolio/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class CapitalFactoryScraper(BaseScraper):
    name = "capital_factory"
    domain = "capitalfactory.com"
    difficulty = "easy"
    source_url = SOURCE_URL

    def scrape(self) -> List[ScrapedCompany]:
        logger.info(f"Fetching {SOURCE_URL}")
        response = requests.get(SOURCE_URL, headers=HEADERS, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        cards = soup.select("div.startup-item")
        logger.info(f"Found {len(cards)} company cards")

        results: List[ScrapedCompany] = []
        for card in cards:
            name_el = card.select_one("h4.startup-name")
            name = name_el.get_text(strip=True) if name_el else None
            if not name:
                continue

            link_el = card.select_one("a.startup-card[href]")
            profile_url = link_el["href"] if link_el else None

            # Industries and technologies are space-separated slug strings
            # in data attributes — convert hyphens to spaces for readability
            raw_industries = card.get("data-industries", "")
            raw_technologies = card.get("data-technologies", "")
            tags = [
                s.replace("-", " ")
                for s in (raw_industries + " " + raw_technologies).split()
                if s
            ]
            industry_str = ", ".join(dict.fromkeys(tags)) if tags else None

            is_ai = self.detect_ai(industry_str or "")

            results.append(ScrapedCompany(
                name=name,
                profile_url=profile_url,
                industry=industry_str,
                is_ai_startup=is_ai,
                program="Capital Factory",
                source_url=SOURCE_URL,
            ))

        return results
