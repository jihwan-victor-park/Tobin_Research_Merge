#!/usr/bin/env python3
"""
Weekly Update Orchestrator
===========================
Runs the full pipeline: GitHub discovery → Crunchbase match → PitchBook match.
Produces a weekly summary report as JSON.

Usage:
    python scripts/run_weekly_update.py [--since-days 7]
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.db.connection import session_scope, init_db
from backend.db.models import Company, GithubSignal, FundingSignal

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("weekly_update")

# File paths from environment
CB_ORGS_PATH = os.getenv("CB_ORGANIZATIONS_PATH", "")
CB_CATS_PATH = os.getenv("CB_CATEGORIES_PATH", "")
PB_DEAL_PATH = os.getenv("PB_DEAL_PATH", "")
PB_RELATION_PATH = os.getenv("PB_RELATION_PATH", "")


def run_github_discovery(since_days: int) -> dict:
    """Run GitHub weekly discovery."""
    logger.info("=" * 60)
    logger.info("STEP 1: GitHub Discovery")
    logger.info("=" * 60)

    from scripts.github_weekly_discover import discover_repos, process_candidates, upsert_to_db

    candidates = discover_repos(since_days=since_days)
    records = process_candidates(candidates)
    stats = upsert_to_db(records)

    logger.info(f"GitHub: {stats}")
    return stats


def run_crunchbase_import() -> dict:
    """Run Crunchbase import if parquet files are configured."""
    logger.info("=" * 60)
    logger.info("STEP 2: Crunchbase Import")
    logger.info("=" * 60)

    if not CB_ORGS_PATH or not os.path.exists(CB_ORGS_PATH):
        logger.warning(f"Crunchbase organizations file not found: {CB_ORGS_PATH!r}. Skipping.")
        return {"skipped": True}

    from scripts.import_crunchbase import import_crunchbase

    cats_path = CB_CATS_PATH if CB_CATS_PATH and os.path.exists(CB_CATS_PATH) else None
    stats = import_crunchbase(CB_ORGS_PATH, cats_path)
    logger.info(f"Crunchbase: {stats}")
    return stats


def run_pitchbook_import() -> dict:
    """Run PitchBook import if parquet files are configured."""
    logger.info("=" * 60)
    logger.info("STEP 3: PitchBook Import")
    logger.info("=" * 60)

    if not PB_DEAL_PATH or not os.path.exists(PB_DEAL_PATH):
        logger.warning(f"PitchBook deal file not found: {PB_DEAL_PATH!r}. Skipping.")
        return {"skipped": True}

    from scripts.import_pitchbook import import_pitchbook

    rel_path = PB_RELATION_PATH if PB_RELATION_PATH and os.path.exists(PB_RELATION_PATH) else None
    stats = import_pitchbook(PB_DEAL_PATH, rel_path)
    logger.info(f"PitchBook: {stats}")
    return stats


def generate_summary_report() -> dict:
    """Generate weekly summary report from current DB state."""
    logger.info("=" * 60)
    logger.info("STEP 4: Generating Summary Report")
    logger.info("=" * 60)

    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "total_companies": 0,
        "tracked_startups": 0,
        "new_this_week": 0,
        "promoted_this_week": 0,
        "by_verification_status": {},
        "top_countries": [],
        "top_repos_by_stars": [],
    }

    with session_scope() as session:
        # Total companies
        report["total_companies"] = session.query(Company).count()

        # Tracked startups (ai_score >= 0.6 AND startup_score >= 0.6)
        report["tracked_startups"] = session.query(Company).filter(
            Company.ai_score >= 0.6,
            Company.startup_score >= 0.6,
        ).count()

        # New this week
        week_ago = datetime.utcnow() - timedelta(days=7)
        new_companies = session.query(Company).filter(
            Company.first_seen_at >= week_ago,
        ).all()
        report["new_this_week"] = len(new_companies)

        # Promoted this week (tracked + new)
        promoted = [c for c in new_companies
                    if (c.ai_score or 0) >= 0.6 and (c.startup_score or 0) >= 0.6]
        report["promoted_this_week"] = len(promoted)

        # By verification status
        from sqlalchemy import func
        status_counts = session.query(
            Company.verification_status, func.count(Company.id)
        ).group_by(Company.verification_status).all()
        report["by_verification_status"] = {
            str(s.value) if hasattr(s, 'value') else str(s): c
            for s, c in status_counts
        }

        # Top countries
        country_counts = session.query(
            Company.country, func.count(Company.id)
        ).filter(
            Company.country.isnot(None),
            Company.country != "",
        ).group_by(Company.country).order_by(func.count(Company.id).desc()).limit(10).all()
        report["top_countries"] = [
            {"country": c, "count": n} for c, n in country_counts
        ]

        # Top new repos by stars (this week)
        top_repos = session.query(GithubSignal).filter(
            GithubSignal.collected_at >= week_ago,
        ).order_by(GithubSignal.stars.desc()).limit(20).all()
        report["top_repos_by_stars"] = [
            {
                "repo": r.repo_full_name,
                "stars": r.stars,
                "owner": r.owner_login,
                "description": (r.description or "")[:200],
            }
            for r in top_repos
        ]

    return report


def main():
    parser = argparse.ArgumentParser(description="Run weekly AI startup tracker update")
    parser.add_argument("--since-days", type=int, default=7, help="Look back N days for GitHub (default: 7)")
    parser.add_argument("--init-db", action="store_true", help="Create DB tables before running")
    parser.add_argument("--report-dir", default="data", help="Directory to write report JSON")
    args = parser.parse_args()

    if args.init_db:
        init_db()

    all_stats = {}

    # Step 1: GitHub
    try:
        all_stats["github"] = run_github_discovery(args.since_days)
    except Exception as e:
        logger.error(f"GitHub discovery failed: {e}", exc_info=True)
        all_stats["github"] = {"error": str(e)}

    # Step 2: Crunchbase
    try:
        all_stats["crunchbase"] = run_crunchbase_import()
    except Exception as e:
        logger.error(f"Crunchbase import failed: {e}", exc_info=True)
        all_stats["crunchbase"] = {"error": str(e)}

    # Step 3: PitchBook
    try:
        all_stats["pitchbook"] = run_pitchbook_import()
    except Exception as e:
        logger.error(f"PitchBook import failed: {e}", exc_info=True)
        all_stats["pitchbook"] = {"error": str(e)}

    # Step 4: Report
    try:
        report = generate_summary_report()
        report["pipeline_stats"] = all_stats

        # Write report
        os.makedirs(args.report_dir, exist_ok=True)
        report_path = os.path.join(
            args.report_dir,
            f"weekly_report_{datetime.utcnow().strftime('%Y%m%d')}.json",
        )
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        logger.info(f"Report written to {report_path}")
    except Exception as e:
        logger.error(f"Report generation failed: {e}", exc_info=True)

    # Final summary
    logger.info("=" * 60)
    logger.info("WEEKLY UPDATE COMPLETE")
    logger.info("=" * 60)
    for step, stats in all_stats.items():
        logger.info(f"  {step}: {stats}")

    return all_stats


if __name__ == "__main__":
    main()
