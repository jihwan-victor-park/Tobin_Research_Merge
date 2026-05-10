#!/usr/bin/env python3
"""
Live Agent Activity Monitor
============================
A long-running terminal heartbeat that proves the multi-agent system is
actually working in real time. Polls the DB every few seconds and prints:

  - SCRAPING agents: rows that just landed in scrape_runs
  - HEALING agent : sites whose status / pending_reason changed
  - DISCOVERY     : new domains added to site_health
  - DATA WALL     : current company / signal counts

Intended for `tail -f`-style observation, not for production logging.

Run:
  python scripts/live_agent_monitor.py             # default 5s interval
  python scripts/live_agent_monitor.py --interval 2

Stop with Ctrl+C.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text  # noqa: E402

from backend.db.connection import get_engine  # noqa: E402


def _ts() -> str:
    return datetime.utcnow().strftime("%H:%M:%S")


def _emit(level: str, agent: str, msg: str) -> None:
    """Single-line, agent-tagged event print."""
    print(f"[{_ts()}] [{level}] [{agent:<10}] {msg}", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--interval", type=float, default=5.0,
                   help="Seconds between polls (default 5).")
    p.add_argument("--horizon-min", type=int, default=10,
                   help="Initial backfill window in minutes (default 10).")
    args = p.parse_args()

    engine = get_engine()
    seen_runs: Set[int] = set()
    seen_health_versions: dict[str, Tuple[str, str | None]] = {}
    seen_domains: Set[str] = set()

    horizon = datetime.utcnow() - timedelta(minutes=args.horizon_min)

    # Header
    print("=" * 78, flush=True)
    print(f"  LIVE AGENT MONITOR — polling every {args.interval}s "
          f"(initial backfill: last {args.horizon_min} min)", flush=True)
    print("  agents:", flush=True)
    print("    SCRAPER     — easy/hard tier scrape executions (scrape_runs table)", flush=True)
    print("    HEALER      — orchestrator health-state transitions (site_health)", flush=True)
    print("    DISCOVERY   — new domains entering site_health", flush=True)
    print("  Ctrl+C to stop.", flush=True)
    print("=" * 78, flush=True)

    # Prime caches on first read so we don't shout the entire backlog.
    with engine.connect() as conn:
        for row in conn.execute(text(
            "SELECT id FROM scrape_runs WHERE started_at < :h"
        ), {"h": horizon}).mappings().all():
            seen_runs.add(row["id"])
        for row in conn.execute(text(
            "SELECT domain, status, pending_reason FROM site_health"
        )).mappings().all():
            seen_health_versions[row["domain"]] = (row["status"], row["pending_reason"])
            seen_domains.add(row["domain"])

    _emit("BOOT", "monitor", f"primed: {len(seen_runs)} historical runs, "
                              f"{len(seen_domains)} known domains")

    try:
        while True:
            with engine.connect() as conn:
                # 1) New scrape runs
                rows = conn.execute(text(
                    "SELECT id, domain, scraper_name, difficulty, status, "
                    "       records_found, records_new, duration_seconds, started_at "
                    "FROM scrape_runs ORDER BY id DESC LIMIT 50"
                )).mappings().all()
                for r in reversed(rows):
                    if r["id"] in seen_runs:
                        continue
                    seen_runs.add(r["id"])
                    duration = f"{(r['duration_seconds'] or 0):.1f}s"
                    msg = (
                        f"{r['domain']:<32}  tier={r['difficulty']:<4} "
                        f"status={r['status']:<10} found={r['records_found'] or 0:>4} "
                        f"new={r['records_new'] or 0:>4}  ({duration})"
                    )
                    level = "OK" if r["status"] == "success" else "WARN"
                    _emit(level, "SCRAPER", msg)

                # 2) Health-state transitions
                health_rows = conn.execute(text(
                    "SELECT domain, status, pending_reason "
                    "FROM site_health"
                )).mappings().all()
                cur: dict[str, Tuple[str, str | None]] = {}
                for r in health_rows:
                    cur[r["domain"]] = (r["status"], r["pending_reason"])

                # 2a) New domains (DISCOVERY agent)
                new_domains = set(cur) - seen_domains
                for d in sorted(new_domains):
                    seen_domains.add(d)
                    _emit("INFO", "DISCOVERY", f"new domain registered: {d}")

                # 2b) State transitions (HEALER agent)
                for d, (new_status, new_reason) in cur.items():
                    prev = seen_health_versions.get(d)
                    if prev is None:
                        seen_health_versions[d] = (new_status, new_reason)
                        continue
                    prev_status, prev_reason = prev
                    if new_status != prev_status:
                        _emit("INFO", "HEALER",
                              f"{d:<32}  status: {prev_status} -> {new_status}")
                    if (new_reason or "") != (prev_reason or "") and new_reason:
                        _emit("INFO", "HEALER",
                              f"{d:<32}  diagnosis: {new_reason[:80]}")
                    seen_health_versions[d] = (new_status, new_reason)

                # 3) Periodic data wall (every ~10 polls)
                if int(time.time()) % max(int(args.interval * 10), 30) < args.interval:
                    counts = conn.execute(text(
                        "SELECT "
                        "  (SELECT COUNT(*) FROM companies) AS comps, "
                        "  (SELECT COUNT(*) FROM scrape_runs WHERE started_at > NOW() - INTERVAL '1 hour') AS runs_1h, "
                        "  (SELECT COUNT(*) FROM site_health WHERE worker_state='working') AS working, "
                        "  (SELECT COUNT(*) FROM site_health WHERE worker_state='pending') AS pending"
                    )).mappings().first()
                    _emit("STAT", "DATAWALL",
                          f"companies={counts['comps']:,} | "
                          f"runs(1h)={counts['runs_1h']} | "
                          f"working={counts['working']} | pending={counts['pending']}")

            time.sleep(args.interval)
    except KeyboardInterrupt:
        _emit("BOOT", "monitor", "stopped by user (Ctrl+C)")
        return


if __name__ == "__main__":
    main()
