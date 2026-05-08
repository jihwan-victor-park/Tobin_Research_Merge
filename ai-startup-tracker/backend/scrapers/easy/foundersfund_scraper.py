"""
Founders Fund Scraper — WordPress REST API, paginated.

Why API (not HTML):
  foundersfund.com exposes /wp-json/wp/v2/company returning all 62
  portfolio companies with name, FF profile URL, and yoast description.
"""
import logging
import time
from typing import List

import requests

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

API_BASE = "https://foundersfund.com/wp-json/wp/v2/company"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
PER_PAGE = 100


class FoundersFundScraper(BaseScraper):
    name = "foundersfund"
    domain = "foundersfund.com"
    difficulty = "easy"
    source_url = "https://foundersfund.com/companies/"

    def scrape(self) -> List[ScrapedCompany]:
        companies = self._fetch_all_pages()
        logger.info("Founders Fund: fetched %d companies via WP REST API", len(companies))
        results = []
        for item in companies:
            name = item.get("title", {}).get("rendered", "").strip()
            if not name:
                continue
            profile_url = item.get("link", "")
            yoast = item.get("yoast_head_json", {}) or {}
            description = yoast.get("og_description") or yoast.get("description")
            results.append(ScrapedCompany(
                name=name,
                description=description,
                website_url=None,
                profile_url=profile_url or self.source_url,
                program="Founders Fund",
                source_url=self.source_url,
                is_ai_startup=self.detect_ai(f"{name} {description or ''}"),
                confidence=0.85,
            ))
        return results

    def _fetch_all_pages(self) -> list[dict]:
        results = []
        page = 1
        while True:
            r = requests.get(
                API_BASE,
                params={"per_page": PER_PAGE, "page": page},
                headers=HEADERS,
                timeout=30,
            )
            if r.status_code == 400:
                break
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            results.extend(batch)
            total_pages = int(r.headers.get("X-WP-TotalPages", 1))
            logger.info("Founders Fund page %d/%d (%d companies so far)", page, total_pages, len(results))
            if page >= total_pages:
                break
            page += 1
            time.sleep(0.5)
        return results
