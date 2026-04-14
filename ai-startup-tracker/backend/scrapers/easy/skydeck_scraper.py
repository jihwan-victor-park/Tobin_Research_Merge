"""
Berkeley SkyDeck Scraper — fetches all portfolio companies via a WordPress
AJAX endpoint in a single request.

Ported from Alastair branch (standalone script) to BaseScraper class.

Why AJAX endpoint instead of scraping HTML:
  SkyDeck's portfolio page loads companies dynamically via a WordPress AJAX
  action. A single POST to admin-ajax.php with action=company_filtration_query
  returns all 800+ companies as JSON — no pagination, no JS rendering needed.

API discovery:
  Found via DevTools Network tab -> filter by 'admin-ajax'. POST payload uses
  duplicate keys (meta[0][], meta[1][], meta[2][]) so must be sent as a list
  of tuples, not a dict. X-Requested-With: XMLHttpRequest header required.
"""

import logging
from typing import List

import requests

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# --- Config ---
AJAX_URL = "https://skydeck.berkeley.edu/wp-admin/admin-ajax.php"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}
# Duplicate keys require a list of tuples — a dict would silently drop repeats
PAYLOAD = [
    ("action", "company_filtration_query"),
    ("meta[0][]", "main_industry"),
    ("meta[0][]", "all"),
    ("meta[1][]", "classes"),
    ("meta[1][]", "all"),
    ("meta[2][]", "industry"),
    ("meta[2][]", "all"),
    ("search", ""),
]


class SkydeckScraper(BaseScraper):
    name = "skydeck"
    domain = "skydeck.berkeley.edu"
    difficulty = "easy"
    source_url = "https://skydeck.berkeley.edu/startups/"

    def scrape(self) -> List[ScrapedCompany]:
        raw_posts = self._fetch_companies()
        logger.info(f"Received {len(raw_posts)} companies from API")

        results: List[ScrapedCompany] = []
        for post in raw_posts:
            name = post.get("title", "").strip()
            is_ai = self.detect_ai(name)  # name-only -- low confidence

            results.append(ScrapedCompany(
                name=name,
                description=None,  # not available from this endpoint
                website_url=post.get("url") or None,
                profile_url=self.source_url,
                is_ai_startup=is_ai,
                batch=post.get("class") or None,
                program="Berkeley SkyDeck",
                confidence=0.5,  # low confidence -- name-only AI detection
                source_url=self.source_url,
            ))

        return results

    def _fetch_companies(self) -> list[dict]:
        """POST to the SkyDeck AJAX endpoint and return the raw posts list."""
        response = requests.post(AJAX_URL, data=PAYLOAD, headers=HEADERS, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get("posts", [])
