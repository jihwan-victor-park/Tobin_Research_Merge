"""
Greylock Scraper — WordPress REST API, paginated.

Why API (not HTML):
  greylock.com exposes /wp-json/wp/v2/portfolio which returns all 157
  portfolio companies with name, Greylock profile URL, and sector tags.

The portfolio page renders company logos with JS-animated detail panels —
no external website URL is available in the API response or profile pages.
We store the Greylock profile URL as profile_url; dedup works on name.
"""
import logging
import time
from typing import List

import requests

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

API_BASE = "https://greylock.com/wp-json/wp/v2/portfolio"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
PER_PAGE = 100


class GreylockScraper(BaseScraper):
    name = "greylock"
    domain = "greylock.com"
    difficulty = "easy"
    source_url = "https://greylock.com/portfolio/"

    def scrape(self) -> List[ScrapedCompany]:
        companies = self._fetch_all_pages()
        logger.info("Greylock: fetched %d companies via WP REST API", len(companies))
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
                program="Greylock",
                source_url=self.source_url,
                is_ai_startup=self.detect_ai(f"{name} {description or ''}", keyword_only=True),
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
            logger.info("Greylock page %d/%d (%d companies so far)", page, total_pages, len(results))
            if page >= total_pages:
                break
            page += 1
            time.sleep(0.5)
        return results
