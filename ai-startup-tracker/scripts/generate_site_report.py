#!/usr/bin/env python3
"""
Generate a single human-readable TXT report listing every source we track,
split into WORKING vs NOT-WORKING groups, with grouped failure reasons.
URL paths are intentionally omitted — only domain + category + signal.

Output: ai-startup-tracker/reports/site_status.txt
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text  # noqa: E402

from backend.db.connection import get_engine  # noqa: E402

OUT_DIR = PROJECT_ROOT / "reports"
OUT_DIR.mkdir(exist_ok=True)
OUT_FILE = OUT_DIR / "site_status.txt"

CATEGORY_ORDER = [
    "discovery_aggregator",
    "accelerator",
    "vc_portfolio",
    "university_incubator",
    "government_program",
    "other",
]


def _err_bucket(err: str | None) -> str:
    """Map a raw error string to a short, human-readable bucket label."""
    if not err:
        return "untried (never run)"
    e = err.lower()
    if "credit balance is too low" in e or "insufficient" in e:
        return "blocked: Anthropic credits exhausted"
    if "tavily" in e and "400" in e:
        return "blocked: Tavily extract 400"
    if "login" in e or "authentication" in e or "unauthorized" in e or "401" in e:
        return "blocked: login / auth required"
    if "captcha" in e or "cloudflare" in e:
        return "blocked: bot protection"
    if "no_portfolio_page" in e or "404" in e or "not found" in e:
        return "page not found / no portfolio listing"
    if "timeout" in e or "timed out" in e:
        return "timeout / slow page"
    if "javascript" in e or "rendered" in e or "spa" in e:
        return "JS-rendered (needs browser)"
    if "json" in e and "parse" in e:
        return "LLM JSON parse failure"
    return f"other: {err[:80]}"


def main() -> None:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(
            """
            SELECT
                domain,
                category,
                worker_state,
                status,
                difficulty,
                last_record_count,
                total_runs,
                total_successes,
                last_success_at,
                last_failure_at,
                pending_reason,
                last_error
            FROM site_health
            ORDER BY worker_state DESC, category NULLS LAST, last_record_count DESC NULLS LAST, domain
            """
        )).mappings().all()

    working = [r for r in rows if r["worker_state"] == "working"]
    pending = [r for r in rows if r["worker_state"] != "working"]

    total = len(rows)
    work_count = len(working)
    pend_count = len(pending)
    work_records = sum(r["last_record_count"] or 0 for r in working)

    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("  AI Startup Tracker — Site Inventory Status")
    lines.append("  Generated: " + datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
    lines.append("=" * 78)
    lines.append("")
    lines.append(f"  Total sources tracked         : {total:,}")
    lines.append(f"  WORKING (producing data)      : {work_count:,}  "
                 f"-> {work_records:,} startup rows pulled across them")
    lines.append(f"  NOT WORKING / pending         : {pend_count:,}")
    lines.append("")
    lines.append("  NOTE: URLs are omitted on purpose — only the domain identity, the")
    lines.append("        category bucket, and the signal that matters per row.")
    lines.append("")

    # ── WORKING ──────────────────────────────────────────────────────────
    lines.append("=" * 78)
    lines.append(f"  WORKING SITES — {work_count} total")
    lines.append("=" * 78)
    by_cat: dict[str, list] = {}
    for r in working:
        c = r["category"] or "other"
        by_cat.setdefault(c, []).append(r)

    for cat in CATEGORY_ORDER + sorted(set(by_cat) - set(CATEGORY_ORDER)):
        rows_cat = by_cat.get(cat, [])
        if not rows_cat:
            continue
        lines.append("")
        lines.append(f"  [{cat}]  ({len(rows_cat)} sites)")
        lines.append("  " + "-" * 74)
        for r in rows_cat:
            domain = (r["domain"] or "").ljust(38)
            n = r["last_record_count"] or 0
            runs = r["total_runs"] or 0
            ok = r["total_successes"] or 0
            tier = (r["difficulty"] or "?")[:4]
            lines.append(f"    {domain}  {n:>6,} rows   runs={runs:>3} ok={ok:>3} ({tier})")

    # ── NOT WORKING ──────────────────────────────────────────────────────
    lines.append("")
    lines.append("=" * 78)
    lines.append(f"  NOT WORKING SITES — {pend_count} total")
    lines.append("=" * 78)
    lines.append("")
    lines.append("  Grouped by failure reason (most common first).")
    lines.append("  These sites are registered but currently produce 0 rows.")
    lines.append("")

    by_bucket: dict[str, list] = {}
    for r in pending:
        bucket = _err_bucket(r.get("last_error") or r.get("pending_reason"))
        by_bucket.setdefault(bucket, []).append(r)

    for bucket in sorted(by_bucket, key=lambda b: -len(by_bucket[b])):
        rows_b = by_bucket[bucket]
        lines.append("")
        lines.append(f"  >> {bucket}  ({len(rows_b)} sites)")
        lines.append("  " + "-" * 74)
        # Sub-group by category so it's still readable.
        sub: dict[str, list[str]] = {}
        for r in rows_b:
            c = r["category"] or "other"
            sub.setdefault(c, []).append(r["domain"] or "(unknown)")
        for c in CATEGORY_ORDER + sorted(set(sub) - set(CATEGORY_ORDER)):
            doms = sub.get(c, [])
            if not doms:
                continue
            lines.append(f"    [{c}]")
            # Print 3 per line for compactness
            for i in range(0, len(doms), 3):
                chunk = doms[i:i + 3]
                lines.append("      " + "   ".join(d.ljust(32) for d in chunk).rstrip())

    lines.append("")
    lines.append("=" * 78)
    lines.append("  How to read this:")
    lines.append("    - 'untried (never run)'        => domain seeded but orchestrator hasn't")
    lines.append("                                     visited it yet. Just needs a run.")
    lines.append("    - 'blocked: Anthropic credits' => agentic engine attempt died because")
    lines.append("                                     Claude API had no balance. Top up + retry.")
    lines.append("    - 'JS-rendered'                => needs Playwright path; agentic engine")
    lines.append("                                     can do it but only with credit.")
    lines.append("    - 'login / auth required'      => structurally inaccessible without an")
    lines.append("                                     account or paid API. Consider replacing")
    lines.append("                                     with the bulk-export path (PitchBook/CB).")
    lines.append("=" * 78)

    OUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_FILE}  ({OUT_FILE.stat().st_size:,} bytes, {total} sites)")


if __name__ == "__main__":
    main()
