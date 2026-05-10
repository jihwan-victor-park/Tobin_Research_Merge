"""Print a markdown morning report summarising overnight scrape activity."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db.connection import session_scope
from backend.db.models import Company, IncubatorSignal, IncubatorSource

LOGDIR = Path(__file__).resolve().parent.parent / "logs"
P1_REPORT = LOGDIR / "batch_high_roi.json"
P2_REPORT = LOGDIR / "batch_phase2.json"


def _load(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as e:
        print(f"<!-- failed to load {path}: {e} -->")
        return None


def _section_phase(label: str, data: dict | None) -> str:
    if not data:
        return f"## {label}\n\n_(no report — phase did not run or was skipped)_\n"
    lines = [f"## {label}"]
    lines.append("")
    lines.append(f"- Sites attempted: **{data.get('sites_attempted', 0)}**")
    lines.append(f"- Total cost: **${data.get('total_cost_usd', 0):.2f}**")
    lines.append(f"- LLM calls: {data.get('total_llm_calls', 0):,}")
    lines.append(f"- Elapsed: {data.get('elapsed_s', 0)/60:.1f} min")
    lines.append(f"- Records found: {data.get('total_records', 0):,}")
    lines.append(f"- **NEW records: {data.get('total_new_records', 0):,}**")
    if data.get("halted_for_budget"):
        lines.append("- ⚠️ Halted on budget cap")
    lines.append("")

    # Per-category table
    per_cat = data.get("per_category", {})
    if per_cat:
        lines.append("| Category | Sites | OK | Err | Records | New | Cost |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for cat, cs in sorted(per_cat.items()):
            lines.append(
                f"| {cat} | {cs['sites']} | {cs['successes']} | {cs['errors']} | "
                f"{cs['records']} | **{cs['new']}** | ${cs['cost_usd']:.2f} |"
            )
        lines.append("")

    # Top 10 productive sites
    sites = data.get("per_site", []) or []
    sites_sorted = sorted(sites, key=lambda s: s.get("new", 0), reverse=True)[:10]
    if sites_sorted:
        lines.append("**Top sites by NEW records:**")
        lines.append("")
        for s in sites_sorted:
            if s.get("new", 0) <= 0:
                break
            lines.append(
                f"- **{s.get('new', 0)} new** / {s.get('records', 0)} found "
                f"— `{s.get('domain', '')}` (${s.get('cost_usd', 0):.3f}, "
                f"{s.get('elapsed_s', 0):.0f}s)"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    p1 = _load(P1_REPORT)
    p2 = _load(P2_REPORT)

    total_cost = (p1 or {}).get("total_cost_usd", 0) + (p2 or {}).get("total_cost_usd", 0)
    total_new = (p1 or {}).get("total_new_records", 0) + (p2 or {}).get("total_new_records", 0)
    total_records = (p1 or {}).get("total_records", 0) + (p2 or {}).get("total_records", 0)
    total_sites = (p1 or {}).get("sites_attempted", 0) + (p2 or {}).get("sites_attempted", 0)

    # Pull current DB stats
    with session_scope() as s:
        total_companies = s.query(Company).count()
        ai_companies = s.query(Company).filter(Company.ai_score >= 0.6).count()
        agentic_signals = s.query(IncubatorSignal).filter(
            IncubatorSignal.source == IncubatorSource.agentic_scrape
        ).count()

    print("# Morning Report — overnight scrape\n")
    print(f"**Total spend: ${total_cost:.2f} / $9.00 budget**")
    print(f"**Sites attempted: {total_sites}** | "
          f"Records: {total_records:,} | **New: {total_new:,}**")
    print(f"**DB now: {total_companies:,} companies | {ai_companies:,} AI** "
          f"({agentic_signals:,} agentic-scrape signals total)\n")

    print("---\n")
    print(_section_phase("Phase 1 — government + university + aggregator", p1))
    print("---\n")
    print(_section_phase("Phase 2 — accelerator + vc", p2))


if __name__ == "__main__":
    main()
