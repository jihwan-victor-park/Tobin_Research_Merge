"""
Rice Alliance OwlSpark Scraper — fetches alliance.rice.edu/owlspark/ventures
and parses all cohort companies from the static server-rendered accordion HTML.

Ported from Alastair branch to BaseScraper class.

Structure:
  Class header : span.item-title  (e.g. "Class 13 | May 15 - August 1, 2025")
  Panel        : div.accordion-panel > ul > li
  Name         : <strong> tag within each li
"""

import logging
import re
from typing import List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

URL = "https://alliance.rice.edu/owlspark/ventures"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class RiceOwlsparkScraper(BaseScraper):
    name = "rice_owlspark"
    domain = "alliance.rice.edu"
    difficulty = "easy"
    source_url = URL

    def _parse_cohort_year(self, header_text: str) -> Optional[int]:
        m = re.search(r"\b(20\d{2})\b", header_text)
        return int(m.group(1)) if m else None

    def _parse_batch(self, header_text: str) -> str:
        parts = header_text.split("|", 1)
        return parts[0].strip()

    def _parse_li(self, li) -> Tuple[Optional[str], Optional[str]]:
        strong = li.find("strong")
        if strong:
            name = strong.get_text(strip=True)
            full_text = re.sub(r"\s+", " ", li.get_text(" ", strip=True)).strip()
            return name, full_text if full_text else None

        a = li.find("a")
        if a:
            return a.get_text(strip=True), None

        name = li.get_text(strip=True)
        return (name, None) if name else (None, None)

    def scrape(self) -> List[ScrapedCompany]:
        response = requests.get(URL, headers=HEADERS, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        results = []
        accordion_items = soup.select("li:has(button.accordion-trigger)")

        for item in accordion_items:
            header_el = item.select_one("span.item-title")
            if not header_el:
                continue
            header_text = header_el.get_text(strip=True)
            batch = self._parse_batch(header_text)

            panel = item.select_one("div.accordion-panel")
            if not panel:
                continue

            for li in panel.select("ul > li"):
                name, description = self._parse_li(li)
                if not name:
                    continue

                text_for_ai = description or name
                results.append(ScrapedCompany(
                    name=name,
                    description=description,
                    batch=batch,
                    is_ai_startup=self.detect_ai(text_for_ai),
                    source_url=self.source_url,
                ))

        logger.info(f"Total: {len(results)} companies")
        return results
