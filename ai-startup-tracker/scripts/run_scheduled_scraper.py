#!/usr/bin/env python3
"""
In-process scheduler for re-running the agentic scraper on registered URLs.

Uses the `schedule` library (no external cron). Reads:
  data/scrape_schedule/registered_sites.yaml

Usage:
  python scripts/run_scheduled_scraper.py
  python scripts/run_scheduled_scraper.py --once
  python scripts/run_scheduled_scraper.py --config path/to/registered_sites.yaml
  python scripts/run_scheduled_scraper.py --once --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import schedule
import yaml
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.agentic import run_agentic_scrape  # noqa: E402
from backend.agentic.site_registry import load_registered_sites  # noqa: E402

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "data" / "scrape_schedule" / "registered_sites.yaml"
DEFAULT_REPORT_DIR = Path(__file__).resolve().parents[1] / "reports" / "agentic_runs"
DEFAULT_LOG_DIR = Path(__file__).resolve().parents[1] / "reports" / "scheduler_logs"


def _load_config(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _enabled_sites(config: Dict[str, Any]) -> List[Tuple[str, int]]:
    out: List[Tuple[str, int]] = []
    for item in config.get("sites") or []:
        if not isinstance(item, dict):
            continue
        if not item.get("enabled", True):
            continue
        url = (item.get("url") or "").strip()
        if not url:
            continue
        max_retries = int(item.get("max_retries", 2))
        out.append((url, max_retries))
    return out


def _write_run_report(report_dir: Path, report: Any) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = report_dir / f"agentic_run_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(mode="json"), f, indent=2, default=str)
    return out_path


def _all_sites(config: Dict[str, Any]) -> List[Tuple[str, int]]:
    """Merge YAML config sites + auto-parsed sites from CSV/MD."""
    yaml_sites = _enabled_sites(config)
    registry_sites = [(s["url"], 1) for s in load_registered_sites()]
    seen: set = set()
    combined: List[Tuple[str, int]] = []
    for url, retries in yaml_sites + registry_sites:
        normalized = url.rstrip("/")
        if normalized not in seen:
            seen.add(normalized)
            combined.append((url, retries))
    return combined


def run_registered_scrapes(
    config: Dict[str, Any],
    *,
    save_to_db: bool,
    report_dir: Path,
    logger: logging.Logger,
) -> int:
    """Run all enabled sites; return number of failures."""
    sites = _all_sites(config)
    if not sites:
        logger.warning("No enabled sites in config — nothing to do.")
        return 0

    failures = 0
    for url, max_retries in sites:
        logger.info("Scraping %s", url)
        try:
            report = run_agentic_scrape(
                url=url,
                save_to_db=save_to_db,
                max_retries=max_retries,
            )
            path = _write_run_report(report_dir, report)
            logger.info(
                "Done %s | validation=%s records=%s | report=%s",
                url,
                report.final_validation.is_good,
                report.total_records_after_clean,
                path,
            )
        except Exception as e:
            failures += 1
            logger.exception("Failed %s: %s", url, e)
    return failures


def _register_schedule(sched_block: Dict[str, Any], job) -> None:
    mode = (sched_block.get("mode") or "daily").strip().lower()
    if mode == "interval":
        hours = float(sched_block.get("interval_hours", 24))
        if hours < 1:
            hours = 1.0
        schedule.every(int(hours)).hours.do(job)
    else:
        at = (sched_block.get("time") or "09:00").strip()
        schedule.every().day.at(at).do(job)


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Scheduled agentic scraper (schedule library)")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to registered_sites.yaml",
    )
    parser.add_argument("--once", action="store_true", help="Run all sites once and exit")
    parser.add_argument(
        "--run-on-start",
        action="store_true",
        help="When staying in the scheduler loop, run one batch immediately before waiting",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write to DB")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("scheduled_scraper")

    if not args.config.is_file():
        logger.error("Config not found: %s", args.config)
        sys.exit(1)

    config = _load_config(args.config)
    sched_cfg = config.get("schedule") or {}

    def job():
        log_path = args.log_dir / f"scheduler_{datetime.utcnow().strftime('%Y%m%d')}.log"
        args.log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        root = logging.getLogger()
        root.addHandler(fh)
        try:
            failures = run_registered_scrapes(
                config,
                save_to_db=not args.dry_run,
                report_dir=args.report_dir,
                logger=logger,
            )
            logger.info("Batch finished; failures=%s", failures)
        finally:
            root.removeHandler(fh)

    if args.once:
        failures = run_registered_scrapes(
            config,
            save_to_db=not args.dry_run,
            report_dir=args.report_dir,
            logger=logger,
        )
        sys.exit(1 if failures else 0)

    _register_schedule(sched_cfg, job)
    try:
        nxt = schedule.next_run()
    except Exception:
        nxt = None
    logger.info("Scheduler started (mode=%s). Next run: %s", sched_cfg.get("mode"), nxt)

    if args.run_on_start:
        logger.info("Running initial batch (--run-on-start)")
        job()

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
