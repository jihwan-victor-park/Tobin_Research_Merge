"""
Spark Capital Scraper — BeautifulSoup, single page.

Why HTML (not API):
  sparkcapital.com serves all 144 portfolio companies server-rendered inside
  div.company-detail-wrapper modals. Each card contains the company name,
  a short description, optional exit/acquisition info, and a direct link to
  the company website.

Card structure (per company):
  div.company-detail-wrapper
    div.company-specs-wrapper
      h3.h3                              → company name
      div.company-specs.spacing---extra-small → description
      div.acquisition-spec               → exit / exchange info (optional)
    div.link-holder
      div.website-link
        a.company-link[href]             → company website
"""
import logging
from typing import List

import requests
from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SOURCE_URL = "https://www.sparkcapital.com/companies"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


class SparkCapitalScraper(BaseScraper):
    name = "sparkcapital"
    domain = "sparkcapital.com"
    difficulty = "easy"
    source_url = SOURCE_URL

    def scrape(self) -> List[ScrapedCompany]:
        r = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        cards = soup.find_all("div", class_="company-detail-wrapper")
        logger.info("SparkCapital: found %d cards", len(cards))

        results = []
        for card in cards:
            name_el = card.find("h3")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name:
                continue

            desc_el = card.find("div", class_="company-specs")
            description = desc_el.get_text(strip=True) if desc_el else None

            exit_el = card.find("div", class_="acquisition-spec")
            batch = exit_el.get_text(strip=True) if exit_el else None

            link_el = card.find("a", class_="company-link")
            website = link_el["href"] if link_el and link_el.get("href", "").startswith("http") else None

            is_ai = self.detect_ai(f"{name} {description or ''}", keyword_only=True)

            results.append(ScrapedCompany(
                name=name,
                description=description,
                website_url=website,
                profile_url=SOURCE_URL,
                batch=batch,
                program="Spark Capital",
                source_url=SOURCE_URL,
                is_ai_startup=is_ai,
                confidence=0.9,
            ))

        logger.info("SparkCapital: parsed %d companies", len(results))
        return results
