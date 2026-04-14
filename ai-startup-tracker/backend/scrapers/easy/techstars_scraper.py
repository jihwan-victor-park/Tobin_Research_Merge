"""
Techstars Scraper — queries the Techstars Typesense API for all accelerator
portfolio companies.

Ported from Alastair branch (standalone script) to BaseScraper class.

Why Typesense instead of scraping HTML:
  Techstars' portfolio page is JS-rendered. Their search is powered by
  Typesense, which returns clean structured JSON — no HTML parsing needed.

API discovery:
  Found via browser DevTools Network tab. Filter by 'typesense' to see
  the search requests and extract the base URL and API key.
"""

import logging
import re
import time
from typing import List, Optional

import requests

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# --- Config ---
TYPESENSE_URL = "https://8gbms7c94riane0lp-1.a1.typesense.net/collections/companies/documents/search"
TYPESENSE_HEADERS = {
    "x-typesense-api-key": "0QKFSu4mIDX9UalfCNQN4qjg2xmukDE0",
}
PER_PAGE = 250


class TechstarsScraper(BaseScraper):
    name = "techstars"
    domain = "techstars.com"
    difficulty = "easy"
    source_url = "https://www.techstars.com/portfolio"

    def scrape(self) -> List[ScrapedCompany]:
        raw_docs = self._fetch_all_companies()
        logger.info(f"Total raw companies fetched: {len(raw_docs)}")

        results: List[ScrapedCompany] = []
        for doc in raw_docs:
            text = " ".join(filter(None, [
                doc.get("brief_description", ""),
                " ".join(doc.get("industry_vertical", [])),
            ]))
            is_ai = self.detect_ai(text)

            # Combine city + country for location
            city = doc.get("city")
            country = doc.get("country")

            tags = doc.get("industry_vertical", [])
            programs = doc.get("program_names", [])
            all_tags = tags + programs

            results.append(ScrapedCompany(
                name=doc.get("company_name"),
                description=doc.get("brief_description"),
                website_url=doc.get("website"),
                profile_url=self.source_url,
                industry=", ".join(all_tags) if all_tags else None,
                country=country,
                city=city,
                is_ai_startup=is_ai,
                batch=str(doc["first_session_year"]) if doc.get("first_session_year") else None,
                program="Techstars",
                source_url=self.source_url,
            ))

        return results

    def _fetch_page(self, page: int) -> dict:
        """Fetch one page of Techstars accelerator companies from Typesense."""
        params = {
            "q": "",
            "query_by": "company_name,brief_description",
            "filter_by": "is_accelerator_company:=true",
            "per_page": PER_PAGE,
            "page": page,
        }
        response = requests.get(
            TYPESENSE_URL, headers=TYPESENSE_HEADERS, params=params, timeout=15
        )
        response.raise_for_status()
        return response.json()

    def _fetch_all_companies(self) -> list[dict]:
        """Paginate through all Typesense results until no hits are returned."""
        all_hits = []
        page = 1  # Typesense pages are 1-indexed

        while True:
            logger.info(f"Fetching page {page} ...")
            data = self._fetch_page(page)
            hits = [h["document"] for h in data.get("hits", [])]

            if not hits:
                logger.info(f"No hits on page {page} -- pagination complete.")
                break

            all_hits.extend(hits)
            logger.info(
                f"Got {len(hits)} hits (total so far: {len(all_hits)} "
                f"of {data.get('found', '?')})"
            )

            # Stop if we've collected everything
            if len(all_hits) >= data.get("found", 0):
                break

            page += 1
            time.sleep(0.3)  # be polite

        return all_hits
