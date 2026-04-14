"""
Princeton Keller Center eLab Scraper — fetches all eLab portfolio companies
from a Drupal server-rendered site with two-pass approach (listing + detail pages).

Ported from Alastair branch to BaseScraper class.

Two-pass approach:
  Pass 1 — listing pages: extract name, short description, program track, cohort year, detail URL
  Pass 2 — detail pages: fetch each company's detail page for full description
"""

import logging
import re
import time
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_LISTING_URL = (
    "https://kellercenter.princeton.edu/people/teams-startups-filtered"
    "?program-filter%5B18%5D=18"
)
DETAIL_BASE = "https://kellercenter.princeton.edu"
TOTAL_PAGES = 9
RATE_LIMIT = 1.5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class PrincetonScraper(BaseScraper):
    name = "princeton_keller"
    domain = "kellercenter.princeton.edu"
    difficulty = "easy"
    source_url = BASE_LISTING_URL

    def _listing_url(self, page: int) -> str:
        if page == 0:
            return BASE_LISTING_URL
        return f"{BASE_LISTING_URL}&page={page}"

    def _fetch(self, url: str) -> BeautifulSoup:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    def _parse_listing_page(self, soup: BeautifulSoup) -> list[dict]:
        companies = []
        view_content = soup.select_one("div.view-content")
        if not view_content:
            return companies

        current_year = None
        for child in view_content.children:
            if not hasattr(child, "name"):
                continue

            if child.name == "h2" and "group-title" in child.get("class", []):
                m = re.search(r"(20\d{2})", child.get_text())
                current_year = m.group(1) if m else child.get_text(strip=True)
                continue

            if child.name == "div" and "group-status" in child.get("class", []):
                for row in child.find_all("div", class_="views-row"):
                    card = row.select_one("div.node--type-startup-team")
                    if not card:
                        continue

                    name_el = card.select_one("div.field--name-node-title p")
                    name = name_el.get_text(strip=True) if name_el else None
                    if not name:
                        continue

                    track_el = card.select_one("div.field--name-startup-team-program")
                    program_track = track_el.get_text(strip=True) if track_el else None

                    subtitle_link = card.select_one("div.field--name-field-subtitle a")
                    short_desc = subtitle_link.get_text(strip=True) if subtitle_link else None
                    detail_path = subtitle_link.get("href", "") if subtitle_link else ""
                    detail_url = urljoin(DETAIL_BASE, detail_path) if detail_path else None

                    companies.append({
                        "name": name,
                        "short_desc": short_desc,
                        "program_track": program_track,
                        "cohort_year": current_year,
                        "detail_url": detail_url,
                    })

        return companies

    def _fetch_detail_description(self, detail_url: str) -> Optional[str]:
        try:
            soup = self._fetch(detail_url)
            content = (
                soup.select_one("div.field--name-field-text")
                or soup.select_one("div.field--name-field-description")
                or soup.select_one("div.field--name-body")
            )

            if content:
                text = " ".join(
                    p.get_text(strip=True) for p in content.find_all("p") if p.get_text(strip=True)
                )
                if not text:
                    text = content.get_text(strip=True)
            else:
                paragraphs = [
                    p.get_text(strip=True) for p in soup.select("main p")
                    if p.get_text(strip=True)
                    and "Princeton University" not in p.get_text()
                    and not p.find_parent(["nav", "footer"])
                ]
                text = " ".join(paragraphs)

            if not text or len(text) < 30 or text.startswith("Princeton University"):
                return None
            return text
        except Exception as e:
            logger.warning(f"Detail page failed ({detail_url}): {e}")
            return None

    def scrape(self) -> List[ScrapedCompany]:
        # Pass 1: listing pages
        all_raw = []
        for page in range(TOTAL_PAGES):
            url = self._listing_url(page)
            soup = self._fetch(url)
            cards = self._parse_listing_page(soup)
            logger.info(f"Listing page {page}: {len(cards)} cards")
            all_raw.extend(cards)
            if page < TOTAL_PAGES - 1:
                time.sleep(RATE_LIMIT)

        # Pass 2: detail pages
        for i, raw in enumerate(all_raw):
            if not raw.get("detail_url"):
                continue
            raw["full_desc"] = self._fetch_detail_description(raw["detail_url"])
            time.sleep(RATE_LIMIT)

        # Build ScrapedCompany list
        results = []
        for raw in all_raw:
            description = raw.get("full_desc") or raw.get("short_desc")
            results.append(ScrapedCompany(
                name=raw["name"],
                description=description,
                batch=raw.get("cohort_year"),
                program=raw.get("program_track"),
                is_ai_startup=self.detect_ai(description or ""),
                source_url=self.source_url,
            ))

        logger.info(f"Total: {len(results)} companies")
        return results
