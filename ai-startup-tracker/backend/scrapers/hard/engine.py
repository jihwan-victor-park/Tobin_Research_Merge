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
from backend.scrapers.base import BaseScraper, ScrapeRunResult, _log_scrape_run

logger = logging.getLogger(__name__)


def _audit_agentic_run(
    domain: str,
    source_url: str,
    result: ScrapeRunResult,
    save_to_db: bool,
) -> None:
    """Mirror easy-tier scrapers: write scrape_runs for Pipeline Health → Recent runs."""
    if not save_to_db or not result.started_at or not result.finished_at:
        return
    try:
        duration = (result.finished_at - result.started_at).total_seconds()
        _log_scrape_run(
            domain=domain,
            url=source_url or "",
            difficulty="hard",
            scraper_name=result.scraper_name,
            status=result.status,
            error_message=result.error_message,
            records_found=result.records_found,
            records_new=result.records_new,
            records_updated=result.records_updated,
            duration_seconds=duration,
            escalated_from=None,
            started_at=result.started_at,
            finished_at=result.finished_at,
        )
    except Exception as e:
        logger.warning("scrape_runs audit log failed for %s: %s", domain, e)


class AgenticScraper(BaseScraper):
    """Hard-tier scraper using Claude tool-use agent with Tavily/Playwright."""

    name = "agentic_engine"
    difficulty = "hard"

    def __init__(self, url: str = "", domain: str = "", force: bool = False):
        self.source_url = url
        self.domain = domain
        self.force = force

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
                force=self.force,
            )

            status = "success" if report.final_validation.is_good else "zero_result"
            if report.total_records_after_clean == 0:
                status = "zero_result"

            finished_at = datetime.now(timezone.utc)
            result = ScrapeRunResult(
                scraper_name=self.name,
                domain=self.domain,
                status=status,
                records_found=report.total_records_after_clean,
                records_new=report.db_new_companies,
                records_updated=report.db_updated_companies,
                started_at=started_at,
                finished_at=finished_at,
            )
            _audit_agentic_run(self.domain, self.source_url, result, save_to_db)
            return result

        except Exception as e:
            logger.error(f"Agentic engine failed for {self.source_url}: {e}", exc_info=True)
            finished_at = datetime.now(timezone.utc)
            result = ScrapeRunResult(
                scraper_name=self.name,
                domain=self.domain,
                status="error",
                error_message=str(e),
                started_at=started_at,
                finished_at=finished_at,
            )
            _audit_agentic_run(self.domain, self.source_url, result, save_to_db)
            return result
