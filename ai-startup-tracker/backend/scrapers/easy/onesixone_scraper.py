"""
161 Ventures Portfolio Scraper — Playwright (JS-rendered, single page).

Why Playwright (not requests):
  onesixone.ventures is a JS-rendered site (Webflow). The static HTML
  returns only a bare app shell; all portfolio cards are injected at runtime.
  A single page load is sufficient — no pagination or load-more needed.

Card structure (per company):
  Each card contains:
    - Company name (heading element)
    - Industry/sector (text label)
    - Short description
    - Company website (external link or plain domain text)
"""
import logging
import re
from typing import List

from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SOURCE_URL = "https://www.onesixone.ventures/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
DOMAIN_RE = re.compile(
    r"\b([\w-]+\.(?:com|ai|io|co|app|cloud|health|bio|finance|market|education|"
    r"ventures|tech|gov|network|family|security|media|digital|vc|fund))\b"
)


class OneSixOneScraper(BaseScraper):
    name = "onesixone"
    domain = "onesixone.ventures"
    difficulty = "easy"
    source_url = SOURCE_URL

    def scrape(self) -> List[ScrapedCompany]:
        html = self._render_page()
        return self._parse(html)

    def _render_page(self) -> str:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(SOURCE_URL, timeout=30000)
            page.wait_for_load_state("networkidle")
            html = page.content()
            browser.close()
        return html

    def _parse(self, html: str) -> List[ScrapedCompany]:
        soup = BeautifulSoup(html, "html.parser")

        # Webflow dynamic list items
        cards = soup.select("div.w-dyn-item")

        # Fallback: any div that contains an external link and a heading
        if not cards:
            cards = [
                div for div in soup.find_all("div")
                if div.find(["h1", "h2", "h3", "h4"])
                and div.find("a", href=re.compile(r"^https?://(?!.*onesixone)"))
            ]

        logger.info("161 Ventures: found %d candidate elements", len(cards))

        results = []
        seen: set[str] = set()

        for card in cards:
            # Name — first heading in the card
            heading = card.find(["h1", "h2", "h3", "h4", "h5"])
            if not heading:
                continue
            name = heading.get_text(strip=True)
            if not name or name in seen:
                continue

            # Skip nav/footer noise
            if len(name) > 80:
                continue

            # Website — prefer external href, fall back to domain pattern in text
            website: str | None = None
            ext_link = card.find("a", href=re.compile(r"^https?://(?!.*onesixone)"))
            if ext_link:
                website = ext_link["href"].rstrip("/")
            else:
                card_text = card.get_text(" ", strip=True)
                m = DOMAIN_RE.search(card_text)
                if m:
                    website = "https://" + m.group(1)

            # Description — longest <p> in the card that isn't the name
            paragraphs = [
                p.get_text(strip=True) for p in card.find_all("p")
                if p.get_text(strip=True) and p.get_text(strip=True) != name
            ]
            description = max(paragraphs, key=len) if paragraphs else None

            # Industry — short text block that's not the name or description
            industry: str | None = None
            for el in card.find_all(["span", "p", "div"]):
                txt = el.get_text(strip=True)
                if txt and txt != name and txt != description and len(txt) < 60:
                    # Likely an industry/sector label
                    industry = txt
                    break

            seen.add(name)
            is_ai = self.detect_ai(f"{name} {description or ''} {industry or ''}", keyword_only=True)

            results.append(ScrapedCompany(
                name=name,
                description=description,
                website_url=website,
                profile_url=SOURCE_URL,
                industry=industry,
                program="161 Ventures",
                source_url=SOURCE_URL,
                is_ai_startup=is_ai,
                confidence=0.9,
            ))

        logger.info("161 Ventures: parsed %d companies", len(results))
        return results
