"""
Single daily entry point for the local pipeline. Runs in this order:

  1. Reactivate any excluded sites whose 90-day timer has elapsed.
  2. Orchestrator.run_all_due() — scrape every site past its cooldown.
  3. Retry zero-result sites from the last 48 hours.
  4. (Mondays only) GitHub weekly discovery.
  5. LLM classifier batch on un-classified GitHub repos.
  6. (Mondays only) Scout 5 new US sites.

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


def main() -> None:
    today = datetime.now()
    is_monday = today.weekday() == 0
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

    # 4. Weekly GitHub discovery (Mondays only).
    if is_monday:
        _run_subprocess("github_weekly", [sys.executable, "scripts/github_weekly_discover.py", "--since-days", "7"])

    # 5. LLM classifier batch — keeps daily classification queue from piling up.
    _run_subprocess("llm_classify", [sys.executable, "scripts/run_llm_classify.py", "--batch-limit", "200"])

    # 6. Scout 5 new US sites once a week.
    if is_monday:
        _run_subprocess("scout", [sys.executable, "scripts/run_scout.py", "--country", "US", "--limit", "5"])

    logger.info("=== Daily run done ===")


if __name__ == "__main__":
    main()
