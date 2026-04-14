"""
MIT delta v Scraper — fetches the past teams page, cleans the HTML,
and uses Claude Haiku to extract structured company data by cohort year.

Ported from Alastair branch to BaseScraper class.

Why Claude for extraction:
  MIT delta v is a standard WordPress page with no consistent CSS class
  pattern. Claude reads the natural-language structure and extracts correctly.
  Cost ~$0.01 per run using Haiku.
"""

import json
import logging
import os
from typing import List

import anthropic
import requests
from bs4 import BeautifulSoup

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

URL = "https://entrepreneurship.mit.edu/accelerator/past-teams/"
MODEL = "claude-haiku-4-5-20251001"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

SYSTEM_PROMPT = (
    "You are a data extraction assistant. "
    "Extract all startup companies from this MIT delta v accelerator page. "
    "The page lists companies by year cohort. "
    "Return ONLY a valid JSON array where each object has: "
    "name (string), batch_year (integer), description (string or null if not present), "
    "website (string or null). "
    "No markdown fences, no preamble."
)


class MitDeltavScraper(BaseScraper):
    name = "mit_deltav"
    domain = "entrepreneurship.mit.edu"
    difficulty = "easy"
    source_url = URL

    def _fetch_and_clean(self) -> str:
        response = requests.get(URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "meta", "link"]):
            tag.decompose()
        return " ".join(soup.get_text(separator=" ", strip=True).split())

    def _extract_with_claude(self, cleaned_html: str) -> list[dict]:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=MODEL,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Extract companies from:\n\n{cleaned_html}"}],
        )

        raw = message.content[0].text
        logger.info(f"Claude tokens: {message.usage.input_tokens} in / {message.usage.output_tokens} out")

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        companies = json.loads(cleaned)
        if not isinstance(companies, list):
            raise ValueError(f"Expected JSON array, got {type(companies).__name__}")
        return companies

    def scrape(self) -> List[ScrapedCompany]:
        cleaned_html = self._fetch_and_clean()
        logger.info(f"Cleaned content: {len(cleaned_html):,} characters")

        raw_companies = self._extract_with_claude(cleaned_html)
        logger.info(f"Extracted {len(raw_companies)} companies via Claude")

        results = []
        for c in raw_companies:
            name = c.get("name")
            if not name:
                continue
            description = c.get("description")
            text_for_ai = " ".join(filter(None, [name, description]))

            results.append(ScrapedCompany(
                name=name,
                description=description,
                website_url=c.get("website"),
                batch=str(c["batch_year"]) if c.get("batch_year") else None,
                country="United States",
                city="Cambridge",
                is_ai_startup=self.detect_ai(text_for_ai),
                source_url=self.source_url,
            ))

        return results
