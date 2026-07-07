#!/usr/bin/env python3
"""
LLM vertical classifier for companies without categories.

Targets companies where categories IS NULL and a description exists.
Sends batches of 25 to Claude Haiku with the 17 canonical verticals.
Only writes when Haiku returns a known canonical vertical — skips "Other".

Usage:
    python scripts/classify_verticals_with_llm.py [--dry-run] [--limit N] [--batch-size N]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import anthropic
from sqlalchemy import text

from backend.db.connection import get_engine
from backend.utils.industry import CANONICAL_VERTICALS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("classify_verticals")

MODEL = "claude-haiku-4-5-20251001"
PACING = 0.3   # seconds between batches (Haiku is fast, stay under rate limit)
MAX_RETRIES = 3

VERTICAL_LIST = "\n".join(f"- {v}" for v in CANONICAL_VERTICALS)

SYSTEM_PROMPT = f"""You classify companies into industry verticals.
Choose the single best vertical from this list for each company:
{VERTICAL_LIST}

Return ONLY a JSON array, one object per company in input order:
[{{"id": <int>, "vertical": "<exact vertical name from list>", "confidence": 0.0-1.0}}]
No prose. No markdown. JSON array only."""


def _fetch_candidates(engine, limit: int) -> list[dict]:
    query = """
        SELECT id, name, LEFT(description, 400) AS description
        FROM companies
        WHERE categories IS NULL
          AND description IS NOT NULL
          AND length(description) >= 30
        ORDER BY id
    """
    if limit:
        query += f" LIMIT {limit}"
    with engine.connect() as c:
        rows = c.execute(text(query)).fetchall()
    return [{"id": r[0], "name": r[1], "description": r[2]} for r in rows]


def _call_haiku(client: anthropic.Anthropic, records: list[dict]) -> list[dict]:
    blocks = []
    for r in records:
        blocks.append(
            f"ID:{r['id']} | {r['name']}\n{r['description'][:300]}"
        )
    user_msg = "Classify each company:\n\n" + "\n\n---\n\n".join(blocks)

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
                temperature=0.0,
            )
            raw = resp.content[0].text.strip()
            return _parse(raw, records)
        except anthropic.RateLimitError:
            wait = 15 * (attempt + 1)
            logger.warning(f"Rate limited; sleeping {wait}s")
            time.sleep(wait)
        except Exception as e:
            logger.error(f"Haiku call failed (attempt {attempt+1}): {e}")
            time.sleep(2 ** attempt)

    # Give up — return empty verdicts so we skip this batch
    return []


def _parse(raw: str, records: list[dict]) -> list[dict]:
    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.M)
    raw = re.sub(r"\s*```$", "", raw, flags=re.M)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except Exception:
            return []

    by_id = {int(v["id"]): v for v in data if "id" in v and "vertical" in v}
    out = []
    for i, r in enumerate(records):
        v = by_id.get(r["id"]) or (data[i] if i < len(data) else {})
        if not v:
            continue
        vertical = str(v.get("vertical", "")).strip()
        confidence = float(v.get("confidence", 0))
        if vertical in CANONICAL_VERTICALS and confidence >= 0.5:
            out.append({"id": r["id"], "vertical": vertical, "confidence": confidence})
    return out


def _apply(engine, verdicts: list[dict], dry_run: bool) -> int:
    if dry_run or not verdicts:
        return len(verdicts)
    with engine.begin() as c:
        for v in verdicts:
            c.execute(
                text("UPDATE companies SET categories = ARRAY[:v]::TEXT[] WHERE id = :id"),
                {"v": v["vertical"], "id": v["id"]},
            )
    return len(verdicts)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=0, help="Max companies (0=all)")
    p.add_argument("--batch-size", type=int, default=25)
    args = p.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    engine = get_engine()

    candidates = _fetch_candidates(engine, args.limit)
    logger.info(f"Companies to classify: {len(candidates):,}  batch_size={args.batch_size}")

    total_batches = (len(candidates) + args.batch_size - 1) // args.batch_size
    written = 0
    skipped = 0
    counts: Counter = Counter()

    for i in range(0, len(candidates), args.batch_size):
        batch = candidates[i : i + args.batch_size]
        bnum = i // args.batch_size + 1

        verdicts = _call_haiku(client, batch)
        skipped += len(batch) - len(verdicts)
        for v in verdicts:
            counts[v["vertical"]] += 1

        written += _apply(engine, verdicts, args.dry_run)

        if bnum % 20 == 0 or bnum == total_batches:
            logger.info(f"  [{bnum}/{total_batches}] written={written:,}  skipped={skipped}")

        if i + args.batch_size < len(candidates):
            time.sleep(PACING)

    logger.info(f"\nDone. {'[DRY RUN] ' if args.dry_run else ''}Written: {written:,}  Skipped/low-conf: {skipped}")
    logger.info("\nVertical distribution:")
    for v, n in sorted(counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {v:30} {n:>5,}")


if __name__ == "__main__":
    main()
