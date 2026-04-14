"""
Hard-tier scraper adapter — wraps the existing agentic engine as a BaseScraper.

The agentic engine (Tavily + Claude tool-use + Playwright) handles unknown/complex
sites. This adapter bridges it into the unified two-tier system.

The actual engine implementation stays in backend/agentic/engine.py —
this module just provides the BaseScraper interface.
"""
from __future__ import annotations

import logging
from typing import List

from backend.agentic.engine import run_agentic_scrape
from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper, ScrapeRunResult

logger = logging.getLogger(__name__)


class AgenticScraper(BaseScraper):
    """Hard-tier scraper using Claude tool-use agent with Tavily/Playwright."""

    name = "agentic_engine"
    difficulty = "hard"

    def __init__(self, url: str = "", domain: str = ""):
        self.source_url = url
        self.domain = domain

    def scrape(self) -> List[ScrapedCompany]:
        """Not used directly — run() is overridden to use run_agentic_scrape()."""
        raise NotImplementedError("Use run() instead for agentic scraper")

    def run(self, save_to_db: bool = True) -> ScrapeRunResult:
        """Run the agentic engine and return a unified ScrapeRunResult."""
        from datetime import datetime, timezone

        started_at = datetime.now(timezone.utc)

        try:
            report = run_agentic_scrape(
                url=self.source_url,
                save_to_db=save_to_db,
                max_retries=2,
                force=False,
            )

            status = "success" if report.final_validation.is_good else "zero_result"
            if report.total_records_after_clean == 0:
                status = "zero_result"

            return ScrapeRunResult(
                scraper_name=self.name,
                domain=self.domain,
                status=status,
                records_found=report.total_records_after_clean,
                records_new=report.db_new_companies,
                records_updated=report.db_updated_companies,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            logger.error(f"Agentic engine failed for {self.source_url}: {e}", exc_info=True)
            return ScrapeRunResult(
                scraper_name=self.name,
                domain=self.domain,
                status="error",
                error_message=str(e),
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )
