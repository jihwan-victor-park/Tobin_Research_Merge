"""
Columbia Entrepreneurship Startup Directory Scraper — queries the public REST
API at startups.columbia.edu for all companies.

Ported from Alastair branch to BaseScraper class.

API:
  GET /api/organizations?role=company&page_idx=N&sort=latest_update
  ~6,200 companies across ~311 pages.
"""

import logging
import re
import time
from typing import List, Optional

import requests

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://startups.columbia.edu/api/organizations"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class ColumbiaScraper(BaseScraper):
    name = "columbia"
    domain = "startups.columbia.edu"
    difficulty = "easy"
    source_url = "https://startups.columbia.edu"

    def _fetch_page(self, page_idx: int) -> dict:
        params = {
            "role": "company",
            "page_idx": page_idx,
            "sort": "latest_update",
        }
        response = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=20)
        response.raise_for_status()
        return response.json()

    def _parse_founded_year(self, org: dict) -> Optional[int]:
        founded_on = org.get("founded_on")
        if not founded_on:
            return None
        m = re.match(r"(\d{4})", str(founded_on))
        return int(m.group(1)) if m else None

    def scrape(self) -> List[ScrapedCompany]:
        # Get page count from first request
        first = self._fetch_page(1)
        meta = first.get("meta", {})
        page_count = meta.get("page_count", 1)
        total = meta.get("total", "?")
        logger.info(f"{total} companies across {page_count} pages")

        all_orgs = list(first.get("organizations", []))

        for page in range(2, page_count + 1):
            time.sleep(1)
            data = self._fetch_page(page)
            orgs = data.get("organizations", [])
            if not orgs:
                break
            all_orgs.extend(orgs)
            if page % 50 == 0 or page == page_count:
                logger.info(f"Page {page}/{page_count}: {len(all_orgs):,} total")

        # Normalize to ScrapedCompany
        results = []
        for org in all_orgs:
            name = org.get("name")
            if not name:
                continue

            stage = None
            lfe = org.get("last_funding_event")
            if isinstance(lfe, dict):
                stage = lfe.get("series")

            results.append(ScrapedCompany(
                name=name,
                website_url=org.get("homepage_url") or None,
                is_ai_startup=self.detect_ai(name),
                source_url=self.source_url,
            ))

        logger.info(f"Total: {len(results)} companies")
        return results
