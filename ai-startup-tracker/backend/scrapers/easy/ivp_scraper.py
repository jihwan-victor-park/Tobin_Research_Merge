"""
IVP (Institutional Venture Partners) Portfolio Scraper — BeautifulSoup, single page.

Why slug extraction (not API):
  ivp.com renders all 157 portfolio companies as anchor.portfolio-grid-item
  links to /portfolio/{slug}/. The company name is not in the static HTML
  (only logo images are rendered); it is derived from the URL slug.

Card structure (per company):
  ul.portfolio-grid
    a.portfolio-grid-item[href="/portfolio/{slug}/"]
      div.company-logo
        img[alt]               → company name (sometimes present)
"""
import logging
import re
from typing import List

import requests
from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SOURCE_URL = "https://www.ivp.com/portfolio/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def _slug_to_name(slug: str) -> str:
    return " ".join(w.capitalize() for w in slug.replace("-", " ").split())


class IVPScraper(BaseScraper):
    name = "ivp"
    domain = "ivp.com"
    difficulty = "easy"
    source_url = SOURCE_URL

    def scrape(self) -> List[ScrapedCompany]:
        r = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        portfolio_grid = soup.find("ul", class_="portfolio-grid")
        if not portfolio_grid:
            logger.error("IVP: portfolio-grid not found")
            return []

        links = portfolio_grid.find_all("a", href=re.compile(r"/portfolio/"))
        logger.info("IVP: found %d portfolio links", len(links))

        results = []
        seen = set()
        for a in links:
            href = a["href"]
            slug = href.rstrip("/").split("/")[-1]
            if not slug or slug in seen:
                continue
            seen.add(slug)

            # Try img alt for company name, fall back to slug
            img = a.find("img")
            name = (img.get("alt") or "").strip() if img else ""
            if not name:
                name = _slug_to_name(slug)

            profile_url = f"https://www.ivp.com{href}" if href.startswith("/") else href
            is_ai = self.detect_ai(name)

            results.append(ScrapedCompany(
                name=name,
                description=None,
                website_url=None,
                profile_url=profile_url,
                program="Institutional Venture Partners (IVP)",
                source_url=SOURCE_URL,
                is_ai_startup=is_ai,
                confidence=0.9,
            ))

        logger.info("IVP: parsed %d companies", len(results))
        return results
