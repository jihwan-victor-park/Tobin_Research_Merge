"""
Index Ventures Scraper — BeautifulSoup, single page.

Why HTML (not API):
  indexventures.com server-renders all ~370 portfolio companies as
  li.companies__relationships__list__item.js-company elements.
  Each li carries data-sectors and data-regions JSON attributes alongside
  the company name and a profile slug — no JavaScript required.

Card structure (per company):
  li.companies__relationships__list__item.js-company
    data-sectors='["aiml","fintech",...]'   → sector tags (JSON list)
    data-regions='["north-america",...]'    → region tags (JSON list)
    a.companies__relationships__list__item__link[href=/companies/slug/]
      text                                  → company name
      span.ticker-symbol                    → stock ticker (optional, strip)
"""
import json
import logging
from typing import List

import requests
from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.indexventures.com"
SOURCE_URL = f"{BASE_URL}/companies"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

# Index Ventures sector tag that signals an AI company
_AI_SECTORS = {"aiml", "ai", "ml"}


class IndexVenturesScraper(BaseScraper):
    name = "indexventures"
    domain = "indexventures.com"
    difficulty = "easy"
    source_url = SOURCE_URL

    def scrape(self) -> List[ScrapedCompany]:
        r = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # li elements tagged js-company; filter out the nav "Companies" item
        items = [
            li for li in soup.find_all("li", class_=True)
            if "js-company" in li.get("class", [])
            and li.find("a", href=lambda h: h and "/companies/" in h and h != "/companies/")
        ]
        logger.info("IndexVentures: found %d company items", len(items))

        results = []
        for item in items:
            a = item.find("a", href=True)
            if not a:
                continue

            # Strip ticker symbol span before reading name
            ticker_el = a.find("span", class_="ticker-symbol")
            if ticker_el:
                ticker_el.decompose()
            name = a.get_text(strip=True)
            if not name:
                continue

            profile_url = BASE_URL + a["href"]

            sectors = json.loads(item.get("data-sectors") or "[]")
            regions = json.loads(item.get("data-regions") or "[]")
            industry = ", ".join(s.upper() for s in sectors) if sectors else None
            country = regions[0].replace("-", " ").title() if regions else None

            # Sector-based AI detection first; fall back to name heuristic
            is_ai = bool(_AI_SECTORS & set(sectors)) or self.detect_ai(name)

            results.append(ScrapedCompany(
                name=name,
                description=None,
                website_url=None,
                profile_url=profile_url,
                industry=industry,
                country=country,
                program="Index Ventures",
                source_url=SOURCE_URL,
                is_ai_startup=is_ai,
                confidence=0.85,
            ))

        logger.info("IndexVentures: parsed %d companies", len(results))
        return results
