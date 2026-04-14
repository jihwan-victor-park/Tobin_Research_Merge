"""
YC Scraper — queries the YC Algolia API directly and maps fields in Python.

Ported from Alastair branch (standalone script) to BaseScraper class.

Why Algolia instead of scraping HTML:
  YC's companies page is JavaScript-rendered, so requests only returns an
  empty shell. YC uses Algolia for their search — querying it directly gives
  us clean, structured JSON without any HTML parsing.

Pagination strategy:
  Algolia caps results at 1000 per query regardless of hitsPerPage.
  To get all 4000+ companies we query per-batch (e.g. "Winter 2024"),
  collect results, then deduplicate by company name.
"""

import logging
import re
import time
from typing import List, Optional
from urllib.parse import quote

import requests

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# --- Config ---
ALGOLIA_URL = (
    "https://45bwzj1sgc-dsn.algolia.net/1/indexes/*/queries"
    "?x-algolia-application-id=45BWZJ1SGC"
    "&x-algolia-api-key=NzllNTY5MzJiZGM2OTY2ZTQwMDEzOTNhYWZiZGRjODlhYzVkNjBmOGRjNzJiMWM4ZTU0ZDlhYTZjOTJiMjlhMWFuYWx5dGljc1RhZ3M9eWNkYyZyZXN0cmljdEluZGljZXM9WUNDb21wYW55X3Byb2R1Y3Rpb24lMkNZQ0NvbXBhbnlfQnlfTGF1bmNoX0RhdGVfcHJvZHVjdGlvbiZ0YWdGaWx0ZXJzPSU1QiUyMnljZGNfcHVibGljJTIyJTVE"
)
ALGOLIA_HEADERS = {
    "Content-Type": "application/json",
}
HITS_PER_PAGE = 1000

# Map Algolia's full season names to short batch codes e.g. "Winter 2009" -> "W09"
SEASON_PREFIX = {
    "winter": "W",
    "spring": "Sp",
    "summer": "S",
    "fall": "F",
}

# All YC batch seasons and year range to query
SEASONS = ["Winter", "Summer"]
BATCH_YEAR_START = 2005
BATCH_YEAR_END = 2026  # update annually as new batches are added


def normalize_batch(raw_batch: Optional[str]) -> Optional[str]:
    """
    Convert Algolia's full batch name to short form.
    "Winter 2009" -> "W09", "Summer 2013" -> "S13"
    Returns raw value as-is if format is unrecognised.
    """
    if not raw_batch:
        return None
    parts = raw_batch.strip().split()
    if len(parts) != 2:
        return raw_batch
    season, year = parts[0].lower(), parts[1]
    prefix = SEASON_PREFIX.get(season)
    if not prefix or len(year) != 4:
        return raw_batch
    return f"{prefix}{year[2:]}"  # e.g. "W09"


def extract_founded_year(hit: dict) -> Optional[int]:
    """
    Attempt to extract a founding year from long_description using regex.

    Algolia has no dedicated founded_year field — launched_at is the YC profile
    creation date, not the founding date, so it's unreliable.
    """
    description = hit.get("long_description", "") or ""
    match = re.search(
        r"(?:founded|incorporated|established|started|launched)\b.{0,40}?\b((?:19|20)\d{2})\b",
        description,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1))
    return None


class YCScraper(BaseScraper):
    name = "yc"
    domain = "ycombinator.com"
    difficulty = "easy"
    source_url = "https://www.ycombinator.com/companies"

    def scrape(self) -> List[ScrapedCompany]:
        raw_hits = self._fetch_all_companies()
        logger.info(f"Total unique companies fetched: {len(raw_hits)}")

        results: List[ScrapedCompany] = []
        for hit in raw_hits:
            text = " ".join(filter(None, [
                hit.get("one_liner", ""),
                hit.get("long_description", ""),
                " ".join(hit.get("tags", [])),
            ]))
            is_ai = self.detect_ai(text)

            location = hit.get("all_locations")
            country = None
            city = None
            if location:
                parts = [p.strip() for p in location.split(",")]
                if len(parts) >= 2:
                    city = parts[0]
                    country = parts[-1]
                elif len(parts) == 1:
                    country = parts[0]

            tags = hit.get("tags", [])
            industries = hit.get("industries", [])
            all_tags = tags + industries
            if hit.get("subindustry"):
                all_tags.append(hit["subindustry"])

            results.append(ScrapedCompany(
                name=hit.get("name"),
                description=hit.get("one_liner"),
                website_url=hit.get("website"),
                profile_url=f"https://www.ycombinator.com/companies/{hit.get('slug', '')}",
                industry=", ".join(all_tags) if all_tags else None,
                country=country,
                city=city,
                is_ai_startup=is_ai,
                batch=normalize_batch(hit.get("batch")),
                program="Y Combinator",
                source_url=self.source_url,
            ))

        return results

    def _fetch_batch(self, batch_name: str) -> list[dict]:
        """Query Algolia filtered to a single batch e.g. 'Winter 2024'."""
        encoded_filter = quote(f'batch:"{batch_name}"')
        params = f"hitsPerPage={HITS_PER_PAGE}&page=0&filters={encoded_filter}"
        body = {
            "requests": [
                {
                    "indexName": "YCCompany_production",
                    "params": params,
                }
            ]
        }
        response = requests.post(ALGOLIA_URL, headers=ALGOLIA_HEADERS, json=body, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data["results"][0]["hits"]

    def _fetch_all_companies(self) -> list[dict]:
        """
        Fetch all YC companies by querying each batch individually.
        Deduplicates by objectID (Algolia's unique company identifier).
        """
        seen_ids: set[str] = set()
        all_hits: list[dict] = []

        batches = [
            f"{season} {year}"
            for year in range(BATCH_YEAR_START, BATCH_YEAR_END + 1)
            for season in SEASONS
        ]

        for batch_name in batches:
            hits = self._fetch_batch(batch_name)
            if not hits:
                continue

            new_hits = [h for h in hits if h["objectID"] not in seen_ids]
            seen_ids.update(h["objectID"] for h in new_hits)
            all_hits.extend(new_hits)
            logger.info(
                f"{batch_name}: {len(hits)} hits, {len(new_hits)} new "
                f"(total: {len(all_hits)})"
            )

            # Be polite — small delay between requests
            time.sleep(0.3)

        return all_hits
