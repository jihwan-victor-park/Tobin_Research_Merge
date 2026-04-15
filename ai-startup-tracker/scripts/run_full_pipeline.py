#!/usr/bin/env python3
"""
Weekly Full Pipeline
====================
Runs the complete data update cycle in order:

  1. Easy scrapers  — all 17 registered scrapers; failures escalate to agentic engine
  2. GitHub discovery — finds new AI repos from the past 7 days (skipped if no GITHUB_TOKEN)
  3. LLM classification — classifies GitHub snapshots with ai_score=NULL
                          (uses GROQ → ANTHROPIC fallback; skipped if neither key present)
  4. Summary report — printed to stdout + saved to logs/pipeline_YYYY-MM-DD.log

Usage:
    python scripts/run_full_pipeline.py              # full run, save to DB
    python scripts/run_full_pipeline.py --dry-run    # no DB writes, no file saves
    python scripts/run_full_pipeline.py --skip-github
    python scripts/run_full_pipeline.py --skip-llm
    python scripts/run_full_pipeline.py --since-days 14

Cron (add to crontab -e):
    0 8 * * 1  cd /path/to/ai-startup-tracker && .venv/bin/python scripts/run_full_pipeline.py >> logs/weekly.log 2>&1
"""
import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pipeline")

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = SCRIPT_DIR.parent / "logs"


# ── Step 1: Easy scrapers ──────────────────────────────────────────────────

def run_easy_scrapers(dry_run: bool) -> dict:
    logger.info("=" * 60)
    logger.info("STEP 1: Easy Scrapers")
    logger.info("=" * 60)

    from backend.scrapers.registry import SCRAPER_REGISTRY
    from backend.agentic import run_agentic_scrape

    stats = {
        "total": len(SCRAPER_REGISTRY),
        "success": 0,
        "failed": 0,
        "escalated": 0,
        "escalation_details": [],
    }

    for domain, entry in SCRAPER_REGISTRY.items():
        scraper = entry.cls()
        try:
            result = scraper.run(save_to_db=not dry_run)
            if result.status == "success":
                stats["success"] += 1
                logger.info(f"  ✓ {domain:45s} found={result.records_found:4d} new={result.records_new:4d}")
            else:
                stats["failed"] += 1
                logger.warning(f"  ✗ {domain:45s} status={result.status} error={result.error_message}")

                # Escalate to agentic engine
                logger.info(f"    → Escalating {domain} to agentic engine...")
                try:
                    agentic_report = run_agentic_scrape(
                        url=scraper.source_url,
                        save_to_db=not dry_run,
                        max_retries=2,
                    )
                    escalation_ok = agentic_report.final_validation.is_good if agentic_report else False
                    stats["escalated"] += 1
                    stats["escalation_details"].append({
                        "domain": domain,
                        "scraper_status": result.status,
                        "agentic_ok": escalation_ok,
                        "agentic_records": agentic_report.total_records_after_clean if agentic_report else 0,
                    })
                    logger.info(f"    → Agentic result: ok={escalation_ok}")
                except Exception as e:
                    logger.error(f"    → Agentic escalation failed for {domain}: {e}")
                    stats["escalation_details"].append({
                        "domain": domain,
                        "scraper_status": result.status,
                        "agentic_ok": False,
                        "error": str(e),
                    })

        except Exception as e:
            stats["failed"] += 1
            logger.error(f"  ✗ {domain}: unhandled exception: {e}", exc_info=True)

    logger.info(f"Easy scrapers: {stats['success']}/{stats['total']} success, "
                f"{stats['failed']} failed, {stats['escalated']} escalated to agentic")
    return stats


# ── Step 2: GitHub discovery ───────────────────────────────────────────────

