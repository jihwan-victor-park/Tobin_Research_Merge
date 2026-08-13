"""Decide whether a name-only hidden entity is a company or a person's GitHub account.

Most of the hidden population that has neither a domain nor a description came
from the GitHub scan, and a sample showed roughly two thirds are individual
user accounts rather than companies. Rather than *assume* that, this asks
GitHub directly: a login that resolves to type=Organization is evidence of a
real entity, type=User is evidence of a person, and a 404 means the account is
gone. The result is stored per company so the claim "this is not a company"
carries evidence instead of being inferred from missing data.

Free: the GitHub API allows 5,000 authenticated requests per hour. When that
budget runs out the script sleeps until the reset timestamp GitHub returns and
then continues on its own, so a multi-hour run needs no supervision.

    python scripts/classify_github_entities.py                 # run to completion
    python scripts/classify_github_entities.py --limit 200     # short test
    python scripts/classify_github_entities.py --status        # progress only
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import requests
from dotenv import load_dotenv
from sqlalchemy import text

from backend.db.connection import get_engine

load_dotenv()
TOKEN = os.getenv("GITHUB_TOKEN", "")
API = "https://api.github.com/users/"
HIDDEN = "verification_status = 'emerging_github'"
# the population in question: no domain and no description, so nothing in our
# own data says whether it is a company
NAME_ONLY = f"{HIDDEN} AND (description IS NULL OR description = '') AND domain IS NULL"

# GitHub also enforces an unpublished secondary limit, so hold a steady pace
# rather than bursting: 5,000/hour is ~1.4 req/s.
MIN_INTERVAL = 0.72
_pace_lock = threading.Lock()
_next_slot = [0.0]
# When the hourly budget is gone every worker must wait for the same reset.
_sleep_lock = threading.Lock()
_resume_at = [0.0]


def ensure_columns(engine) -> None:
    with engine.begin() as c:
        c.execute(text("""
            CREATE TABLE IF NOT EXISTS github_entity_check (
                company_id  INTEGER PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
                login       VARCHAR(200),
                entity_type VARCHAR(24),   -- Organization | User | missing | error
                real_name   VARCHAR(200),
                checked_at  TIMESTAMPTZ DEFAULT now()
            )
        """))


def _throttle() -> None:
    """Serialize requests to MIN_INTERVAL apart, and honour a global pause when
    the hourly budget has been exhausted."""
    while True:
        with _sleep_lock:
            wait = _resume_at[0] - time.time()
        if wait <= 0:
            break
        time.sleep(min(wait, 30))
    with _pace_lock:
        now = time.time()
        slot = max(now, _next_slot[0])
        _next_slot[0] = slot + MIN_INTERVAL
    delay = slot - time.time()
    if delay > 0:
        time.sleep(delay)


def _park_until_reset(resp) -> None:
    """Sleep until the window GitHub says the budget refills, then let everyone
    continue. Falls back to 60s when the header is absent."""
    reset = resp.headers.get("X-RateLimit-Reset")
    try:
        until = float(reset) + 5
    except (TypeError, ValueError):
        until = time.time() + 60
    with _sleep_lock:
        if until > _resume_at[0]:
            _resume_at[0] = until
            mins = max(0, (until - time.time()) / 60)
            print(f"  · rate limit reached — sleeping {mins:.1f} min until reset",
                  flush=True)


def lookup(session: requests.Session, login: str):
    """Return (entity_type, real_name). Retries once past a rate-limit pause."""
    for _ in range(2):
        _throttle()
        try:
            r = session.get(API + login, timeout=20)
        except requests.RequestException:
            return "error", None
        if r.status_code == 200:
            j = r.json()
            return j.get("type") or "unknown", j.get("name")
        if r.status_code == 404:
            return "missing", None
        # 403/429 with no budget left is the documented rate-limit signal
        if r.status_code in (403, 429) and r.headers.get("X-RateLimit-Remaining") == "0":
            _park_until_reset(r)
            continue
        return "error", None
    return "error", None


def progress(engine) -> dict:
    with engine.connect() as c:
        total = c.execute(text(f"SELECT COUNT(*) FROM companies WHERE {NAME_ONLY}")).scalar()
        done = c.execute(text(f"""
            SELECT COUNT(*) FROM companies co JOIN github_entity_check g ON g.company_id = co.id
            WHERE co.{NAME_ONLY}
        """)).scalar()
        rows = c.execute(text("""
            SELECT entity_type, COUNT(*) n FROM github_entity_check
            GROUP BY 1 ORDER BY 2 DESC
        """)).mappings().all()
    return {"total": total, "done": done, "by_type": {r["entity_type"]: r["n"] for r in rows}}


def show_status(engine) -> None:
    p = progress(engine)
    print(f"name-only entities : {p['total']:,}")
    print(f"checked            : {p['done']:,} ({p['done']/max(p['total'],1)*100:.1f}%)")
    for k, v in p["by_type"].items():
        share = v / max(p["done"], 1) * 100
        print(f"   {str(k):14} {v:6,} ({share:4.1f}%)")


def run(engine, limit: int, workers: int) -> None:
    with engine.connect() as c:
        rows = c.execute(text(f"""
            SELECT co.id, co.name FROM companies co
            LEFT JOIN github_entity_check g ON g.company_id = co.id
            WHERE co.{NAME_ONLY} AND g.company_id IS NULL
            LIMIT :lim
        """), {"lim": limit}).mappings().all()
    print(f"to check: {len(rows):,}  (workers={workers}, ~{MIN_INTERVAL}s apart)", flush=True)
    if not rows:
        return

    session = requests.Session()
    session.headers.update({"Accept": "application/vnd.github+json"})
    if TOKEN:
        session.headers["Authorization"] = f"Bearer {TOKEN}"
    else:
        print("  ! GITHUB_TOKEN not set — unauthenticated limit is only 60/hour", flush=True)

    def work(row):
        kind, real = lookup(session, str(row["name"]).strip())
        return row["id"], str(row["name"]).strip(), kind, real

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(work, r) for r in rows]):
            cid, login, kind, real = f.result()
            with engine.begin() as c:
                c.execute(text("""
                    INSERT INTO github_entity_check (company_id, login, entity_type, real_name, checked_at)
                    VALUES (:cid, :login, :kind, :real, now())
                    ON CONFLICT (company_id) DO UPDATE
                      SET login = EXCLUDED.login, entity_type = EXCLUDED.entity_type,
                          real_name = EXCLUDED.real_name, checked_at = now()
                """), {"cid": cid, "login": login[:200], "kind": kind,
                       "real": (real or None) and real[:200]})
            done += 1
            if done % 200 == 0:
                p = progress(engine)
                print(f"  {done}/{len(rows)} this batch · overall "
                      f"{p['done']:,}/{p['total']:,} — {p['by_type']}", flush=True)
    print(f"✓ batch done ({done:,} checked)", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()

    engine = get_engine()
    ensure_columns(engine)
    if a.status:
        show_status(engine)
        return
    run(engine, a.limit, a.workers)
    print()
    show_status(engine)


if __name__ == "__main__":
    main()
