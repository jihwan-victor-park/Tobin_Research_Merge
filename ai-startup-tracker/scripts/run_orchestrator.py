#!/usr/bin/env python3
"""
Unified orchestrator CLI — single entry point for all scraping operations.

Usage:
  # Scrape a single URL (auto-detects easy/hard tier)
  python scripts/run_orchestrator.py --url https://seedcamp.com/companies/

  # Scrape a single URL, force (ignore cooldown)
  python scripts/run_orchestrator.py --url https://seedcamp.com/companies/ --force

  # Run all sites due for scraping
  python scripts/run_orchestrator.py --batch

  # Retry zero-result sites from last 48 hours
  python scripts/run_orchestrator.py --retry

  # Re-evaluate excluded sites past 3-month revisit
  python scripts/run_orchestrator.py --revisit

  # Register all easy scrapers as sites
  python scripts/run_orchestrator.py --register-easy

  # Run on a daily schedule
  python scripts/run_orchestrator.py --schedule
"""
import argparse
import logging
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db.connection import init_db
from backend.orchestrator.orchestrator import Orchestrator
from backend.orchestrator.health import HealthMonitor
from backend.scrapers.registry import SCRAPER_REGISTRY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def register_easy_scrapers():
    """Register all easy scrapers in the site_health table."""
    health = HealthMonitor()
    for domain, entry in SCRAPER_REGISTRY.items():
        scraper = entry.cls()
        health.register_site(
            domain=domain,
            url=scraper.source_url,
            difficulty=entry.difficulty,
            scraper_name=scraper.name,
        )
    logger.info(f"Registered {len(SCRAPER_REGISTRY)} scrapers")


def main():
    parser = argparse.ArgumentParser(description="AI Startup Tracker Orchestrator")
    parser.add_argument("--url", help="Scrape a single URL")
    parser.add_argument("--force", action="store_true", help="Ignore cooldown")
    parser.add_argument("--batch", action="store_true", help="Run all due sites")
    parser.add_argument("--retry", action="store_true", help="Retry zero-result sites")
    parser.add_argument("--revisit", action="store_true", help="Re-evaluate excluded sites")
    parser.add_argument("--register-easy", action="store_true", help="Register all easy scrapers")
    parser.add_argument("--schedule", action="store_true", help="Run on daily schedule")
    parser.add_argument("--cooldown", type=int, default=7, help="Cooldown days (default: 7)")
    args = parser.parse_args()

    # Initialize DB tables
    init_db()

    orch = Orchestrator(cooldown_days=args.cooldown)

    if args.register_easy:
        register_easy_scrapers()
        return

    if args.url:
        result = orch.run(args.url, force=args.force)
        logger.info(f"Result: {result}")
        return

    if args.batch:
        results = orch.run_all_due()
        success = sum(1 for r in results if r.success)
        logger.info(f"Batch: {success}/{len(results)} succeeded")
        return

    if args.retry:
        results = orch.run_retries(hours=48)
        logger.info(f"Retried {len(results)} sites")
        return

    if args.revisit:
        health = HealthMonitor()
        health.reactivate_revisit_sites()
        results = orch.run_all_due()
        logger.info(f"Revisited {len(results)} sites")
        return

    if args.schedule:
        import schedule

        logger.info("Starting daily scheduler...")
        register_easy_scrapers()

        def daily_job():
            logger.info("=== Daily scrape run ===")
            # 1. Reactivate revisit sites
            orch.health.reactivate_revisit_sites()
            # 2. Run all due sites
            results = orch.run_all_due()
            # 3. Retry zero-result sites
            retry_results = orch.run_retries(hours=48)
            success = sum(1 for r in results if r.success)
            logger.info(f"Daily: {success}/{len(results)} succeeded, {len(retry_results)} retries")

        schedule.every().day.at("09:00").do(daily_job)
        logger.info("Scheduled daily at 09:00. Press Ctrl+C to stop.")

        while True:
            schedule.run_pending()
            time.sleep(60)

    parser.print_help()


if __name__ == "__main__":
    main()