def run_github_discovery(since_days: int, dry_run: bool) -> dict:
    logger.info("=" * 60)
    logger.info("STEP 2: GitHub Discovery")
    logger.info("=" * 60)

    github_token = os.getenv("GITHUB_TOKEN", "")
    if not github_token:
        logger.warning("GITHUB_TOKEN not set — skipping GitHub discovery.")
        logger.warning("  Add GITHUB_TOKEN to .env for 5,000 req/hour (vs 60 unauthenticated).")
        return {"skipped": True, "reason": "missing GITHUB_TOKEN"}

    cmd = [sys.executable, str(SCRIPT_DIR / "github_weekly_discover.py"), f"--since-days={since_days}"]
    if dry_run:
        logger.info("  --dry-run: skipping GitHub discovery subprocess")
        return {"skipped": True, "reason": "dry-run"}

    logger.info(f"  Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            logger.info("  GitHub discovery completed successfully")
            return {"skipped": False, "returncode": 0}
        else:
            logger.error(f"  GitHub discovery failed (exit {result.returncode})")
            logger.error(result.stderr[-1000:] if result.stderr else "(no stderr)")
            return {"skipped": False, "returncode": result.returncode, "error": result.stderr[-500:]}
    except subprocess.TimeoutExpired:
        logger.error("  GitHub discovery timed out after 10 minutes")
        return {"skipped": False, "error": "timeout"}
    except Exception as e:
        logger.error(f"  GitHub discovery failed: {e}")
        return {"skipped": False, "error": str(e)}


# ── Step 3: LLM classification ─────────────────────────────────────────────

def run_llm_classification(dry_run: bool) -> dict:
    logger.info("=" * 60)
    logger.info("STEP 3: LLM Classification")
    logger.info("=" * 60)

    groq_key = os.getenv("GROQ_API_KEY", "")
    together_key = os.getenv("TOGETHER_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

    # Pick backend — prefer whatever is already configured, fall back in order
    configured_backend = os.getenv("LLM_BACKEND", "together").lower()

    backend_key_map = {
        "groq": groq_key,
        "together": together_key,
        "anthropic": anthropic_key,
        "ollama": "local",  # Ollama is local, no key needed
    }

    # Use configured backend if it has a key, else try fallback order
    chosen_backend = None
    if configured_backend in backend_key_map and backend_key_map[configured_backend]:
        chosen_backend = configured_backend
    else:
        for fallback in ["together", "groq", "anthropic", "ollama"]:
            if backend_key_map.get(fallback):
                chosen_backend = fallback
                logger.info(f"  Configured backend '{configured_backend}' has no key — "
                            f"falling back to '{chosen_backend}'")
                break

    if chosen_backend is None:
        logger.warning("  No LLM API key configured (GROQ_API_KEY, TOGETHER_API_KEY, ANTHROPIC_API_KEY).")
        logger.warning("  Skipping LLM classification. Add a key to .env to enable.")
        return {"skipped": True, "reason": "no LLM API key configured"}

    logger.info(f"  Using LLM backend: {chosen_backend}")

    # Override LLM_BACKEND env for the subprocess
    env = os.environ.copy()
    env["LLM_BACKEND"] = chosen_backend

    cmd = [sys.executable, str(SCRIPT_DIR / "run_llm_classify.py")]
    if dry_run:
        cmd.append("--dry-run")

    logger.info(f"  Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=False, text=True, timeout=3600, env=env)
        if result.returncode == 0:
            return {"skipped": False, "backend": chosen_backend, "returncode": 0}
        else:
            return {"skipped": False, "backend": chosen_backend, "returncode": result.returncode}
    except subprocess.TimeoutExpired:
        logger.error("  LLM classification timed out after 1 hour")
        return {"skipped": False, "error": "timeout"}
    except Exception as e:
        logger.error(f"  LLM classification failed: {e}")
        return {"skipped": False, "error": str(e)}


# ── Step 4: Summary report ─────────────────────────────────────────────────

def generate_report(all_stats: dict, started_at: datetime) -> str:
    from backend.db.connection import session_scope
    from backend.db.models import Company

    finished_at = datetime.now(timezone.utc)
    duration = (finished_at - started_at).total_seconds()

    with session_scope() as session:
        total_companies = session.query(Company).count()
        ai_flagged = session.query(Company).filter(Company.ai_score >= 0.6).count()

    scraper_stats = all_stats.get("scrapers", {})
    github_stats = all_stats.get("github", {})
    llm_stats = all_stats.get("llm", {})

    lines = [
        "",
        "=" * 60,
        f"WEEKLY PIPELINE REPORT — {started_at.strftime('%Y-%m-%d')}",
        "=" * 60,
        f"Duration:              {duration:.0f}s",
        f"Total companies in DB: {total_companies:,}",
        f"AI-flagged (≥0.6):     {ai_flagged:,}",
        "",
        "── Easy Scrapers ──",
        f"  Total registered:    {scraper_stats.get('total', '?')}",
        f"  Succeeded:           {scraper_stats.get('success', '?')}",
        f"  Failed:              {scraper_stats.get('failed', '?')}",
        f"  Escalated to agentic:{scraper_stats.get('escalated', '?')}",
    ]

    for esc in scraper_stats.get("escalation_details", []):
        ok = esc.get("agentic_ok", False)
        records = esc.get("agentic_records", 0)
        lines.append(f"    {esc['domain']:40s} agentic={'ok' if ok else 'FAIL'} records={records}")

    lines += [
        "",
        "── GitHub Discovery ──",
    ]
    if github_stats.get("skipped"):
        lines.append(f"  SKIPPED: {github_stats.get('reason', '')}")
    else:
        rc = github_stats.get("returncode", "?")
        lines.append(f"  Status: {'success' if rc == 0 else f'FAILED (exit {rc})'}")

    lines += [
        "",
        "── LLM Classification ──",
    ]
    if llm_stats.get("skipped"):
        lines.append(f"  SKIPPED: {llm_stats.get('reason', '')}")
    else:
        backend = llm_stats.get("backend", "?")
        rc = llm_stats.get("returncode", "?")
        lines.append(f"  Backend: {backend}")
        lines.append(f"  Status: {'success' if rc == 0 else f'FAILED (exit {rc})'}")

    lines += [
        "=" * 60,
        "",
        "To run again:  python scripts/run_full_pipeline.py",
        "Cron (weekly): 0 8 * * 1  cd <project_dir> && .venv/bin/python scripts/run_full_pipeline.py >> logs/weekly.log 2>&1",
        "",
    ]

    return "\n".join(lines)


def save_report(report: str, dry_run: bool) -> None:
    if dry_run:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"pipeline_{datetime.now().strftime('%Y-%m-%d')}.log"
    with open(log_path, "a") as f:
        f.write(report)
    logger.info(f"Report saved to {log_path}")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run the full weekly data pipeline")
    parser.add_argument("--dry-run", action="store_true", help="No DB writes, no file saves")
    parser.add_argument("--skip-github", action="store_true", help="Skip GitHub discovery step")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM classification step")
    parser.add_argument("--since-days", type=int, default=7, help="GitHub look-back window in days")
    args = parser.parse_args()

    if args.dry_run:
        logger.info("DRY-RUN MODE — no database writes, no file saves")

    started_at = datetime.now(timezone.utc)
    all_stats = {}

    # Step 1
    try:
        all_stats["scrapers"] = run_easy_scrapers(dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"Easy scrapers step failed: {e}", exc_info=True)
        all_stats["scrapers"] = {"error": str(e)}

    # Step 2
    if args.skip_github:
        logger.info("STEP 2: GitHub Discovery — SKIPPED (--skip-github)")
        all_stats["github"] = {"skipped": True, "reason": "--skip-github flag"}
    else:
        try:
            all_stats["github"] = run_github_discovery(since_days=args.since_days, dry_run=args.dry_run)
        except Exception as e:
            logger.error(f"GitHub discovery step failed: {e}", exc_info=True)
            all_stats["github"] = {"error": str(e)}

    # Step 3
    if args.skip_llm:
        logger.info("STEP 3: LLM Classification — SKIPPED (--skip-llm)")
        all_stats["llm"] = {"skipped": True, "reason": "--skip-llm flag"}
    else:
        try:
            all_stats["llm"] = run_llm_classification(dry_run=args.dry_run)
        except Exception as e:
            logger.error(f"LLM classification step failed: {e}", exc_info=True)
            all_stats["llm"] = {"error": str(e)}

    # Step 4
    report = generate_report(all_stats, started_at)
    print(report)
    save_report(report, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
