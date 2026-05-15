"""
Google Ventures (GV) Portfolio Scraper — BeautifulSoup, single page.

Why HTML (not API):
  gv.com serves all 1288 portfolio companies server-rendered as
  span.company-name elements inside a div.companies-list accordion.
  No company websites or descriptions are available in the static HTML —
  only company names (with trailing * for exited/acquired companies).

Card structure (per company):
  div.companies-list
    div.synchronized-accordion-item (per letter group)
      span.company-name              → company name (* = exited)
"""
import logging
from typing import List

import requests
from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SOURCE_URL = "https://www.gv.com/portfolio/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


class GVScraper(BaseScraper):
    name = "gv"
    domain = "gv.com"
    difficulty = "easy"
    source_url = SOURCE_URL

    def scrape(self) -> List[ScrapedCompany]:
        r = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        name_els = soup.find_all(class_="company-name")
        logger.info("GV: found %d company-name elements", len(name_els))

        results = []
        seen = set()
        for el in name_els:
            raw = el.get_text(strip=True)
            name = raw.rstrip("* ").strip()
            if not name or name in seen:
                continue
            seen.add(name)

            is_ai = self.detect_ai(name)

            results.append(ScrapedCompany(
                name=name,
                description=None,
                website_url=None,
                profile_url=SOURCE_URL,
                program="Google Ventures (GV)",
                source_url=SOURCE_URL,
                is_ai_startup=is_ai,
                confidence=0.85,
            ))

        logger.info("GV: parsed %d companies", len(results))
        return results
