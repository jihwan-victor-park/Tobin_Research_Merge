"""
Entrepreneur First (EF) Scraper — fetches portfolio companies via the
WordPress AJAX filter endpoint.

Ported from Alastair branch (standalone script) to BaseScraper class.

Why AJAX endpoint instead of scraping HTML:
  EF's portfolio page loads companies dynamically via a WordPress AJAX
  action. POSTing to admin-ajax.php with the right params returns paginated
  HTML fragments containing all company tiles — no JS rendering needed.

API discovery:
  Found via DevTools Network tab -> filter by 'admin-ajax' to see the POST
  request, then inspect the form data payload.
"""

import json
import logging
import re
import time
from typing import List

import requests
from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# --- Config ---
AJAX_URL = "https://www.joinef.com/wp-admin/admin-ajax.php"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
# Company IDs excluded by EF's own frontend (placeholder/admin entries)
EXCLUDED_IDS = [
    12720, 12721, 12722, 12723, 12724, 12725, 12727, 12728, 12729, 12730,
    12731, 12732, 12733, 12734, 12735, 12736, 12737, 12738, 12739, 12740,
    12741, 12742, 12743, 13192,
]
POSTS_PER_PAGE = 24


class EFScraper(BaseScraper):
    name = "entrepreneur_first"
    domain = "joinef.com"
    difficulty = "easy"
    source_url = "https://www.joinef.com/companies/"

    def scrape(self) -> List[ScrapedCompany]:
        raw_companies = self._fetch_all_companies()
        logger.info(f"Total parsed: {len(raw_companies)}")

        results: List[ScrapedCompany] = []
        for company in raw_companies:
            text = " ".join(filter(None, [
                company.get("description", ""),
                " ".join(company.get("tags", [])),
            ]))
            is_ai = self.detect_ai(text)

            tags = company.get("tags", [])
            results.append(ScrapedCompany(
                name=company["name"],
                description=company.get("description"),
                website_url=None,  # not included in the listing tiles
                profile_url=self.source_url,
                industry=", ".join(tags) if tags else None,
                country=None,
                city=company.get("location"),
                is_ai_startup=is_ai,
                program="Entrepreneur First",
                source_url=self.source_url,
            ))

        return results

    def _fetch_page(self, page: int) -> dict:
        """POST to the WordPress AJAX endpoint for one page of companies."""
        query = json.dumps({
            "post_type": "company",
            "paged": page,
            "post_status": "publish",
            "post__not_in": EXCLUDED_IDS,
            "orderby": "menu_order",
            "order": "ASC",
            "posts_per_page": POSTS_PER_PAGE,
        })
        response = requests.post(
            AJAX_URL,
            headers=HEADERS,
            data={"action": "filter", "query": query},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def _parse_tiles(self, html_content: str) -> list[dict]:
        """Parse company tiles from the HTML fragment returned by the AJAX endpoint."""
        soup = BeautifulSoup(html_content, "html.parser")
        companies = []

        for tile in soup.select("div.tile--company"):
            # Name -- prefer the h4 heading, fall back to data attribute
            name_el = tile.select_one("h4.tile__name")
            name = name_el.get_text(strip=True) if name_el else None
            if not name:
                link_el = tile.select_one("div.tile__link[data-companyname]")
                name = link_el["data-companyname"] if link_el else None

            # Description
            desc_el = tile.select_one("div.tile__description")
            description = desc_el.get_text(strip=True) if desc_el else None

            # Founded year
            founded_year = None
            for row in tile.select("div.meta__row"):
                cols = row.select("div.col")
                if len(cols) == 2:
                    label = cols[0].get_text(strip=True)
                    value = cols[1].get_text(strip=True)
                    if label == "Founded" and re.match(r"^\d{4}$", value):
                        founded_year = int(value)
                        break

            # Location
            loc_el = tile.select_one("a.locationtag")
            location = loc_el.get_text(strip=True) if loc_el else None

            # Industry tags
            tags = [el.get_text(strip=True) for el in tile.select("a.categorytag")]

            companies.append({
                "name": name,
                "description": description,
                "founded_year": founded_year,
                "location": location,
                "tags": tags,
            })

        return companies

    def _fetch_all_companies(self) -> list[dict]:
        """Paginate through all AJAX pages using max_page from the first response."""
        logger.info("Fetching page 1 ...")
        data = self._fetch_page(1)
        max_page = data.get("max_page", 1)
        found_posts = data.get("found_posts", 0)
        logger.info(f"Found {found_posts} companies across {max_page} pages")

        all_companies = self._parse_tiles(data.get("content", ""))
        logger.info(f"Page 1: {len(all_companies)} companies parsed")

        for page in range(2, max_page + 1):
            logger.info(f"Fetching page {page}/{max_page} ...")
            data = self._fetch_page(page)
            content = data.get("content", "")
            if not content:
                logger.info(f"Empty content on page {page} -- stopping.")
                break
            batch = self._parse_tiles(content)
            all_companies.extend(batch)
            logger.info(f"Page {page}: {len(batch)} companies (total: {len(all_companies)})")
            time.sleep(0.5)

        return all_companies
