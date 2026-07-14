#!/usr/bin/env python3
"""
Domain-liveness survival proxy for the non-CB/PB company population.

METHODOLOGY CAVEAT (read before trusting this data):
This checks whether a company's domain currently resolves and serves a page —
it is NOT a verified operating-status field. A "dead" result can mean the
company shut down, but it can equally mean: the domain lapsed while the
company kept operating under a new one, a temporary hosting outage, an
overzealous bot-block responding 403 to a plain requests.get, or a rebrand
without a redirect. A "live" result can equally be a parked domain someone
squatted after the real company died. Treat this as a noisy proxy for
survival, not ground truth — and remember it only covers companies that have
a domain at all (41% of the non-CB/PB population; the rest are simply
`unchecked`, not presumed dead).

Writes to two new columns on `companies` (kept separate from the CB/PB-
semantics `operating_status` enum, which means something stronger):
  - domain_status:     'live' | 'dead' | 'unchecked'
  - domain_checked_at: timestamp of the check (so re-checks are possible later)

Usage:
    python scripts/check_domain_liveness.py --non-cb-pb-only --dry-run
    python scripts/check_domain_liveness.py --non-cb-pb-only
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.db.connection import get_engine  # noqa: E402

TIMEOUT_SECONDS = 6
MAX_WORKERS = 40
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

NON_CB_PB_FILTER = (
    "verification_status NOT IN ('verified_cb', 'verified_pb', 'verified_cb_pb')"
)


def ensure_columns(engine) -> None:
    with engine.connect() as conn:
        for col, ddl in [
            ("domain_status", "ALTER TABLE companies ADD COLUMN domain_status VARCHAR(16)"),
            ("domain_checked_at", "ALTER TABLE companies ADD COLUMN domain_checked_at TIMESTAMP"),
        ]:
            exists = conn.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'companies' AND column_name = :col"
            ), {"col": col}).fetchone()
            if exists is None:
                conn.execute(text(ddl))
                conn.commit()
                print(f"  Added column companies.{col}")


def check_one(domain: str) -> str:
    url = domain if domain.startswith(("http://", "https://")) else f"https://{domain}"
    try:
        resp = requests.get(
            url, headers=HEADERS, timeout=TIMEOUT_SECONDS,
            allow_redirects=True, stream=True,
        )
        resp.close()
        return "live" if resp.status_code < 500 else "dead"
    except requests.exceptions.SSLError:
        # Retry once over plain HTTP — some small/old sites never set up TLS.
        try:
            resp = requests.get(
                f"http://{domain}", headers=HEADERS, timeout=TIMEOUT_SECONDS,
                allow_redirects=True, stream=True,
            )
            resp.close()
            return "live" if resp.status_code < 500 else "dead"
        except Exception:
            return "dead"
    except Exception:
        return "dead"


def fetch_candidates(engine, non_cb_pb_only: bool, limit: int) -> list[tuple[int, str]]:
    where = ["domain IS NOT NULL"]
    if non_cb_pb_only:
        where.append(NON_CB_PB_FILTER)
    sql = f"SELECT id, domain FROM companies WHERE {' AND '.join(where)} ORDER BY id"
    if limit > 0:
        sql += f" LIMIT {limit}"
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
    return [(r[0], r[1]) for r in rows]


def bulk_write(engine, results: list[tuple[int, str]], checked_at: datetime, chunk_size: int = 2000) -> None:
    if not results:
        return
    stmt = text(
        "UPDATE companies SET domain_status = :status, domain_checked_at = :checked_at "
        "WHERE id = :id"
    )
    with engine.begin() as conn:
        for i in range(0, len(results), chunk_size):
            chunk = results[i:i + chunk_size]
            conn.execute(stmt, [
                {"id": cid, "status": status, "checked_at": checked_at}
                for cid, status in chunk
            ])


def main() -> None:
    ap = argparse.ArgumentParser(description="Check domain liveness as a survival proxy")
    ap.add_argument("--non-cb-pb-only", action="store_true", help="Scope to non-CB/PB companies")
    ap.add_argument("--limit", type=int, default=0, help="Cap candidates (0 = all)")
    ap.add_argument("--dry-run", action="store_true", help="Print results only, no DB writes")
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    args = ap.parse_args()

    engine = get_engine()
    candidates = fetch_candidates(engine, args.non_cb_pb_only, args.limit)
    print(f"Checking {len(candidates):,} domains ({args.workers} workers, {TIMEOUT_SECONDS}s timeout)...")

    results: list[tuple[int, str]] = []
    live = dead = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(check_one, domain): (cid, domain) for cid, domain in candidates}
        for i, future in enumerate(as_completed(futures), 1):
            cid, domain = futures[future]
            status = future.result()
            results.append((cid, status))
            if status == "live":
                live += 1
            else:
                dead += 1
            if i % 1000 == 0:
                print(f"  checked {i:,}/{len(candidates):,}  (live={live:,} dead={dead:,})", flush=True)

    print(f"\nDone: live={live:,} dead={dead:,} out of {len(candidates):,}")

    if args.dry_run:
        print("(dry-run — no DB writes)")
        return

    ensure_columns(engine)
    checked_at = datetime.now(timezone.utc)
    bulk_write(engine, results, checked_at)
    print("Written to companies.domain_status / domain_checked_at.")


if __name__ == "__main__":
    main()
