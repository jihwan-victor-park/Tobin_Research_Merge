"""
StartX Scraper — fetches web.startx.com/community and parses all portfolio
companies from the Webflow CMS pages using Finsweet list pagination.

Ported from Alastair branch to BaseScraper class.

Pagination:
  Finsweet CMS List uses a hashed query param: ?6a151520_page=N
  Increment N from 1 until the response contains no div.comn-list-item elements.
"""

import logging
import re
import time
from typing import List

import requests
from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://web.startx.com/community"
PAGE_PARAM = "6a151520_page"
RATE_LIMIT = 2

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class StartxScraper(BaseScraper):
    name = "startx"
    domain = "web.startx.com"
    difficulty = "easy"
    source_url = BASE_URL

    def scrape(self) -> List[ScrapedCompany]:
        all_companies = []
        page = 1

        while True:
            url = f"{BASE_URL}?{PAGE_PARAM}={page}"
            response = requests.get(url, headers=HEADERS, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            items = soup.select("div.comn-list-item")
            if not items:
                break

            for item in items:
                name_el = item.select_one("[fs-list-field='title']")
                name = name_el.get_text(strip=True) if name_el else None
                if not name:
                    continue

                desc_el = item.select_one("p[fs-list-field='description']")
                description = desc_el.get_text(strip=True) if desc_el else None

                batch_el = item.select_one("[fs-list-field='session']")
                batch = batch_el.get_text(strip=True) if batch_el else None

                industry_els = item.select("[fs-list-field='industry']")
                tags = [el.get_text(strip=True) for el in industry_els if el.get_text(strip=True)]

                year_el = item.select_one("[fs-list-field='year']")
                year_text = year_el.get_text(strip=True) if year_el else None
                founded_year = None
                if year_text:
                    m = re.search(r"\b(19|20)\d{2}\b", year_text)
                    if m:
                        founded_year = int(m.group())

                link_el = item.select_one("a.comn-list-link[href]")
                website = link_el["href"] if link_el else None

                text_for_ai = " ".join(filter(None, [description, " ".join(tags)]))

                all_companies.append(ScrapedCompany(
                    name=name,
                    description=description,
                    website_url=website,
                    batch=batch,
                    industry=", ".join(tags) if tags else None,
                    is_ai_startup=self.detect_ai(text_for_ai),
                    source_url=self.source_url,
                ))

            logger.info(f"Page {page}: {len(items)} companies")
            page += 1
            time.sleep(RATE_LIMIT)

        logger.info(f"Total: {len(all_companies)} companies")
        return all_companies
