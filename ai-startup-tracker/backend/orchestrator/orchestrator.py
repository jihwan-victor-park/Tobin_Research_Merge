"""
Orchestrator — unified entry point for the two-tier scraping system.

Routes scrape requests to easy or hard tier based on the registry,
handles auto-escalation on failure, and logs all runs.

Usage:
    from backend.orchestrator.orchestrator import Orchestrator
    orch = Orchestrator()
    result = orch.run("https://seedcamp.com/companies/")
    orch.run_all_due()  # daily batch
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from backend.db.connection import session_scope
from backend.db.models import SiteHealth
from backend.orchestrator.health import HealthMonitor
from backend.scrapers.base import ScrapeRunResult
from backend.scrapers.hard.engine import AgenticScraper
from backend.scrapers.registry import classify_difficulty, get_scraper
from backend.utils.domain import canonicalize_domain

logger = logging.getLogger(__name__)

DEFAULT_COOLDOWN_DAYS = 7


class Orchestrator:
    """Unified orchestrator for easy + hard tier scraping."""

    def __init__(self, cooldown_days: int = DEFAULT_COOLDOWN_DAYS):
        self.cooldown_days = cooldown_days
        self.health = HealthMonitor()

    def run(self, url: str, force: bool = False) -> ScrapeRunResult:
        """
        Scrape a single URL. Routes to easy or hard tier based on registry.

        Flow:
          1. Canonicalize domain
          2. Check cooldown (skip if scraped recently, unless force=True)
          3. Look up in registry
          4. If EASY: try easy scraper, escalate to hard on failure
          5. If HARD: run agentic engine
          6. Update site health
        """
        domain = canonicalize_domain(url)
        if not domain:
            domain = url  # fallback for non-URL inputs (e.g. parquet path)

        logger.info(f"Orchestrator: {url} (domain={domain})")

        # Check cooldown
        if not force and self._is_on_cooldown(domain):
            logger.info(f"Skipping {domain}: on cooldown")
            return ScrapeRunResult(
                scraper_name="orchestrator",
                domain=domain,
                status="skipped",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            )

        # Route to appropriate tier
        difficulty = classify_difficulty(domain)
        logger.info(f"Difficulty for {domain}: {difficulty}")

        if difficulty == "easy":
            result = self._run_easy(url, domain)
            # Auto-escalate on failure
            if not result.success:
                logger.warning(f"Easy scraper failed for {domain}: {result.error_message}. Escalating to hard tier.")
                hard_result = self._run_hard(url, domain)
                hard_result.error_message = f"Escalated from easy: {result.error_message}"
                self.health.update(domain, hard_result, escalated_from="easy")
                return hard_result
            else:
                self.health.update(domain, result)
                return result
        else:
            result = self._run_hard(url, domain)
            self.health.update(domain, result)
            return result

    def _run_easy(self, url: str, domain: str) -> ScrapeRunResult:
        """Run the registered easy scraper for this domain."""
        scraper = get_scraper(domain)
        if scraper is None:
            return ScrapeRunResult(
                scraper_name="none",
                domain=domain,
                status="error",
                error_message=f"No easy scraper registered for {domain}",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            )
        return scraper.run(save_to_db=True)

    def _run_hard(self, url: str, domain: str) -> ScrapeRunResult:
        """Run the agentic engine for this URL."""
        scraper = AgenticScraper(url=url, domain=domain)
        return scraper.run(save_to_db=True)

    def _is_on_cooldown(self, domain: str) -> bool:
        """Check if this domain was scraped recently."""
        with session_scope() as session:
            health = session.query(SiteHealth).filter(SiteHealth.domain == domain).first()
            if health is None:
                return False
            if health.last_success_at is None:
                return False
            cooldown_until = health.last_success_at + timedelta(days=self.cooldown_days)
            return datetime.now(timezone.utc) < cooldown_until

    def run_all_due(self) -> List[ScrapeRunResult]:
        """Run all sites that are due for scraping (past cooldown, not excluded)."""
        results = []
        now = datetime.now(timezone.utc)

        with session_scope() as session:
            due_sites = (
                session.query(SiteHealth)
                .filter(
                    SiteHealth.status.notin_(["excluded"]),
                    SiteHealth.next_scrape_at <= now,
                )
                .all()
            )
            # Materialize before closing session
            sites_to_run = [(s.domain, s.url, s.difficulty) for s in due_sites]

        logger.info(f"Found {len(sites_to_run)} sites due for scraping")

        for domain, url, difficulty in sites_to_run:
            if not url:
                logger.warning(f"No URL for {domain}, skipping")
                continue
            try:
                result = self.run(url, force=True)
                results.append(result)
            except Exception as e:
                logger.error(f"Orchestrator error for {domain}: {e}", exc_info=True)
                results.append(ScrapeRunResult(
                    scraper_name="orchestrator",
                    domain=domain,
                    status="error",
                    error_message=str(e),
                    started_at=now,
                    finished_at=datetime.now(timezone.utc),
                ))

        # Summary
        success_count = sum(1 for r in results if r.success)
        logger.info(f"Batch complete: {success_count}/{len(results)} succeeded")
        return results

    def run_retries(self, hours: int = 48) -> List[ScrapeRunResult]:
        """Retry sites that got zero results in the last N hours using the hard tier."""
        results = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        with session_scope() as session:
            zero_sites = (
                session.query(SiteHealth)
                .filter(
                    SiteHealth.status == "degraded",
                    SiteHealth.last_failure_at >= cutoff,
                )
                .all()
            )
            sites_to_retry = [(s.domain, s.url) for s in zero_sites]

        logger.info(f"Retrying {len(sites_to_retry)} zero-result sites via hard tier")

        for domain, url in sites_to_retry:
            if not url:
                continue
            result = self._run_hard(url, domain)
            self.health.update(domain, result)
            results.append(result)

        return results
