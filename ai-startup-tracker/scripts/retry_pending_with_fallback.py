#!/usr/bin/env python3
"""
Retry every site in `site_health` whose previous attempt died because the
Anthropic API ran out of credit, now that the agentic engine has an
automatic Together fallback. Optionally also retries the never-run sites.

Usage:
  python scripts/retry_pending_with_fallback.py                    # all credit-blocked
  python scripts/retry_pending_with_fallback.py --include-untried  # also try never-run
  python scripts/retry_pending_with_fallback.py --limit 30         # safety cap
  python scripts/retry_pending_with_fallback.py --skip 'pitchbook' # skip domains containing
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import or_  # noqa: E402

from backend.db.connection import session_scope  # noqa: E402
from backend.db.models import SiteHealth  # noqa: E402
from backend.orchestrator.orchestrator import Orchestrator  # noqa: E402


def _reset_failure_state(domains: list[str]) -> None:
    """Wipe the credit-era failure streak so a single Together fallback miss
    doesn't immediately auto-exclude the site for 90 days."""
    if not domains:
        return
    with session_scope() as session:
        for d in domains:
            site = session.query(SiteHealth).filter(SiteHealth.domain == d).first()
            if not site:
                continue
            site.consecutive_failures = 0
            site.last_error = None
            site.status = "pending"
            site.exclude_until = None
            site.exclude_reason = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("retry_fallback")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--include-untried", action="store_true",
                   help="Also retry sites that have never been run.")
    p.add_argument("--limit", type=int, default=0, help="Max sites to retry (0 = all)")
    p.add_argument("--skip", default="",
                   help="Comma-separated substrings; sites containing any are skipped")
    args = p.parse_args()

    skip_tokens = [t.strip().lower() for t in args.skip.split(",") if t.strip()]

    with session_scope() as session:
        query = session.query(SiteHealth).filter(
            SiteHealth.worker_state == "pending",
            SiteHealth.status.notin_(["excluded"]),
        )
        if args.include_untried:
            # blocked OR untried
            query = query.filter(
                or_(
                    SiteHealth.last_error.ilike("%credit balance%"),
                    SiteHealth.last_error.ilike("%insufficient%"),
                    SiteHealth.total_runs == 0,
                )
            )
        else:
            query = query.filter(
                or_(
                    SiteHealth.last_error.ilike("%credit balance%"),
                    SiteHealth.last_error.ilike("%insufficient%"),
                )
            )

        sites = [(s.domain, s.url) for s in query.all() if s.url]

    if skip_tokens:
        before = len(sites)
        sites = [
            (d, u) for d, u in sites
            if not any(tok in (d or "").lower() or tok in (u or "").lower() for tok in skip_tokens)
        ]
        logger.info(f"skip filter dropped {before - len(sites)} sites")

    if args.limit > 0:
        sites = sites[: args.limit]

    logger.info(f"retrying {len(sites)} sites (Together fallback active)")

    # Wipe the credit-era failure streak so the HEALER doesn't 90-day-exclude
    # a site after one Together miss. We give every site a fresh 3-strike
    # budget under the new backend.
    _reset_failure_state([d for d, _ in sites])
    logger.info(f"reset failure streak for {len(sites)} sites")

    orch = Orchestrator()
    success = 0
    rows_added = 0
    started = time.time()
    for i, (domain, url) in enumerate(sites, start=1):
        try:
            result = orch.run(url, force=True)
            ok = getattr(result, "success", False)
            n_found = getattr(result, "records_found", 0) or 0
            n_new = getattr(result, "records_new", 0) or 0
            status = getattr(result, "status", "unknown")
            if ok:
                success += 1
                rows_added += n_new
            logger.info(
                f"[{i}/{len(sites)}] {domain:<32} status={status:<10} "
                f"found={n_found:>4} new={n_new:>4}"
            )
        except Exception as e:
            logger.error(f"[{i}/{len(sites)}] {domain}: ERR {e}")

    elapsed = time.time() - started
    logger.info(
        f"DONE in {elapsed:.0f}s: success={success}/{len(sites)} | rows_added={rows_added}"
    )


if __name__ == "__main__":
    main()
