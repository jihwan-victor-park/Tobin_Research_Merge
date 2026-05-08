"""
Balderton Capital Scraper — Playwright (headless Chromium), load-more pagination.

Why Playwright (not requests):
  balderton.com serves only 30 companies in the initial HTML; the remaining
  ~170+ companies load via FacetWP AJAX on "Load more" button clicks.
  FacetWP's REST endpoint requires WordPress page context and cannot be called
  directly, so we drive a headless browser to click through all batches.

Card structure (per company):
  div.card.type-company
    h3                    → company name
    div.text-powder p     → description
    span.label-M          → city/country
    span.label-m.fw-medium → investment stage/year
    a.mask[href]          → external company website
"""
import logging
import re
import time
from typing import List

from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SOURCE_URL = "https://www.balderton.com/companies/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
SECTOR_RE = re.compile(r"\bsector-([a-z0-9-]+)\b")


class BaldertonScraper(BaseScraper):
    name = "balderton"
    domain = "balderton.com"
    difficulty = "easy"
    source_url = SOURCE_URL

    def scrape(self) -> List[ScrapedCompany]:
        html = self._render_all_companies()
        return self._parse_html(html)

    def _render_all_companies(self) -> str:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(SOURCE_URL, timeout=30000)
            page.wait_for_load_state("networkidle")

            clicks = 0
            no_change_streak = 0
            while clicks < 30:
                count_before = page.locator("div.card.type-company").count()
                btn = page.locator("button.facetwp-load-more")
                if btn.count() == 0:
                    break
                # Button may briefly be hidden during animation — wait up to 3s
                try:
                    btn.wait_for(state="visible", timeout=3000)
                except Exception:
                    break
                btn.scroll_into_view_if_needed()
                page.evaluate("window.scrollBy(0, 200)")
                time.sleep(0.5)
                try:
                    btn.click(force=True)
                except Exception:
                    # Button disappeared mid-click (all pages loaded)
                    break
                page.wait_for_load_state("networkidle")
                time.sleep(1.5)
                clicks += 1
                count_after = page.locator("div.card.type-company").count()
                logger.info("Balderton: click %d → %d companies", clicks, count_after)
                if count_after == count_before:
                    no_change_streak += 1
                    if no_change_streak >= 3:
                        break
                else:
                    no_change_streak = 0

            html = page.content()
            browser.close()
            return html

    def _parse_html(self, html: str) -> List[ScrapedCompany]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.card")
        logger.info("Balderton: found %d card elements in rendered HTML", len(cards))

        results = []
        for card in cards:
            cls = " ".join(card.get("class", []))
            if "type-company" not in cls:
                continue

            name_el = card.select_one("h3")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name:
                continue

            website_el = card.select_one("a.mask[href]")
            website = website_el["href"] if website_el else None
            if website and not website.startswith("http"):
                website = None

            desc_el = card.select_one("div.text-powder p")
            description = desc_el.get_text(strip=True) if desc_el else None

            loc_el = card.select_one("span.label-M")
            city_country = loc_el.get_text(strip=True) if loc_el else None
            city, country = self._parse_location(city_country)

            sector_match = SECTOR_RE.search(cls)
            sector = sector_match.group(1).replace("-", " ").title() if sector_match else None

            stage_el = card.select_one("span.label-m.fw-medium")
            batch = stage_el.get_text(strip=True) if stage_el else None

            is_ai = self.detect_ai(f"{name} {description or ''} {sector or ''}")

            results.append(ScrapedCompany(
                name=name,
                description=description,
                website_url=website,
                profile_url=SOURCE_URL,
                industry=sector,
                country=country,
                city=city,
                batch=batch,
                program="Balderton Capital",
                source_url=SOURCE_URL,
                is_ai_startup=is_ai,
                confidence=0.9,
            ))

        logger.info("Balderton: parsed %d companies", len(results))
        return results

    @staticmethod
    def _parse_location(text: str | None) -> tuple[str | None, str | None]:
        if not text:
            return None, None
        parts = [p.strip() for p in text.split(",")]
        if len(parts) >= 2:
            return parts[0], parts[-1]
        return None, parts[0] if parts else None
