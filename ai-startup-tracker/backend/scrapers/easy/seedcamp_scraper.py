"""
Seedcamp Scraper — fetches seedcamp.com/companies/ and parses all portfolio
companies from the server-rendered WordPress HTML in a single request.

Ported from Alastair branch (standalone script) to BaseScraper class.

Why BeautifulSoup (no API, no Claude):
  The page loads all 550+ companies in one ~441KB HTML payload.
  Category filters (AI, Climate, Fintech, etc.) are purely client-side —
  no separate requests are made. All data is in the initial HTML.
  Each company is a div.company__item with clean, consistent selectors.

Selectors:
  Name        : span.company__item__name
  Year        : h6.company__item__year
  Description : div.company__item__description__content
  Website     : a.company__item__link[href]
  Sector tags : CSS classes on div.company__item (e.g. 'ai', 'climate')
"""

import logging
from typing import List

import requests
from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# CSS classes on div.company__item that indicate AI — used to supplement keyword matching
AI_SECTOR_CLASSES = {"ai"}


class SeedcampScraper(BaseScraper):
    name = "seedcamp"
    domain = "seedcamp.com"
    difficulty = "easy"
    source_url = "https://seedcamp.com/companies/"

    def scrape(self) -> List[ScrapedCompany]:
        soup = self._fetch_page()
        raw_companies = self._parse_companies(soup)
        logger.info(f"Parsed {len(raw_companies)} companies from Seedcamp")

        results: List[ScrapedCompany] = []
        for company in raw_companies:
            is_ai = self._detect_ai_with_sectors(company)
            tags = company.get("sector_tags", [])
            results.append(ScrapedCompany(
                name=company["name"],
                description=company.get("description"),
                website_url=company.get("website"),
                profile_url=self.source_url,
                industry=", ".join(tags) if tags else None,
                is_ai_startup=is_ai,
                batch=company.get("batch"),
                program="Seedcamp",
                source_url=self.source_url,
            ))

        return results

    def _fetch_page(self) -> BeautifulSoup:
        """Fetch the Seedcamp companies page and return a BeautifulSoup object."""
        response = requests.get(self.source_url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        logger.info(f"Downloaded {len(response.text):,} bytes")
        return BeautifulSoup(response.text, "html.parser")

    def _parse_companies(self, soup: BeautifulSoup) -> list[dict]:
        """Parse all company__item divs from the page."""
        items = soup.select("div.company__item")
        logger.info(f"Found {len(items)} company__item elements")

        companies = []
        for item in items:
            # Name
            name_el = item.select_one("span.company__item__name")
            name = name_el.get_text(strip=True) if name_el else None
            if not name:
                continue

            # Year of investment (stored as batch)
            year_el = item.select_one("h6.company__item__year")
            batch = year_el.get_text(strip=True) if year_el else None

            # Description
            desc_el = item.select_one("div.company__item__description__content")
            description = desc_el.get_text(strip=True) if desc_el else None

            # Website — the primary anchor link
            link_el = item.select_one("a.company__item__link[href]")
            website = link_el["href"] if link_el else None

            # Sector tags from CSS classes — filter out structural class names
            structural_classes = {"company__item", "mix"}
            raw_classes = set(item.get("class", []))
            sector_tags = sorted(raw_classes - structural_classes)

            companies.append({
                "name": name,
                "description": description,
                "batch": batch,
                "website": website,
                "sector_tags": sector_tags,
            })

        return companies

    def _detect_ai_with_sectors(self, company: dict) -> bool:
        """
        Word-boundary keyword check on description + sector tags.
        Also flags if the 'ai' CSS class is present on the company div.
        """
        # Direct AI sector class match
        if AI_SECTOR_CLASSES & set(company.get("sector_tags", [])):
            return True

        text = " ".join(filter(None, [
            company.get("description", ""),
            " ".join(company.get("sector_tags", [])),
        ]))
        return self.detect_ai(text)
