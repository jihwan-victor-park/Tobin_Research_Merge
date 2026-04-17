"""
Alchemist Accelerator Scraper — fetches all portfolio companies from
vault.alchemistaccelerator.com REST API.

Why API instead of HTML:
  The portfolio page (alchemistaccelerator.com/portfolio) is HubSpot CMS
  with only 5 featured companies in static HTML. The full 490-company
  dataset is loaded client-side from a JSON:API endpoint at
  vault.alchemistaccelerator.com.

API discovery:
  Found in inline JavaScript on the portfolio page:
  const gridBaseURL = 'https://vault.alchemistaccelerator.com/api/v1/
    alchemist_companies?include=aclass&fields[alchemist_classes]=number
    &filter[aclass.class_type:eq]=alchemist&page[size]=100'

Pagination:
  JSON:API page[number] parameter (1-indexed). Stop when page returns
  no data or total collected >= meta.results.available.

Fields available:
  name (only attribute returned by this endpoint)
  batch: cohort class number via included alchemist_classes relationship
  490 companies total across 5 pages of 100.
"""

import logging
import time
from typing import List
from urllib.parse import urlencode

import requests

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

API_BASE = "https://vault.alchemistaccelerator.com/api/v1/alchemist_companies"
PAGE_SIZE = 100
SOURCE_URL = "https://www.alchemistaccelerator.com/portfolio"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": SOURCE_URL,
}


class AlchemistScraper(BaseScraper):
    name = "alchemist"
    domain = "alchemistaccelerator.com"
    difficulty = "easy"
    source_url = SOURCE_URL

    def scrape(self) -> List[ScrapedCompany]:
        all_companies = []
        page = 1

        while True:
            params = {
                "include": "aclass",
                "fields[alchemist_classes]": "number",
                "filter[aclass.class_type:eq]": "alchemist",
                "page[size]": PAGE_SIZE,
                "page[number]": page,
            }
            # Build URL manually to preserve bracket syntax
            qs = "&".join(
                f"{k}={v}" for k, v in params.items()
            )
            url = f"{API_BASE}?{qs}"

            logger.info(f"Fetching page {page}: {url}")
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            data = response.json()

            companies = data.get("data", [])
            if not companies:
                logger.info("No more results — stopping.")
                break

            # Build class_id → class_number lookup from included records
            class_map = {
                item["id"]: item["attributes"]["number"]
                for item in data.get("included", [])
                if item.get("type") == "alchemist_classes"
            }

            for c in companies:
                name = (c.get("attributes", {}).get("name") or "").strip()
                if not name:
                    continue

                rel = c.get("relationships", {}).get("aclass", {}).get("data")
                class_num = class_map.get(rel["id"]) if rel else None
                batch = f"Class {class_num}" if class_num else None

                all_companies.append(ScrapedCompany(
                    name=name,
                    batch=batch,
                    program="Alchemist Accelerator",
                    source_url=SOURCE_URL,
                    profile_url=SOURCE_URL,
                    is_ai_startup=None,  # no description available
                ))

            total_available = data.get("meta", {}).get("results", {}).get("available", 0)
            logger.info(
                f"Page {page}: {len(companies)} companies "
                f"(total so far: {len(all_companies)} / {total_available})"
            )

            if len(all_companies) >= total_available:
                break

            page += 1
            time.sleep(0.3)

        return all_companies
