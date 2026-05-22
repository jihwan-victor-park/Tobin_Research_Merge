"""
Khosla Ventures Portfolio Scraper — BeautifulSoup, single page.

Why HTML (not API):
  khoslaventures.com serves 132 portfolio companies as server-rendered
  anchor tags with class "company-slide". Each slide contains an image
  with the company name in the alt attribute and the company website
  in the href.

Card structure (per company):
  a.company-slide[href]            → company website URL
    img[alt]                       → company name
    div.company-slide--info
      h3                           → company name (redundant with img alt)
      p                            → short description (sometimes present)
"""
import logging
from typing import List

import requests
from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SOURCE_URL = "https://www.khoslaventures.com/portfolio/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


class KhoslaVenturesScraper(BaseScraper):
    name = "khoslaventures"
    domain = "khoslaventures.com"
    difficulty = "easy"
    source_url = SOURCE_URL

    def scrape(self) -> List[ScrapedCompany]:
        r = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        slides = soup.find_all("a", class_="company-slide")
        logger.info("KhoslaVentures: found %d slides", len(slides))

        results = []
        seen = set()
        for slide in slides:
            img = slide.find("img")
            name = (img.get("alt") or "").strip() if img else ""
            if not name or name in seen:
                continue
            seen.add(name)

            href = slide.get("href", "").strip()
            website = href if href.startswith("http") else None

            info = slide.find("div", class_="company-slide--info")
            description = None
            if info:
                p = info.find("p")
                description = p.get_text(strip=True) if p else None

            is_ai = self.detect_ai(f"{name} {description or ''}", keyword_only=True)

            results.append(ScrapedCompany(
                name=name,
                description=description,
                website_url=website,
                profile_url=SOURCE_URL,
                program="Khosla Ventures",
                source_url=SOURCE_URL,
                is_ai_startup=is_ai,
                confidence=0.9,
            ))

        logger.info("KhoslaVentures: parsed %d companies", len(results))
        return results
