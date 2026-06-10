"""
Single daily entry point for the local pipeline. Runs in this order:

  1. Reactivate any excluded sites whose 90-day timer has elapsed.
  2. Orchestrator.run_all_due() — scrape every site past its cooldown.
  3. Retry zero-result sites from the last 48 hours.
  4. Sync site categories from YAML files (idempotent backfill).
  5. (Mondays only) GitHub weekly discovery.
  6. LLM classifier batch on un-classified repos/companies.
  7. International scout rotation — 2-3 countries per day, full rotation weekly.
  8. (Sundays only) International incubator scrape — explicit KR/IL/CN/SG/IL scrapers.
  9. (Sundays only) Dedup report — log domain duplicates to catch cross-source merges.

Logs everything to logs/daily_YYYYMMDD.log so launchd output stays small and
the operator can scroll back to a specific day.

Designed to be run by launchd (see scripts/launchd/) — no cloud dependency.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / f"daily_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("daily")


def _run_subprocess(label: str, args: list[str]) -> int:
    """Run a script as a subprocess so its failure can't kill the whole job."""
    logger.info(f"--- {label}: {' '.join(args)}")
    try:
        result = subprocess.run(
            args, cwd=PROJECT_ROOT, check=False,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            timeout=60 * 60,  # 1 hour cap per step
        )
        if result.stdout:
            for line in result.stdout.rstrip().splitlines():
                logger.info(f"[{label}] {line}")
        logger.info(f"--- {label} exit={result.returncode}")
        return result.returncode
    except Exception as e:
        logger.exception(f"--- {label} crashed: {e}")
        return -1


# Scout rotation: 2-3 countries per weekday so every country is covered weekly.
# 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
_SCOUT_ROTATION: dict[int, list[str]] = {
    0: ["US", "UK"],
    1: ["DE", "FR", "NL"],
    2: ["IN", "SG", "KR"],
    3: ["CA", "AU", "BR"],
    4: ["IL", "SE", "AE"],
    5: ["JP", "MX", "ID"],
    6: ["NG", "ZA"],
}


def main() -> None:
    today = datetime.now()
    weekday = today.weekday()
    is_monday = weekday == 0
    is_sunday = weekday == 6
    logger.info(f"=== Daily run start ({today.isoformat()}) ===")

    # 1+2+3: orchestrator inline so we share the same DB session pool.
    try:
        from backend.orchestrator.orchestrator import Orchestrator
        orch = Orchestrator()
        orch.health.reactivate_revisit_sites()
        results = orch.run_all_due()
        success = sum(1 for r in results if r.success)
        logger.info(f"orchestrator: {success}/{len(results)} succeeded")
        retries = orch.run_retries(hours=48)
        logger.info(f"orchestrator retries: {len(retries)} run")
    except Exception as e:
        logger.exception(f"orchestrator crashed: {e}")

    # 4. Sync site categories from YAML files — idempotent, fast, catches new YAMLs.
    _run_subprocess("sync_categories", [sys.executable, "scripts/sync_site_categories.py"])

    # 5. Weekly GitHub discovery (Mondays only).
    if is_monday:
        _run_subprocess("github_weekly", [sys.executable, "scripts/github_weekly_discover.py", "--since-days", "7"])

    # 6. LLM classifier batch — keeps daily classification queue from piling up.
    _run_subprocess("llm_classify", [sys.executable, "scripts/run_llm_classify.py", "--batch-limit", "200"])

    # 7. International scout — rotate 2-3 countries per day so all 20 countries
    #    get scouted once a week without hammering Tavily in a single run.
    scout_countries = _SCOUT_ROTATION.get(weekday, [])
    for country in scout_countries:
        _run_subprocess(
            f"scout_{country}",
            [sys.executable, "scripts/run_scout.py", "--country", country, "--limit", "15"],
        )

    # 8. Weekly international incubator scrape (Sundays) — explicit KR/IL/CN/SG scrapers.
    if is_sunday:
        _run_subprocess("international_incubators", [sys.executable, "scripts/scrape_international_incubators.py"])

    # 9. Weekly dedup report (Sundays) — surfaces domain duplicates for review.
    if is_sunday:
        _run_subprocess("dedup_report", [sys.executable, "scripts/run_dedup.py", "--limit", "30"])

    logger.info("=== Daily run done ===")


if __name__ == "__main__":
    main()
