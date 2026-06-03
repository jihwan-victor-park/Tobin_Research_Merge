"""
Andreessen Horowitz (a16z) Portfolio Scraper — JS variable extraction.

Why JS extraction (not BeautifulSoup):
  The portfolio page embeds all 836+ companies in a window.a16z_portfolio_companies
  JavaScript array (not rendered into individual DOM elements). The array is
  assigned inline in the HTML and contains the full company payload including
  name, website, description (overview), investment stage, and founders.

Data extracted per company:
  window.a16z_portfolio_companies[*]
    title             → company name
    web               → website URL
    overview          → description
    stage             → investment stage list (e.g. ["venture"], ["growth"])
    year_founded      → founding year (often blank)
    founders          → comma-separated founder names (often blank)
"""
import json
import logging
import re
from typing import List

import requests

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SOURCE_URL = "https://a16z.com/portfolio/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
_VAR_RE = re.compile(r"window\.a16z_portfolio_companies\s*=\s*(\[.*)", re.DOTALL)


class A16ZScraper(BaseScraper):
    name = "a16z"
    domain = "a16z.com"
    difficulty = "easy"
    source_url = SOURCE_URL

    def scrape(self) -> List[ScrapedCompany]:
        r = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()

        m = _VAR_RE.search(r.text)
        if not m:
            logger.error("a16z: window.a16z_portfolio_companies not found in page")
            return []

        raw = m.group(1)
        # Walk to the closing ] of the top-level array
        bracket, end = 0, 0
        for i, ch in enumerate(raw):
            if ch == "[":
                bracket += 1
            elif ch == "]":
                bracket -= 1
                if bracket == 0:
                    end = i + 1
                    break
        try:
            companies = json.loads(raw[:end])
        except json.JSONDecodeError as exc:
            logger.error("a16z: JSON parse failed: %s", exc)
            return []

        logger.info("a16z: found %d companies in JS array", len(companies))
        return self._parse(companies)

    def _parse(self, companies: list) -> List[ScrapedCompany]:
        results = []
        for c in companies:
            name = (c.get("title") or "").strip()
            if not name or name == "[untitled]":
                continue

            website = (c.get("web") or "").strip() or None
            description = (c.get("overview") or "").strip() or None
            stage_list = c.get("stage") or []
            stage = stage_list[0] if stage_list else None

            founded_raw = (c.get("year_founded") or "").strip()
            founded_year = None
            if founded_raw and founded_raw.isdigit():
                founded_year = int(founded_raw)

            is_ai = self.detect_ai(f"{name} {description or ''}", keyword_only=True)

            results.append(ScrapedCompany(
                name=name,
                description=description,
                website_url=website,
                profile_url=f"https://a16z.com/companies/{name.lower().replace(' ', '-').replace('.', '')}/",
                stage=stage,
                source_url=SOURCE_URL,
                program="Andreessen Horowitz (a16z)",
                is_ai_startup=is_ai,
                confidence=0.9,
            ))

        logger.info("a16z: parsed %d valid companies", len(results))
        return results
