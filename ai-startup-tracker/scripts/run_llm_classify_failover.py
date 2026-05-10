#!/usr/bin/env python3
"""
LLM classification of unclassified GithubRepoSnapshot rows with automatic
backend failover.

Strategy:
  1. Start with Together.ai (cheap: ~$0.88/M tokens, in/out symmetric).
  2. On Together credit / payment / auth / quota errors, transparently
     switch the in-process backend to Anthropic Claude Haiku 4.5 and
     resume the SAME batch (no progress lost, no rewind).
  3. Same parsing / DB-write logic as `run_llm_classify.py`.

This wraps the lower-level helpers from `backend.utils.llm_filter` so we
re-use the prompt, batching, and JSON-extraction code rather than forking
it. The decision of "is this a credit-out error?" is intentionally
conservative — only swap on signals that look like billing / quota /
auth, never on a transient 5xx or rate-limit (those are retried by the
existing retry loop).

Usage:
  # Smoke test (no DB writes)
  python scripts/run_llm_classify_failover.py --limit 25 --dry-run

  # Real run, all unclassified rows, Together first
  python scripts/run_llm_classify_failover.py

  # Force Anthropic from the start (skip Together)
  python scripts/run_llm_classify_failover.py --start-backend anthropic

Logs go to stdout AND ``logs/llm_classify_failover.log``. Tail it with:
  tail -f logs/llm_classify_failover.log
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
from typing import Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv()

from backend.db.connection import session_scope  # noqa: E402
from backend.db.models import GithubRepoSnapshot  # noqa: E402
from backend.utils import llm_filter  # noqa: E402  (we mutate llm_filter.LLM_BACKEND)
from backend.utils.llm_filter import (  # noqa: E402
    BATCH_SIZE,
    LLM_STARTUP_CONFIDENCE,
    RateLimitError,
    SYSTEM_PROMPT,
    _build_repo_summary,
    _call_anthropic,
    _call_together,
)

# ── Logging ────────────────────────────────────────────────────────────
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "llm_classify_failover.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("llm_classify_failover")


# ── Failover detection ────────────────────────────────────────────────

# Substrings (case-insensitive) that indicate "this Together call failed
# because credits / quota / billing / auth ran out, not because of a
# transient blip". Anything matching here triggers a permanent swap to
# Anthropic for the rest of the run.
CREDIT_OUT_MARKERS = (
    "insufficient",
    "credit",
    "quota",
    "billing",
    "payment",
    "balance",
    "exceeded",
    "out of",
    "401",
    "402",
    "403",
    "unauthorized",
    "forbidden",
    "suspended",
    "deactivated",
    "expired",
)


def _looks_like_credit_out(err: BaseException) -> bool:
    msg = str(err).lower()
    return any(marker in msg for marker in CREDIT_OUT_MARKERS)


# ── Backend dispatch with in-process swap ─────────────────────────────


class BackendSwitcher:
    """Holds the currently active backend and swaps it on credit-out."""

    def __init__(self, start_backend: str = "together") -> None:
        self.backend = start_backend.lower()
        self._anthropic_model = (
            os.getenv("ANTHROPIC_MODEL") or "claude-haiku-4-5-20251001"
        )
        self._together_model = (
            os.getenv("LLM_MODEL") or "meta-llama/Llama-3.3-70B-Instruct-Turbo"
        )
        # Mutate the global so anything else that imports llm_filter
        # (e.g. retry helpers) sees the same backend.
        llm_filter.LLM_BACKEND = self.backend

    def model_label(self) -> str:
        if self.backend == "anthropic":
            return self._anthropic_model
        if self.backend == "together":
            return self._together_model
        return self.backend

    def call(self, messages: List[Dict], temperature: float = 0.1) -> str:
        if self.backend == "together":
            return _call_together(messages, temperature=temperature)
        if self.backend == "anthropic":
            return _call_anthropic(messages, temperature=temperature)
        raise RuntimeError(f"Unsupported backend in switcher: {self.backend}")

    def swap_to_anthropic(self, reason: str) -> None:
        if self.backend == "anthropic":
            return
        logger.warning(
            f"Swapping LLM backend: together -> anthropic (reason: {reason})"
        )
        if not llm_filter.ANTHROPIC_API_KEY:
            raise RuntimeError(
                "Cannot fail over: ANTHROPIC_API_KEY not set in .env"
            )
        # Switch the Anthropic model env so _call_anthropic picks Haiku 4.5
        # even if .env had something else.
        os.environ["ANTHROPIC_MODEL"] = self._anthropic_model
        self.backend = "anthropic"
        llm_filter.LLM_BACKEND = "anthropic"


# ── Batch classify (with failover) ────────────────────────────────────


def _build_messages(records: List[Dict]) -> List[Dict]:
    repo_blocks = []
    for i, rec in enumerate(records):
        summary = _build_repo_summary(rec)
        repo_blocks.append(f"--- REPO {i+1} ---\n{summary}")
    user_prompt = (
        "Classify each of the following GitHub repositories. "
        "Return a JSON array with one object per repo, in the same order.\n\n"
        + "\n\n".join(repo_blocks)
        + "\n\nReturn ONLY the JSON array, no other text."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def _parse_array(content: str, n_expected: int) -> List[Dict]:
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    content = content.strip()
    results = json.loads(content)
    if not isinstance(results, list):
        results = [results]
    while len(results) < n_expected:
        results.append({
            "classification": "unknown",
            "confidence": 0.0,
            "reason": "missing from response",
        })
    return results[:n_expected]


def classify_batch_failover(
    records: List[Dict],
    switcher: BackendSwitcher,
    max_retries: int = 3,
) -> List[Dict]:
    """Like `classify_batch_with_llm` but swaps Together -> Anthropic on
    credit-out errors, and otherwise retries transient failures."""
    messages = _build_messages(records)

    for attempt in range(max_retries):
        try:
            content = switcher.call(messages)
            return _parse_array(content, n_expected=len(records))

        except RateLimitError as e:
            logger.warning(
                f"Rate limited on {switcher.backend}, sleeping {e.wait_seconds}s "
                f"(attempt {attempt+1}/{max_retries})"
            )
            time.sleep(e.wait_seconds)
            continue

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed (attempt {attempt+1}): {e}")
            time.sleep(2)
            continue

        except Exception as e:
            if _looks_like_credit_out(e) and switcher.backend == "together":
                switcher.swap_to_anthropic(reason=str(e)[:200])
                continue
            logger.error(
                f"LLM call failed on {switcher.backend} "
                f"(attempt {attempt+1}/{max_retries}): {e}"
            )
            time.sleep(min(2 ** attempt, 30))
            continue

    logger.error("Giving up batch after retries.")
    return [
        {"classification": "unknown", "confidence": 0.0, "reason": "retries exhausted"}
        for _ in records
    ]


# ── Snapshot fetch + DB write ──────────────────────────────────────────


def get_unclassified_snapshots(limit: int = 0) -> List[Dict]:
    with session_scope() as session:
        q = (
            session.query(GithubRepoSnapshot)
            .filter(GithubRepoSnapshot.llm_classification.is_(None))
            .order_by(GithubRepoSnapshot.startup_likelihood.desc().nullslast())
        )
        if limit > 0:
            q = q.limit(limit)
        snapshots = q.all()
        out: List[Dict] = []
        for s in snapshots:
            out.append({
                "repo_full_name": s.repo_full_name,
                "owner_type": s.owner_type,
                "description": s.description,
                "domain": None,
                "homepage_url": s.homepage_url,
                "topics": s.topics or [],
                "stars": s.stars or 0,
                "forks": s.forks or 0,
                "language": s.language,
                "readme_snippet": None,
                "startup_likelihood": s.startup_likelihood,
                "snapshot_id": s.id,
            })
        return out


def write_results(batch: List[Dict], results: List[Dict]) -> Tuple[int, int]:
    """Persist classification verdicts. Returns (written, startups)."""
    written = 0
    startups = 0
    with session_scope() as session:
        for rec, result in zip(batch, results):
            snapshot = session.get(GithubRepoSnapshot, rec["snapshot_id"])
            if not snapshot:
                continue
            classification = result.get("classification", "unknown")
            try:
                confidence = float(result.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            snapshot.llm_classification = classification
            snapshot.llm_confidence = confidence
            snapshot.llm_reason = str(result.get("reason", ""))[:1000]
            written += 1
            if classification == "startup" and confidence >= LLM_STARTUP_CONFIDENCE:
                startups += 1
    return written, startups


# ── Driver ─────────────────────────────────────────────────────────────


def run(
    limit: int,
    dry_run: bool,
    start_backend: str,
    pacing: float,
    batch_size: int,
) -> None:
    if start_backend == "together" and not llm_filter.TOGETHER_API_KEY:
        logger.warning("TOGETHER_API_KEY missing — starting on anthropic instead.")
        start_backend = "anthropic"
    if start_backend == "anthropic" and not llm_filter.ANTHROPIC_API_KEY:
        raise SystemExit("ANTHROPIC_API_KEY not set; cannot run.")

    switcher = BackendSwitcher(start_backend=start_backend)
    logger.info(
        f"start_backend={switcher.backend} model={switcher.model_label()} "
        f"batch_size={batch_size} dry_run={dry_run} limit={limit or 'all'}"
    )

    records = get_unclassified_snapshots(limit=limit)
    if not records:
        logger.info("No unclassified snapshots — nothing to do.")
        return

    total = len(records)
    total_batches = (total + batch_size - 1) // batch_size
    logger.info(f"Loaded {total} unclassified snapshots in {total_batches} batches")

    started_at = datetime.utcnow()
    written = 0
    startups_total = 0
    backend_swaps = 0
    last_backend = switcher.backend

    for i in range(0, total, batch_size):
        batch = records[i: i + batch_size]
        bnum = i // batch_size + 1
        logger.info(
            f"Batch {bnum}/{total_batches} ({len(batch)} repos) "
            f"on backend={switcher.backend}"
        )

        results = classify_batch_failover(batch, switcher)

        if switcher.backend != last_backend:
            backend_swaps += 1
            last_backend = switcher.backend

        new_startups = sum(
            1
            for r in results
            if r.get("classification") == "startup"
            and float(r.get("confidence", 0)) >= LLM_STARTUP_CONFIDENCE
        )

        if not dry_run:
            w, s = write_results(batch, results)
            written += w
            startups_total += s
        else:
            startups_total += new_startups

        logger.info(
            f"  -> startups_in_batch={new_startups} | "
            f"running written={written} startups={startups_total} swaps={backend_swaps}"
        )

        if i + batch_size < total and pacing > 0:
            time.sleep(pacing)

    elapsed = (datetime.utcnow() - started_at).total_seconds()
    logger.info(
        f"DONE in {elapsed:.0f}s: total={total} written={written} "
        f"startups={startups_total} backend_swaps={backend_swaps} "
        f"final_backend={switcher.backend}"
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--limit", type=int, default=0,
                   help="Max snapshots to classify (0 = all unclassified)")
    p.add_argument("--dry-run", action="store_true",
                   help="Run LLM but don't write to DB")
    p.add_argument("--start-backend", default="together",
                   choices=["together", "anthropic"],
                   help="Backend to use first (default: together)")
    p.add_argument("--pacing", type=float, default=2.0,
                   help="Seconds between batches (default 2)")
    p.add_argument("--batch-size", type=int, default=BATCH_SIZE,
                   help=f"Repos per LLM call (default {BATCH_SIZE})")
    args = p.parse_args()

    run(
        limit=args.limit,
        dry_run=args.dry_run,
        start_backend=args.start_backend,
        pacing=args.pacing,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
