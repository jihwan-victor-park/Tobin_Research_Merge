#!/usr/bin/env python3
"""
PitchBook AI classifier — resolves whether ai_score is fit for research use.

Problem (see HANDOFF.md "Is ai_score fit for purpose?"): the keyword-based
ai_score maxes out at ~0.3 for PitchBook companies (271K rows), permanently
below the 0.5 research threshold. `cb_ai_tagged OR ai_score>=0.5` therefore
silently excludes PitchBook's AI companies. This script asks an LLM directly
"is AI the core product?" for every PitchBook company the cheap keyword
cascade can't already decide, and stores the verdict in a new
`companies.llm_ai_verified` column.

Cost control: only the AMBIGUOUS band (tech-adjacent language, no explicit AI
marker) goes to the LLM — confident keyword hits/misses are written directly.
LLM calls run through the Message Batches API (50% discount vs sync calls).

Usage:
    # Step 1 — pilot: 100 candidates via live (non-batch) calls, verify JSON
    # parses cleanly and verdicts look sane before spending on the full batch.
    python scripts/classify_pb_ai_with_llm.py --pilot

    # Step 2 — dry-run cost accounting only (no writes, no batch submitted)
    python scripts/classify_pb_ai_with_llm.py --dry-run

    # Step 3 — submit the full batch (writes keyword verdicts now; LLM
    # verdicts land later). Persists batch id + row mapping to resume.
    python scripts/classify_pb_ai_with_llm.py --submit

    # Step 4 — check / apply results once the batch has ended
    python scripts/classify_pb_ai_with_llm.py --resume
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import func, text  # noqa: E402

from backend.db.connection import get_engine, session_scope  # noqa: E402
from backend.db.models import Company, VerificationStatus  # noqa: E402
from backend.utils.classify_ai import classify_ai  # noqa: E402

import anthropic  # noqa: E402
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming  # noqa: E402
from anthropic.types.messages.batch_create_params import Request  # noqa: E402

MODEL = "claude-haiku-4-5"
BATCH_SIZE = 25
MAX_DESC_CHARS = 300
MIN_DESC_CHARS = 30
DEFAULT_MAX_COST = 15.0
# Batch API pricing: 50% off standard $1.00/$5.00 per MTok for Haiku 4.5.
BATCH_INPUT_PER_MTOK = 0.50
BATCH_OUTPUT_PER_MTOK = 2.50

STATE_PATH = PROJECT_ROOT / "output" / "classify_pb_batch_state.json"

SYSTEM_PROMPT = (
    "You decide whether each company's CORE PRODUCT is AI (machine learning, "
    "LLMs, computer vision, robotics autonomy, recommendation/predictive "
    "modelling, or similar AI techniques). Companies that merely USE "
    "third-party AI internally (e.g. a CRM with an AI summarizer bolted on) "
    "are NOT AI companies. For each company in the input, in the same order, "
    "return a verdict."
)

RESPONSE_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "is_ai": {"type": "boolean"},
                    },
                    "required": ["index", "is_ai"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["verdicts"],
        "additionalProperties": False,
    },
}


# ── Column setup ───────────────────────────────────────────────────────

def ensure_column() -> None:
    engine = get_engine()
    with engine.connect() as conn:
        exists = conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'companies' AND column_name = 'llm_ai_verified'"
        )).fetchone()
        if exists is None:
            conn.execute(text("ALTER TABLE companies ADD COLUMN llm_ai_verified BOOLEAN"))
            conn.commit()
            print("  Added column companies.llm_ai_verified")


# ── Candidate selection ───────────────────────────────────────────────

def fetch_candidates(limit: int = 0) -> Tuple[List[Tuple[int, bool]], List[Dict]]:
    """Return (keyword_verdicts, llm_candidates).

    keyword_verdicts: [(company_id, is_ai), ...] — confident keyword decisions,
    written directly, no LLM call needed.
    llm_candidates: [{"id", "name", "description", "tags"}, ...] — ambiguous
    band that needs the LLM.
    """
    keyword_verdicts: List[Tuple[int, bool]] = []
    llm_candidates: List[Dict] = []
    with session_scope() as session:
        q = (
            session.query(Company.id, Company.name, Company.description, Company.ai_tags)
            .filter(
                Company.verification_status == VerificationStatus.verified_pb,
                Company.cb_ai_tagged == False,  # noqa: E712
                func.length(Company.description) >= MIN_DESC_CHARS,
            )
            .order_by(Company.id)
        )
        if limit > 0:
            q = q.limit(limit)

        for row in q.yield_per(2000):
            tags = ",".join(row.ai_tags) if row.ai_tags else None
            is_ai, conf, source = classify_ai(row.name, row.description, tags, keyword_only=True)
            if source == "keyword":
                keyword_verdicts.append((row.id, is_ai))
            else:
                llm_candidates.append({
                    "id": row.id,
                    "name": row.name,
                    "description": (row.description or "")[:MAX_DESC_CHARS],
                    "tags": tags or "",
                })
    return keyword_verdicts, llm_candidates


def bulk_write_verdicts(updates: List[Tuple[int, bool]], chunk_size: int = 5000) -> None:
    """Raw-SQL executemany-style batch update — orders of magnitude faster
    than per-row ORM updates for tens/hundreds of thousands of rows."""
    if not updates:
        return
    engine = get_engine()
    stmt = text("UPDATE companies SET llm_ai_verified = :is_ai WHERE id = :id")
    with engine.begin() as conn:
        for i in range(0, len(updates), chunk_size):
            chunk = updates[i:i + chunk_size]
            conn.execute(stmt, [{"id": cid, "is_ai": is_ai} for cid, is_ai in chunk])


def apply_keyword_verdicts(verdicts: List[Tuple[int, bool]], dry_run: bool) -> None:
    if dry_run or not verdicts:
        return
    bulk_write_verdicts(verdicts)
    print(f"  wrote {len(verdicts)} keyword-confident verdicts directly (no LLM call)")


# ── Request building ──────────────────────────────────────────────────

def build_prompt(records: List[Dict]) -> str:
    blocks = []
    for i, r in enumerate(records):
        blocks.append(
            f"[{i}] Name: {r['name']}\n"
            f"Description: {r['description']}\n"
            f"Tags: {r['tags'] or '(none)'}"
        )
    return "Classify each company below. Index matches the [N] prefix.\n\n" + "\n\n".join(blocks)


def build_request_params(records: List[Dict]) -> dict:
    return {
        "model": MODEL,
        "max_tokens": 2000,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": build_prompt(records)}],
        "output_config": {"format": RESPONSE_SCHEMA},
    }


def parse_response_text(text_content: str) -> Optional[List[Dict]]:
    try:
        data = json.loads(text_content)
    except Exception:
        return None
    verdicts = data.get("verdicts")
    if not isinstance(verdicts, list):
        return None
    return verdicts


def align_verdicts(verdicts: List[Dict], records: List[Dict]) -> List[Tuple[int, bool]]:
    by_index = {}
    for v in verdicts:
        try:
            idx = int(v["index"])
        except (KeyError, TypeError, ValueError):
            continue
        by_index[idx] = bool(v.get("is_ai"))
    out = []
    for i, r in enumerate(records):
        if i in by_index:
            out.append((r["id"], by_index[i]))
    return out


# ── Pilot (live calls, no batch) ────────────────────────────────────────

def run_pilot(client: anthropic.Anthropic, candidates: List[Dict]) -> None:
    pilot = candidates[:100]
    groups = [pilot[i:i + BATCH_SIZE] for i in range(0, len(pilot), BATCH_SIZE)]
    print(f"PILOT: {len(pilot)} companies in {len(groups)} live calls (model={MODEL})")

    total_verdicts = 0
    total_parsed = 0
    all_rows: List[Tuple[Dict, bool]] = []

    for gi, group in enumerate(groups):
        params = build_request_params(group)
        resp = client.messages.create(**params)
        text_block = next((b.text for b in resp.content if b.type == "text"), None)
        verdicts = parse_response_text(text_block) if text_block else None
        total_verdicts += len(group)
        if verdicts is None:
            print(f"  group {gi}: FAILED TO PARSE JSON — raw: {text_block!r}")
            continue
        aligned = align_verdicts(verdicts, group)
        total_parsed += len(aligned)
        for (rid, is_ai), rec in zip(aligned, group):
            all_rows.append((rec, is_ai))

    print(f"\nPILOT RESULT: {total_parsed}/{total_verdicts} verdicts parsed and index-aligned")
    if total_parsed != total_verdicts:
        print("  WARNING: parse/alignment failures in pilot — investigate before --submit")

    print("\nSample verdicts (first 20):")
    for rec, is_ai in all_rows[:20]:
        print(f"  [{'AI' if is_ai else '--'}] {rec['name'][:50]:<50} {rec['description'][:70]}")

    ai_count = sum(1 for _, is_ai in all_rows if is_ai)
    print(f"\nPilot AI rate: {ai_count}/{len(all_rows)} ({ai_count/max(1,len(all_rows))*100:.1f}%)")


# ── Dry-run cost accounting ─────────────────────────────────────────────

def estimate_cost(client: anthropic.Anthropic, candidates: List[Dict]) -> float:
    groups = [candidates[i:i + BATCH_SIZE] for i in range(0, len(candidates), BATCH_SIZE)]
    n_requests = len(groups)
    if n_requests == 0:
        return 0.0

    # Sample a representative group for token counting (system + user content;
    # output_config doesn't affect input token count).
    sample = groups[0]
    params = build_request_params(sample)
    count = client.messages.count_tokens(
        model=MODEL,
        system=params["system"],
        messages=params["messages"],
    )
    per_request_input = count.input_tokens
    total_input_tokens = per_request_input * n_requests

    # Output: minimal JSON schema, ~12-15 tokens per verdict once compact.
    est_output_per_verdict = 14
    total_output_tokens = est_output_per_verdict * len(candidates)

    input_cost = (total_input_tokens / 1_000_000) * BATCH_INPUT_PER_MTOK
    output_cost = (total_output_tokens / 1_000_000) * BATCH_OUTPUT_PER_MTOK
    total_cost = input_cost + output_cost

    print(f"Candidates: {len(candidates)}  Requests: {n_requests}  (batch_size={BATCH_SIZE})")
    print(f"Per-request input tokens (measured): {per_request_input}")
    print(f"Estimated total input tokens:  {total_input_tokens:,}  -> ${input_cost:.2f}")
    print(f"Estimated total output tokens: {total_output_tokens:,}  -> ${output_cost:.2f}")
    print(f"ESTIMATED TOTAL COST: ${total_cost:.2f}  (Batch API, 50% discount already applied)")
    return total_cost


# ── Submit batch ─────────────────────────────────────────────────────────

def submit_batch(client: anthropic.Anthropic, candidates: List[Dict]) -> str:
    groups = [candidates[i:i + BATCH_SIZE] for i in range(0, len(candidates), BATCH_SIZE)]
    requests = []
    id_mapping: List[List[int]] = []
    for gi, group in enumerate(groups):
        custom_id = f"grp-{gi}"
        params = build_request_params(group)
        requests.append(Request(
            custom_id=custom_id,
            params=MessageCreateParamsNonStreaming(**params),
        ))
        id_mapping.append([r["id"] for r in group])

    print(f"Submitting batch: {len(requests)} requests, {len(candidates)} companies...")
    batch = client.messages.batches.create(requests=requests)
    print(f"Batch created: id={batch.id} status={batch.processing_status}")

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump({"batch_id": batch.id, "id_mapping": id_mapping}, f)
    print(f"State saved to {STATE_PATH} — run --resume to check/apply results")
    return batch.id


# ── Resume / apply results ──────────────────────────────────────────────

def resume_batch(client: anthropic.Anthropic, batch_id: Optional[str], dry_run: bool) -> None:
    if not STATE_PATH.exists() and not batch_id:
        print(f"No state file at {STATE_PATH} and no --batch-id given. Nothing to resume.")
        return
    state = {}
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            state = json.load(f)
    bid = batch_id or state.get("batch_id")
    id_mapping = state.get("id_mapping", [])
    if not bid:
        print("No batch id available.")
        return

    batch = client.messages.batches.retrieve(bid)
    print(f"Batch {bid}: status={batch.processing_status}  counts={batch.request_counts}")
    if batch.processing_status != "ended":
        print("Batch still processing — run --resume again later.")
        return

    mapping_by_custom_id = {f"grp-{i}": ids for i, ids in enumerate(id_mapping)}
    total_requests = 0
    parse_failures = 0
    applied = 0
    ai_count = 0

    updates: List[Tuple[int, bool]] = []
    for result in client.messages.batches.results(bid):
        total_requests += 1
        if result.result.type != "succeeded":
            parse_failures += 1
            continue
        msg = result.result.message
        text_block = next((b.text for b in msg.content if b.type == "text"), None)
        verdicts = parse_response_text(text_block) if text_block else None
        if verdicts is None:
            parse_failures += 1
            continue
        ids = mapping_by_custom_id.get(result.custom_id)
        if ids is None:
            parse_failures += 1
            continue
        by_index = {}
        for v in verdicts:
            try:
                idx = int(v["index"])
                by_index[idx] = bool(v.get("is_ai"))
            except (KeyError, TypeError, ValueError):
                continue
        for i, cid in enumerate(ids):
            if i in by_index:
                updates.append((cid, by_index[i]))
                if by_index[i]:
                    ai_count += 1

    fail_rate = parse_failures / max(1, total_requests) * 100
    print(f"\nRequests: {total_requests}  parse_failures: {parse_failures} ({fail_rate:.2f}%)")
    print(f"Verdicts to apply: {len(updates)}  AI={ai_count}  not-AI={len(updates)-ai_count}")

    if fail_rate >= 1.0:
        print("WARNING: parse-failure rate >= 1% — investigate before trusting results")

    if not dry_run and updates:
        bulk_write_verdicts(updates)
        applied = len(updates)
        print(f"Applied {applied} llm_ai_verified updates to companies table.")
    elif dry_run:
        print("(dry-run — no DB writes)")


# ── Main ──────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="PitchBook AI classifier via Message Batches")
    p.add_argument("--pilot", action="store_true", help="Run 100 candidates as live calls, verify parsing")
    p.add_argument("--dry-run", action="store_true", help="Print cost estimate only, no writes/submission")
    p.add_argument("--submit", action="store_true", help="Write keyword verdicts + submit the LLM batch")
    p.add_argument("--resume", action="store_true", help="Check/apply results of a previously submitted batch")
    p.add_argument("--batch-id", type=str, default=None, help="Override batch id for --resume")
    p.add_argument("--max-cost", type=float, default=DEFAULT_MAX_COST, help="Abort --submit if estimated cost exceeds this")
    p.add_argument("--limit", type=int, default=0, help="Cap candidates scanned (testing)")
    args = p.parse_args()

    if not any([args.pilot, args.dry_run, args.submit, args.resume]):
        p.error("choose one of --pilot / --dry-run / --submit / --resume")

    client = anthropic.Anthropic()

    if args.resume:
        resume_batch(client, args.batch_id, dry_run=False)
        return

    print("Fetching candidates (keyword cascade over verified_pb, not cb_ai_tagged)...")
    keyword_verdicts, llm_candidates = fetch_candidates(limit=args.limit)
    print(f"  keyword-confident: {len(keyword_verdicts)}   ambiguous (needs LLM): {len(llm_candidates)}")

    if args.pilot:
        run_pilot(client, llm_candidates)
        return

    if args.dry_run:
        estimate_cost(client, llm_candidates)
        return

    if args.submit:
        ensure_column()
        apply_keyword_verdicts(keyword_verdicts, dry_run=False)
        cost = estimate_cost(client, llm_candidates)
        if cost > args.max_cost:
            print(f"\nABORT: estimated cost ${cost:.2f} exceeds --max-cost ${args.max_cost:.2f}")
            print("This likely signals a selection bug (too many ambiguous rows). Not submitting.")
            sys.exit(1)
        submit_batch(client, llm_candidates)


if __name__ == "__main__":
    main()
