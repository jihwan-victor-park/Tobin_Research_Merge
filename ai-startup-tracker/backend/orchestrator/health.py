"""
Health Monitor — tracks per-site scraping health and handles escalation rules.

Escalation rules:
  - Easy fails 2x consecutively -> auto-escalate to hard (handled by orchestrator)
  - Hard fails 3x consecutively -> exclude for 90 days
  - Zero results treated as failure
  - Sites past exclude_until get re-evaluated
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from backend.db.connection import session_scope
from backend.db.models import SiteHealth
from backend.scrapers.base import ScrapeRunResult

logger = logging.getLogger(__name__)

EXCLUDE_DAYS = 90
MAX_HARD_FAILURES = 3


class HealthMonitor:
    """Manages site health state based on scrape results."""

    def update(
        self,
        domain: str,
        result: ScrapeRunResult,
        escalated_from: Optional[str] = None,
    ):
        """Update site_health row after a scrape run."""
        now = datetime.now(timezone.utc)

        with session_scope() as session:
            health = session.query(SiteHealth).filter(SiteHealth.domain == domain).first()

            if health is None:
                health = SiteHealth(
                    domain=domain,
                    url=result.scraper_name,  # will be overwritten
                    difficulty="hard",
                    status="pending",
                    created_at=now,
                )
                session.add(health)

            health.total_runs = (health.total_runs or 0) + 1
            health.updated_at = now
            health.last_record_count = result.records_found

            if result.success:
                health.status = "healthy"
                health.consecutive_failures = 0
                health.last_success_at = now
                health.total_successes = (health.total_successes or 0) + 1
                health.next_scrape_at = now + timedelta(days=7)
                health.last_error = None
            else:
                health.consecutive_failures = (health.consecutive_failures or 0) + 1
                health.last_failure_at = now
                health.last_error = result.error_message

                if result.status == "zero_result":
                    health.status = "degraded"
                    health.next_scrape_at = now + timedelta(hours=48)
                else:
                    health.status = "broken"

                # Check if should exclude
                if health.consecutive_failures >= MAX_HARD_FAILURES:
                    health.status = "excluded"
                    health.exclude_until = now + timedelta(days=EXCLUDE_DAYS)
                    health.exclude_reason = (
                        f"Failed {health.consecutive_failures}x consecutively. "
                        f"Last error: {result.error_message}"
                    )
                    health.next_scrape_at = health.exclude_until
                    logger.warning(
                        f"Excluded {domain} for {EXCLUDE_DAYS} days "
                        f"(failures={health.consecutive_failures})"
                    )

    def get_due_sites(self) -> List[dict]:
        """Return sites that are due for scraping (past next_scrape_at, not excluded)."""
        now = datetime.now(timezone.utc)
        with session_scope() as session:
            sites = (
                session.query(SiteHealth)
                .filter(
                    SiteHealth.status.notin_(["excluded"]),
                    SiteHealth.next_scrape_at <= now,
                )
                .all()
            )
            return [
                {"domain": s.domain, "url": s.url, "difficulty": s.difficulty}
                for s in sites
            ]

    def get_sites_due_for_revisit(self) -> List[dict]:
        """Return excluded sites whose exclude_until has passed (3-month revisit)."""
        now = datetime.now(timezone.utc)
        with session_scope() as session:
            sites = (
                session.query(SiteHealth)
                .filter(
                    SiteHealth.status == "excluded",
                    SiteHealth.exclude_until <= now,
                )
                .all()
            )
            return [
                {"domain": s.domain, "url": s.url, "difficulty": s.difficulty}
                for s in sites
            ]

    def reactivate_revisit_sites(self):
        """Re-enable excluded sites that are past their revisit date."""
        now = datetime.now(timezone.utc)
        with session_scope() as session:
            sites = (
                session.query(SiteHealth)
                .filter(
                    SiteHealth.status == "excluded",
                    SiteHealth.exclude_until <= now,
                )
                .all()
            )
            for site in sites:
                site.status = "pending"
                site.difficulty = "hard"  # try with hard tier first
                site.exclude_until = None
                site.exclude_reason = None
                site.consecutive_failures = 0
                site.next_scrape_at = now
                logger.info(f"Reactivated {site.domain} for revisit")

    def register_site(
        self,
        domain: str,
        url: str,
        difficulty: str = "hard",
        scraper_name: Optional[str] = None,
    ):
        """Register a new site for scraping."""
        now = datetime.now(timezone.utc)
        with session_scope() as session:
            existing = session.query(SiteHealth).filter(SiteHealth.domain == domain).first()
            if existing:
                logger.info(f"Site {domain} already registered")
                return
            health = SiteHealth(
                domain=domain,
                url=url,
                difficulty=difficulty,
                scraper_name=scraper_name,
                status="pending",
                next_scrape_at=now,
                created_at=now,
            )
            session.add(health)
            logger.info(f"Registered new site: {domain} ({difficulty})")

    def get_health_summary(self) -> dict:
        """Return summary stats for the dashboard."""
        with session_scope() as session:
            all_sites = session.query(SiteHealth).all()
            return {
                "total": len(all_sites),
                "healthy": sum(1 for s in all_sites if s.status == "healthy"),
                "degraded": sum(1 for s in all_sites if s.status == "degraded"),
                "broken": sum(1 for s in all_sites if s.status == "broken"),
                "excluded": sum(1 for s in all_sites if s.status == "excluded"),
                "pending": sum(1 for s in all_sites if s.status == "pending"),
                "easy": sum(1 for s in all_sites if s.difficulty == "easy"),
                "hard": sum(1 for s in all_sites if s.difficulty == "hard"),
            }
