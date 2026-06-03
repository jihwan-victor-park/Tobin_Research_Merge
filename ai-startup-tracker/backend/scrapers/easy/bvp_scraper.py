"""
Bessemer Venture Partners Scraper — BeautifulSoup, single page.

Why HTML (not API):
  bvp.com serves all 512 portfolio companies in server-rendered HTML as
  article.box.investment elements. Each article contains both a card view
  and a detail overlay (duplicating the name), along with an external
  company website URL, description paragraph, and sector tag links.

Card structure (per company):
  article.box.investment.with-overlay-on-open
    div.max-width
      div.company
        h3.h-module-h3.name   → company name (appears twice: card + overlay)
      p                        → description (in overlay section)
      a[href=external_url]     → company website (external, in overlay)
      a[href=/ai or /fintech…] → sector tags (relative internal links)
"""
import logging
import re
from typing import List

import requests
from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SOURCE_URL = "https://www.bvp.com/companies"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

# Sector links are short relative paths like /ai, /fintech, /cloud
_SECTOR_HREF_RE = re.compile(r"^/[a-z-]+$")


class BVPScraper(BaseScraper):
    name = "bvp"
    domain = "bvp.com"
    difficulty = "easy"
    source_url = SOURCE_URL

    def scrape(self) -> List[ScrapedCompany]:
        r = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        articles = soup.select("article.investment")
        logger.info("BVP: found %d investment articles", len(articles))

        results = []
        for art in articles:
            # Name: first h3 in the article
            name_el = art.find("h3")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name:
                continue

            # External website: first http link not on bvp.com
            website = next(
                (
                    a["href"]
                    for a in art.find_all("a", href=True)
                    if a["href"].startswith("http") and "bvp.com" not in a["href"]
                    and "linkedin" not in a["href"]
                ),
                None,
            )

            # Description: first substantial paragraph
            desc_el = next(
                (p for p in art.find_all("p") if len(p.get_text(strip=True)) > 30),
                None,
            )
            description = desc_el.get_text(strip=True) if desc_el else None

            # Sector: short single-word relative links (/ai, /fintech, /cloud…)
            sector_links = [
                a.get_text(strip=True)
                for a in art.find_all("a", href=True)
                if _SECTOR_HREF_RE.match(a.get("href", "")) and a.get_text(strip=True)
            ]
            # Deduplicate while preserving order
            seen: set[str] = set()
            sectors: list[str] = []
            for s in sector_links:
                if s not in seen:
                    seen.add(s)
                    sectors.append(s)
            industry = ", ".join(sectors[:2]) if sectors else None

            is_ai = self.detect_ai(f"{name} {description or ''} {industry or ''}", keyword_only=True)

            results.append(ScrapedCompany(
                name=name,
                description=description,
                website_url=website,
                profile_url=f"https://www.bvp.com/companies/{name.lower().replace(' ', '-')}",
                industry=industry,
                program="Bessemer Venture Partners",
                source_url=SOURCE_URL,
                is_ai_startup=is_ai,
                confidence=0.9,
            ))

        logger.info("BVP: parsed %d companies", len(results))
        return results
