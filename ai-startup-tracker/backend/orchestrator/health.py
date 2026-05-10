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
import os
import yaml
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import or_

from backend.db.connection import session_scope
from backend.db.models import SiteHealth
from backend.scrapers.base import ScrapeRunResult

_INSTR_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "scrape_instructions")


def _category_from_yaml(domain: str) -> Optional[str]:
    path = os.path.join(_INSTR_DIR, f"{domain}.yaml")
    try:
        with open(path) as f:
            d = yaml.safe_load(f)
        return d.get("category") if d else None
    except FileNotFoundError:
        return None
    except yaml.YAMLError:
        logger.warning("Malformed YAML for domain %s at %s", domain, path)
        return None

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
        *,
        seed_url: Optional[str] = None,
        difficulty: Optional[str] = None,
    ):
        """Update site_health row after a scrape run.

        seed_url: last URL scraped (so ad-hoc / random sites get a real portfolio URL on file).
        difficulty: registry tier ('easy' | 'hard'); defaults to 'hard' for new rows.
        """
        now = datetime.now(timezone.utc)
        tier = (difficulty or "hard").strip().lower()
        if tier not in ("easy", "hard"):
            tier = "hard"

        with session_scope() as session:
            health = session.query(SiteHealth).filter(SiteHealth.domain == domain).first()

            if health is None:
                health = SiteHealth(
                    domain=domain,
                    url=(seed_url or None),
                    difficulty=tier,
                    scraper_name=result.scraper_name,
                    status="pending",
                    worker_state="pending",
                    category=_category_from_yaml(domain),
                    created_at=now,
                )
                session.add(health)
            else:
                if seed_url:
                    health.url = seed_url
                health.difficulty = tier
                health.scraper_name = result.scraper_name or health.scraper_name

            health.total_runs = (health.total_runs or 0) + 1
            health.updated_at = now
            health.last_record_count = result.records_found

            if result.success:
                health.status = "healthy"
                health.worker_state = "working"
                health.consecutive_failures = 0
                health.last_success_at = now
                health.total_successes = (health.total_successes or 0) + 1
                health.next_scrape_at = now + timedelta(days=7)
                health.last_error = None
            else:
                health.worker_state = "pending"
                health.consecutive_failures = (health.consecutive_failures or 0) + 1
                health.last_failure_at = now
                health.last_error = result.error_message

                if result.status == "zero_result":
                    health.status = "degraded"
                    health.next_scrape_at = now + timedelta(hours=48)
                else:
                    health.status = "broken"
                    health.next_scrape_at = now + timedelta(days=1)

                # After two failures, ask the LLM for a one-line "why is this
                # site hard" diagnosis so the dashboard can show it. We only
                # diagnose once per failure-streak — the timestamp lets the
                # dashboard show staleness if needed.
                if health.consecutive_failures == 2:
                    try:
                        from backend.orchestrator.diagnose import diagnose_failure
                        reason = diagnose_failure(
                            domain=domain,
                            url=health.url or seed_url,
                            last_error=result.error_message,
                        )
                    except Exception as e:
                        logger.warning(f"diagnose_failure raised for {domain}: {e}")
                        reason = None
                    if reason:
                        health.pending_reason = reason
                        health.pending_reason_at = now

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
                    or_(
                        SiteHealth.next_scrape_at.is_(None),
                        SiteHealth.next_scrape_at <= now,
                    ),
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
                site.worker_state = "pending"
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
        category: Optional[str] = None,
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
                worker_state="pending",
                category=category or _category_from_yaml(domain),
                next_scrape_at=now,
                created_at=now,
            )
            session.add(health)
            logger.info(f"Registered new site: {domain} ({difficulty})")

    def seed_registry(self) -> int:
        """Ensure every registered easy scraper has a site_health row.

        Sites that have never run get a 'pending' row with their seed URL,
        so they show up in the dashboard immediately instead of only after
        the first scrape attempt. Returns the number of rows inserted.
        """
        from backend.scrapers.registry import SCRAPER_REGISTRY  # local import to avoid cycles

        now = datetime.now(timezone.utc)
        inserted = 0
        with session_scope() as session:
            existing_rows = {r.domain: r for r in session.query(SiteHealth).all()}
            for domain, entry in SCRAPER_REGISTRY.items():
                row = existing_rows.get(domain)
                if row is not None:
                    if not row.category:
                        row.category = entry.category
                    continue
                try:
                    seed_url = entry.cls().source_url
                except Exception:
                    seed_url = None
                session.add(SiteHealth(
                    domain=domain,
                    url=seed_url,
                    difficulty=entry.difficulty,
                    scraper_name=entry.cls.__name__,
                    status="pending",
                    worker_state="pending",
                    category=entry.category,
                    next_scrape_at=now,
                    created_at=now,
                ))
                inserted += 1
        if inserted:
            logger.info(f"Seeded {inserted} new registry sites into site_health")
        return inserted

    def get_health_summary(self) -> dict:
        """Return summary stats for the dashboard."""
        with session_scope() as session:
            all_sites = session.query(SiteHealth).all()
            return {
                "total": len(all_sites),
                "working": sum(1 for s in all_sites if s.worker_state == "working"),
                "pending": sum(1 for s in all_sites if s.worker_state == "pending"),
                "healthy": sum(1 for s in all_sites if s.status == "healthy"),
                "degraded": sum(1 for s in all_sites if s.status == "degraded"),
                "broken": sum(1 for s in all_sites if s.status == "broken"),
                "excluded": sum(1 for s in all_sites if s.status == "excluded"),
                "easy": sum(1 for s in all_sites if s.difficulty == "easy"),
                "hard": sum(1 for s in all_sites if s.difficulty == "hard"),
            }
