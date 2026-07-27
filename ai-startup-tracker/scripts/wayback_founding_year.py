#!/usr/bin/env python3
"""
Wayback-Machine first-capture year as a founding-year proxy for hidden
companies that have a domain but no founded_year and no cohort_year.

METHODOLOGY CAVEAT (read before trusting web_first_seen_year):
This is the LOOSEST of our founding-year proxies. It's the year archive.org
first captured the domain, which:
  - usually lags true founding (archive didn't crawl on day one), biasing late;
  - can PREDATE the company entirely if the domain was previously owned by
    someone else (e.g. openai.com's first capture is 2001, long before OpenAI),
    biasing early;
  - is missing for domains archive.org never crawled.
Priority for "effective founding year": founded_year (real) > cohort_year
(accelerator batch) > web_first_seen_year (this). Use only as a last-resort
gap-filler, clearly labeled as a proxy.

Runs directly against the target DB (RAILWAY_DATABASE_URL if --railway, else
DATABASE_URL), self-contained by id. Writes companies.web_first_seen_year.
Incremental: writes in chunks so a crash/timeout keeps partial progress, and
re-runs skip rows already checked (web_first_seen_year IS NOT NULL OR a
sentinel is set). Rows with no snapshot get web_first_seen_year = 0 (checked,
none found) so we don't re-query them forever.

Usage:
    python scripts/wayback_founding_year.py --railway --limit 50   # sample
    python scripts/wayback_founding_year.py --railway              # full run
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

NON_CB_PB = "verification_status NOT IN ('verified_cb', 'verified_pb', 'verified_cb_pb')"
CDX = "http://web.archive.org/cdx/search/cdx"
TIMEOUT = 25
WORKERS = 4          # archive.org rate-limits bursts — keep concurrency low
YEAR_MIN, YEAR_MAX = 1996, 2026  # Wayback started 1996
WRITE_EVERY = 200


def oldest_year(domain: str):
    """Earliest Wayback capture year.

    Returns: an int year (usable), 0 (genuine empty — archive has no snapshot),
    or None (transient error / rate-limit — caller should NOT write, so the row
    stays NULL and a re-run retries it). Distinguishing None from 0 is what
    stops rate-limit resets being mislabeled as 'no snapshot'.
    """
    for attempt in range(3):
        try:
            r = requests.get(CDX, params={
                "url": domain, "output": "json", "fl": "timestamp", "limit": 1,
            }, timeout=TIMEOUT)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(3 * (attempt + 1)); continue
            data = r.json()
            if len(data) > 1:
                y = int(data[1][0][:4])
                return y if YEAR_MIN <= y <= YEAR_MAX else 0
            return 0  # genuine empty
        except Exception:
            time.sleep(3 * (attempt + 1))
    return None  # transient — leave NULL, retry on a later run


def connect(url: str):
    return psycopg2.connect(url, connect_timeout=20)


def ensure_column(conn) -> None:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM information_schema.columns "
                "WHERE table_name='companies' AND column_name='web_first_seen_year'")
    if cur.fetchone() is None:
        cur.execute("ALTER TABLE companies ADD COLUMN web_first_seen_year INTEGER")
        conn.commit()
        print("  Added column companies.web_first_seen_year")


def flush(url: str, rows: list[tuple[int, int]], max_retries: int = 6) -> None:
    if not rows:
        return
    sql = ("UPDATE companies AS c SET web_first_seen_year = v.yr "
           "FROM (VALUES %s) AS v(id, yr) WHERE c.id = v.id")
    conn = connect(url); cur = conn.cursor()
    for attempt in range(1, max_retries + 1):
        try:
            psycopg2.extras.execute_values(cur, sql, rows, template="(%s, %s)")
            conn.commit(); break
        except psycopg2.OperationalError as e:
            print(f"    write retry {attempt}/{max_retries}: {e}")
            try: conn.close()
            except Exception: pass
            time.sleep(3); conn = connect(url); cur = conn.cursor()
    conn.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--railway", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=WORKERS)
    args = ap.parse_args()

    url = os.getenv("RAILWAY_DATABASE_URL") if args.railway else os.getenv("DATABASE_URL")
    if not url:
        sys.exit("target DB URL not set")
    print(f"Target: {'RAILWAY' if args.railway else 'LOCAL'}")

    conn = connect(url); ensure_column(conn)
    cur = conn.cursor()
    sql = (f"SELECT id, domain FROM companies WHERE {NON_CB_PB} "
           "AND domain IS NOT NULL AND founded_year IS NULL AND cohort_year IS NULL "
           "AND web_first_seen_year IS NULL ORDER BY id")
    if args.limit:
        sql += f" LIMIT {args.limit}"
    cur.execute(sql)
    targets = cur.fetchall()
    conn.close()
    print(f"Querying Wayback for {len(targets):,} domains ({args.workers} workers)...")

    pending: list[tuple[int, int]] = []
    found = checked = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(oldest_year, dom): cid for cid, dom in targets}
        for i, fut in enumerate(as_completed(futs), 1):
            cid = futs[fut]
            yr = fut.result()
            checked += 1
            if yr is None:
                continue  # transient error — leave NULL for a later retry
            pending.append((cid, yr))
            if yr > 0:
                found += 1
            if len(pending) >= WRITE_EVERY:
                flush(url, pending); pending = []
            if i % 250 == 0:
                rate = i / (time.time() - t0)
                print(f"  {i:,}/{len(targets):,}  found_year={found:,}  "
                      f"({rate:.1f}/s, ~{(len(targets)-i)/rate/60:.0f}min left)", flush=True)
    flush(url, pending)
    print(f"\nDone: {checked:,} checked, {found:,} got a year "
          f"({100*found/max(1,checked):.0f}% hit rate).")


if __name__ == "__main__":
    main()
