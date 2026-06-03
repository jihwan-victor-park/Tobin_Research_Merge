"""
Lightspeed Venture Partners Portfolio Scraper — BeautifulSoup, single page.

Why slug extraction (not API):
  lsvp.com serves 586 portfolio companies as anchor tags linking to
  /company/{slug}/ pages. Most company cards only show a founder photo
  and name — the company name is derivable from the URL slug. Featured
  "lead--block" cards include the company description.

Card structure:
  div.founder a[href="/company/{slug}/"]
    div.founder.lead--block (featured cards only)
      h3                       → founder name
      h4                       → "Title, CompanyName" (company name after last comma)
      p                        → company description
    (regular cards have no text content, only founder image)
"""
import logging
import re
from typing import List

import requests
from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SOURCE_URL = "https://lsvp.com/portfolio/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def _slug_to_name(slug: str) -> str:
    return " ".join(w.capitalize() for w in slug.replace("-", " ").split())


class LightspeedScraper(BaseScraper):
    name = "lightspeed"
    domain = "lsvp.com"
    difficulty = "easy"
    source_url = SOURCE_URL

    def scrape(self) -> List[ScrapedCompany]:
        r = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        company_links = soup.find_all("a", href=re.compile(r"lsvp\.com/company/"))
        logger.info("Lightspeed: found %d company links", len(company_links))

        # Build slug → (name, description) map
        seen: dict[str, tuple[str, str | None]] = {}
        for a in company_links:
            href = a["href"]
            slug = href.rstrip("/").split("/")[-1]
            if slug in seen:
                continue

            # Try to get company name and description from featured cards
            card = a.parent
            name = None
            description = None

            if card and "lead--block" in " ".join(card.get("class", [])):
                h4 = card.find("h4")
                if h4:
                    h4_text = h4.get_text(strip=True)
                    if "," in h4_text:
                        name = h4_text.split(",")[-1].strip()
                p = card.find("p")
                if p:
                    description = p.get_text(strip=True) or None

            if not name:
                name = _slug_to_name(slug)

            seen[slug] = (name, description)

        results = []
        for slug, (name, description) in seen.items():
            is_ai = self.detect_ai(f"{name} {description or ''}", keyword_only=True)
            results.append(ScrapedCompany(
                name=name,
                description=description,
                website_url=None,
                profile_url=f"https://lsvp.com/company/{slug}/",
                program="Lightspeed Venture Partners",
                source_url=SOURCE_URL,
                is_ai_startup=is_ai,
                confidence=0.9,
            ))

        logger.info("Lightspeed: parsed %d companies", len(results))
        return results
