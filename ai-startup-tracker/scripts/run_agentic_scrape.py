#!/usr/bin/env python3
"""
Run agentic scraping with Tavily + Claude.

Usage:
  python scripts/run_agentic_scrape.py --url https://example.com/portfolio
  python scripts/run_agentic_scrape.py --url https://example.com/portfolio --dry-run
"""
import argparse
import json
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.agentic import run_agentic_scrape  # noqa: E402


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Agentic web scraper runner")
    parser.add_argument("--url", required=True, help="Target URL to scrape")
    parser.add_argument("--dry-run", action="store_true", help="Do not save to DB")
    parser.add_argument("--max-retries", type=int, default=2, help="Max retry attempts")
    parser.add_argument("--report-dir", default="reports/agentic_runs", help="Directory for JSON run reports")
    args = parser.parse_args()

    report = run_agentic_scrape(
        url=args.url,
        save_to_db=not args.dry_run,
        max_retries=args.max_retries,
    )

    os.makedirs(args.report_dir, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(args.report_dir, f"agentic_run_{timestamp}.json")
    with open(out_path, "w") as f:
        json.dump(report.model_dump(mode="json"), f, indent=2, default=str)

    print(f"Run ID: {report.run_id}")
    print(f"Input URL: {report.input_url}")
    print(f"Site domain: {report.site_domain}")
    print(f"Instruction loaded: {report.instruction_loaded} ({report.instruction_path or 'n/a'})")
    print(f"Instruction saved: {report.instruction_saved} ({report.instruction_saved_path or 'n/a'})")
    print(f"Final validation: {report.final_validation.is_good} ({report.final_validation.reason})")
    print(f"Records: {report.total_records_before_clean} -> {report.total_records_after_clean} (clean)")
    print(f"DB changes: new={report.db_new_companies}, updated={report.db_updated_companies}")
    print(f"Report: {out_path}")


if __name__ == "__main__":
    main()
