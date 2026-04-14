"""
Antler Portfolio Scraper — fetches all portfolio companies from
antler.co/portfolio using paginated Webflow CMS with Finsweet.

Ported from Alastair branch (standalone script) to BaseScraper class.

Why BeautifulSoup (not Playwright):
  The site uses Webflow CMS with Finsweet cmslist pagination, which exposes
  a clean GET-based page parameter. Each page is fully server-rendered HTML —
  no JavaScript execution required. Pagination works via ?{hash}_page=N.

Pagination:
  The hash key (e.g. 0b933bfd) is Webflow-generated and could change.
  We detect it from the 'a.w-pagination-next' link on the current page
  rather than hardcoding it.

Selectors (confirmed from HTML inspection):
  Card container : div.portco_card (inside div.portco_cms_wrap)
  Name           : p[fs-cmsfilter-field="name"]
  Description    : p[fs-cmsfilter-field="description"]
  Location       : div.tag_small_wrap (non-sector, non-year) -> div.tag_small_text
  Sector         : div.tag_small_wrap[fs-cmsfilter-field="sector"] .tag_small_text
  Year           : div.tag_small_wrap[fs-cmsfilter-field="year"] .tag_small_text
  Website        : a.clickable_link[href]
"""

import logging
import re
import time
from typing import List, Optional
from urllib.parse import parse_qs

import requests
from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.antler.co/portfolio"
RATE_LIMIT = 1  # seconds between page requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class AntlerScraper(BaseScraper):
    name = "antler"
    domain = "antler.co"
    difficulty = "easy"
    source_url = "https://www.antler.co/portfolio"

    def scrape(self) -> List[ScrapedCompany]:
        all_raw = []
        page = 1
        hash_key_href = None

        while True:
            if page == 1:
                url = BASE_URL
            else:
                url = self._build_page_url(hash_key_href, page)

            logger.info(f"Page {page}: {url}")
            soup = self._fetch(url)
            companies = self._parse_cards(soup)
            logger.info(f"Page {page}: {len(companies)} companies")

            if not companies:
                logger.info("No cards found -- stopping.")
                break

            all_raw.extend(companies)

            next_href = self._detect_next_page(soup)
            if not next_href:
                logger.info("No next-page link -- reached last page.")
                break

            if hash_key_href is None:
                hash_key_href = next_href

            page += 1
            time.sleep(RATE_LIMIT)

        logger.info(f"Total fetched: {len(all_raw)}")

        results: List[ScrapedCompany] = []
        for company in all_raw:
            text = " ".join(filter(None, [
                company.get("description", ""),
                company.get("sector", ""),
            ]))
            is_ai = self.detect_ai(text)

            results.append(ScrapedCompany(
                name=company["name"],
                description=company.get("description"),
                website_url=company.get("website"),
                profile_url=self.source_url,
                industry=company.get("sector"),
                country=None,
                city=company.get("location"),
                is_ai_startup=is_ai,
                program="Antler",
                source_url=self.source_url,
            ))

        return results

    def _fetch(self, url: str) -> BeautifulSoup:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    def _detect_next_page(self, soup: BeautifulSoup) -> Optional[str]:
        """Return the href of the next-page link, or None if on the last page."""
        link = soup.select_one("a.w-pagination-next[href]")
        return link["href"] if link else None

    def _build_page_url(self, next_href: str, page: int) -> str:
        """
        Extract the hash key from a next-page href like '?0b933bfd_page=2'
        and build the URL for the requested page number.
        """
        qs = next_href.lstrip("?")
        for key in parse_qs(qs):
            if key.endswith("_page"):
                return f"{BASE_URL}?{key}={page}"
        return f"{BASE_URL}?{qs.rsplit('=', 1)[0]}={page}"

    def _parse_cards(self, soup: BeautifulSoup) -> list[dict]:
        """Parse all div.portco_card elements from a page."""
        cards = soup.select("div.portco_cms_wrap div.portco_card")
        companies = []

        for card in cards:
            name_el = card.select_one('p[fs-cmsfilter-field="name"]')
            name = name_el.get_text(strip=True) if name_el else None
            if not name:
                continue

            desc_el = card.select_one('p[fs-cmsfilter-field="description"]')
            description = desc_el.get_text(strip=True) if desc_el else None

            location = None
            sector = None
            year_text = None
            for wrap in card.select("div.tag_small_wrap"):
                field = wrap.get("fs-cmsfilter-field", "")
                text_el = wrap.select_one("div.tag_small_text")
                text = text_el.get_text(strip=True) if text_el else None
                if not text:
                    continue
                if field == "sector":
                    sector = text
                elif field == "year":
                    year_text = text
                else:
                    location = text

            founded_year = None
            if year_text:
                m = re.search(r"\b(19|20)\d{2}\b", year_text)
                if m:
                    founded_year = int(m.group())

            website_el = card.select_one("a.clickable_link[href]")
            website = website_el["href"] if website_el else None

            companies.append({
                "name": name,
                "description": description,
                "location": location,
                "sector": sector,
                "founded_year": founded_year,
                "website": website,
            })

        return companies
