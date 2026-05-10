#!/usr/bin/env python3
"""
LLM batch reclassification of `companies.ai_score` for hidden-AI rows.

Why this exists:
  Our keyword classifier (`backend.utils.classify_ai`) only flags companies
  whose name/description/tags contain a hard-coded AI vocabulary. That misses
  hidden-AI startups whose copy emphasises the application ("Platform for ML
  model deployment") rather than the technique ("LLM").

What this script does:
  1. Pulls companies with a non-trivial description AND an ai_score below the
     LLM threshold (or NULL). Pulls description from `companies.description`
     and from any `incubator_signals.description` joined on company_id.
  2. Sends them to the LLM in batches of 25 with a strict JSON contract.
  3. Updates ai_score / ai_tags from the LLM verdict (no destructive overwrite
     when the keyword tier already produced confident True — those keep their
     0.7+ score).

Usage:
  # Dry run on 50 candidates
  python scripts/reclassify_ai_with_llm.py --limit 50 --dry-run

  # Full pass — Claude Haiku via Anthropic by default (LLM_BACKEND env)
  python scripts/reclassify_ai_with_llm.py

  # Force a different backend / model
  LLM_BACKEND=together LLM_MODEL=meta-llama/Llama-3.3-70B-Instruct-Turbo \\
      python scripts/reclassify_ai_with_llm.py
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import func, or_  # noqa: E402

from backend.db.connection import session_scope  # noqa: E402
from backend.db.models import Company, IncubatorSignal  # noqa: E402
from backend.utils.llm_filter import (  # noqa: E402
    ANTHROPIC_API_KEY,
    GROQ_API_KEY,
    LLM_BACKEND,
    LLM_MODEL,
    TOGETHER_API_KEY,
    RateLimitError,
    _call_anthropic,
    _call_groq,
    _call_ollama,
    _call_together,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("reclassify_ai")


# ── Config ─────────────────────────────────────────────────────────────

# Re-classify rows whose current ai_score is strictly below this. 0.6 is the
# in-app "AI" threshold so anything <0.6 is currently *not* counted as AI.
TARGET_THRESHOLD = 0.6
# Minimum description length to be worth an LLM call (cheap filter).
MIN_DESCRIPTION_CHARS = 30
# Companies per LLM call.
BATCH_SIZE = 25
# Confidence floor for accepting the LLM's "AI" verdict.
LLM_AI_CONFIDENCE = 0.6
# Pacing between calls (cloud APIs).
PACING_SECONDS = 1.0
MAX_RETRIES = 3


SYSTEM_PROMPT = (
    "You decide whether each company is an AI/ML startup. "
    "Apply this rule: an AI startup is one whose CORE PRODUCT depends on "
    "machine learning, large language models, computer vision, robotics "
    "autonomy, recommendation systems, predictive modelling, or similar AI "
    "techniques. Companies that merely *use* third-party AI (e.g. a CRM that "
    "added an AI summariser) are NOT AI startups. "
    "Return STRICT JSON: a JSON array, one object per company, in the same "
    "order as input. Each object has keys: "
    "{\"id\": <int>, \"is_ai\": true|false, \"confidence\": 0.0-1.0, "
    "\"reason\": \"<one short sentence>\"}. "
    "No prose. No markdown. JSON array only."
)


# ── DB pull ────────────────────────────────────────────────────────────


def fetch_candidates(limit: int = 0) -> List[Dict]:
    """Pull (id, name, description, industry) for rows that need re-evaluation.

    Description preference: companies.description first, else the longest
    non-null incubator_signal.description. We never invent descriptions —
    rows with no description are skipped (LLM has nothing to classify on).
    """
    with session_scope() as session:
        # Subquery: longest incubator description per company.
        sub = (
            session.query(
                IncubatorSignal.company_id.label("cid"),
                func.max(IncubatorSignal.description).label("inc_desc"),
            )
            .filter(
                IncubatorSignal.description.isnot(None),
                func.length(IncubatorSignal.description) >= MIN_DESCRIPTION_CHARS,
            )
            .group_by(IncubatorSignal.company_id)
            .subquery()
        )

        q = (
            session.query(
                Company.id,
                Company.name,
                Company.description,
                Company.ai_tags,
                Company.ai_score,
                sub.c.inc_desc,
            )
            .outerjoin(sub, sub.c.cid == Company.id)
            .filter(
                or_(Company.ai_score.is_(None), Company.ai_score < TARGET_THRESHOLD),
                or_(
                    func.length(Company.description) >= MIN_DESCRIPTION_CHARS,
                    sub.c.inc_desc.isnot(None),
                ),
            )
            .order_by(Company.id)
        )
        if limit > 0:
            q = q.limit(limit)

        out: List[Dict] = []
        for row in q.yield_per(500):
            comp_desc = row.description or ""
            inc_desc = row.inc_desc or ""
            description = comp_desc if len(comp_desc) >= len(inc_desc) else inc_desc
            if len(description) < MIN_DESCRIPTION_CHARS:
                continue
            tags = ",".join(row.ai_tags) if row.ai_tags else ""
            out.append({
                "id": row.id,
                "name": row.name,
                "description": description.strip(),
                "tags": tags,
                "current_score": row.ai_score,
            })
    return out


# ── LLM dispatch ───────────────────────────────────────────────────────


def _llm_call(messages: List[Dict]) -> str:
    backend = (os.getenv("CLASSIFY_AI_BACKEND") or LLM_BACKEND or "anthropic").lower()
    if backend == "anthropic" and not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    if backend == "together" and not TOGETHER_API_KEY:
        raise RuntimeError("TOGETHER_API_KEY not set")
    if backend == "groq" and not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set")
    fn = {
        "anthropic": _call_anthropic,
        "together": _call_together,
        "groq": _call_groq,
        "ollama": _call_ollama,
    }.get(backend)
    if fn is None:
        raise RuntimeError(f"Unknown LLM_BACKEND: {backend}")
    return fn(messages, temperature=0.0)


def classify_batch(records: List[Dict]) -> List[Dict]:
    """Call the LLM on a 25-row batch. Returns one verdict dict per row."""
    blocks = []
    for r in records:
        blocks.append(
            f"--- COMPANY {r['id']} ---\n"
            f"Name: {r['name']}\n"
            f"Description: {r['description'][:600]}\n"
            f"Tags: {r['tags'] or '(none)'}"
        )
    user = (
        "Classify each company below. Return ONLY a JSON array.\n\n"
        + "\n\n".join(blocks)
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]

    last_error: Optional[str] = None
    for attempt in range(MAX_RETRIES):
        try:
            raw = _llm_call(messages)
        except RateLimitError as e:
            logger.warning(f"rate limited, sleeping {e.wait_seconds}s")
            time.sleep(e.wait_seconds)
            continue
        except Exception as e:
            last_error = str(e)
            logger.error(f"LLM call failed (attempt {attempt+1}): {e}")
            time.sleep(2 ** attempt)
            continue

        parsed = _parse_array(raw)
        if parsed is not None:
            return _align(parsed, records)
        last_error = "JSON parse failed"
        logger.warning(f"failed to parse LLM JSON (attempt {attempt+1})")
        time.sleep(1)

    logger.error(f"giving up on batch after retries: {last_error}")
    return [
        {"id": r["id"], "is_ai": False, "confidence": 0.0, "reason": "llm_unavailable"}
        for r in records
    ]


def _parse_array(raw: str) -> Optional[List[Dict]]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        data = json.loads(raw)
    except Exception:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except Exception:
            return None
    if not isinstance(data, list):
        return None
    return data


def _align(verdicts: List[Dict], records: List[Dict]) -> List[Dict]:
    """Map verdicts back to input records by id (positional fallback)."""
    by_id: Dict[int, Dict] = {}
    for v in verdicts:
        try:
            vid = int(v.get("id"))
        except (TypeError, ValueError):
            continue
        by_id[vid] = v
    out: List[Dict] = []
    for i, r in enumerate(records):
        v = by_id.get(r["id"]) or (verdicts[i] if i < len(verdicts) else {})
        out.append({
            "id": r["id"],
            "is_ai": bool(v.get("is_ai")),
            "confidence": _clip01(v.get("confidence", 0.0)),
            "reason": str(v.get("reason", ""))[:300],
        })
    return out


def _clip01(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        v = 0.0
    return max(0.0, min(1.0, v))


# ── Apply verdicts ─────────────────────────────────────────────────────


def apply_verdicts(verdicts: List[Dict], dry_run: bool) -> Tuple[int, int]:
    """Update Company.ai_score / ai_tags. Returns (updated, marked_ai)."""
    if dry_run or not verdicts:
        marked = sum(1 for v in verdicts if v["is_ai"] and v["confidence"] >= LLM_AI_CONFIDENCE)
        return (0, marked)

    updated = 0
    marked = 0
    with session_scope() as session:
        for v in verdicts:
            company = session.get(Company, v["id"])
            if company is None:
                continue
            old_score = company.ai_score
            if v["is_ai"] and v["confidence"] >= LLM_AI_CONFIDENCE:
                # Promote to a moderate AI score that beats the keyword baseline
                # without claiming we're 100% sure (LLM confidence < 1.0).
                new_score = max(old_score or 0.0, max(0.65, v["confidence"] - 0.05))
                if (old_score or 0.0) < TARGET_THRESHOLD <= new_score:
                    marked += 1
                company.ai_score = new_score
                tags = list(company.ai_tags or [])
                if "llm_classified_ai" not in tags:
                    tags.append("llm_classified_ai")
                company.ai_tags = tags
            else:
                # Mark a low-confidence rejection so we don't re-process it
                # forever — but only if currently NULL. Anything keyword-set
                # at 0.1 (negative) we leave alone for transparency.
                if old_score is None:
                    company.ai_score = 0.1
                tags = list(company.ai_tags or [])
                if "llm_classified_not_ai" not in tags:
                    tags.append("llm_classified_not_ai")
                company.ai_tags = tags
            updated += 1
    return (updated, marked)


# ── Main ───────────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(description="LLM batch reclassify ai_score")
    p.add_argument("--limit", type=int, default=0,
                   help="Max companies to evaluate (0 = all matching)")
    p.add_argument("--batch-size", type=int, default=BATCH_SIZE,
                   help=f"Companies per LLM call (default {BATCH_SIZE})")
    p.add_argument("--pacing", type=float, default=PACING_SECONDS,
                   help="Seconds to sleep between batches")
    p.add_argument("--dry-run", action="store_true",
                   help="Skip DB writes — useful to estimate cost / verdicts")
    args = p.parse_args()

    logger.info(
        f"backend={LLM_BACKEND} model={LLM_MODEL} batch_size={args.batch_size}"
    )
    candidates = fetch_candidates(limit=args.limit)
    if not candidates:
        logger.info("no candidates — already classified.")
        return

    logger.info(f"loaded {len(candidates)} candidates")
    total_batches = (len(candidates) + args.batch_size - 1) // args.batch_size
    promoted = 0
    processed = 0

    for i in range(0, len(candidates), args.batch_size):
        batch = candidates[i: i + args.batch_size]
        bnum = i // args.batch_size + 1
        logger.info(f"batch {bnum}/{total_batches} ({len(batch)} rows)")
        verdicts = classify_batch(batch)
        new_yes = sum(1 for v in verdicts if v["is_ai"] and v["confidence"] >= LLM_AI_CONFIDENCE)
        upd, marked = apply_verdicts(verdicts, args.dry_run)
        processed += upd
        promoted += marked
        logger.info(
            f"  -> verdict yes={new_yes}/{len(batch)} | "
            f"promoted={marked} | running totals updated={processed} promoted={promoted}"
        )
        if i + args.batch_size < len(candidates):
            time.sleep(args.pacing)

    logger.info(
        f"DONE: candidates={len(candidates)} updated={processed} "
        f"newly_marked_ai={promoted} dry_run={args.dry_run}"
    )


if __name__ == "__main__":
    main()
