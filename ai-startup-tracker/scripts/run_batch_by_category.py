"""
Run agentic scrape on all pending sites in selected categories.

Tracks live cost (Anthropic token usage) and writes a JSON summary at the end.

Usage:
  python scripts/run_batch_by_category.py \
      --categories government_program university_incubator discovery_aggregator \
      --max-sites 200

  # Bail out automatically if cost exceeds budget
  python scripts/run_batch_by_category.py --categories government_program --budget 5.00
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── Patch anthropic SDK to count tokens ──────────────────────────────
import anthropic

TOTAL_INPUT_TOKENS = 0
TOTAL_OUTPUT_TOKENS = 0
TOTAL_CALLS = 0


def _wrap_anthropic(client_cls):
    original_init = client_cls.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        original_create = self.messages.create

        def counted_create(*a, **kw):
            global TOTAL_INPUT_TOKENS, TOTAL_OUTPUT_TOKENS, TOTAL_CALLS
            resp = original_create(*a, **kw)
            try:
                u = resp.usage
                TOTAL_INPUT_TOKENS += getattr(u, "input_tokens", 0) or 0
                TOTAL_OUTPUT_TOKENS += getattr(u, "output_tokens", 0) or 0
                TOTAL_CALLS += 1
            except Exception:
                pass
            return resp

        self.messages.create = counted_create

    client_cls.__init__ = patched_init


_wrap_anthropic(anthropic.Anthropic)

from backend.db.connection import session_scope
from backend.db.models import SiteHealth
from backend.orchestrator.orchestrator import Orchestrator

# Claude Haiku 4.5 pricing
INPUT_RATE = 1.0 / 1_000_000
OUTPUT_RATE = 5.0 / 1_000_000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("batch_by_category")
logging.getLogger("backend.agentic.engine").setLevel(logging.WARNING)


def select_sites(categories: List[str], max_sites: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with session_scope() as s:
        rows = (
            s.query(SiteHealth)
            .filter(
                SiteHealth.category.in_(categories),
                SiteHealth.worker_state == "pending",
                SiteHealth.difficulty == "hard",
                SiteHealth.url.isnot(None),
                SiteHealth.url != "",
            )
            .order_by(SiteHealth.category, SiteHealth.id)
            .limit(max_sites)
            .all()
        )
        for r in rows:
            out.append({"id": r.id, "domain": r.domain, "url": r.url, "category": r.category})
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--categories", nargs="+", required=True,
                   help="Categories to scrape (e.g. government_program university_incubator)")
    p.add_argument("--max-sites", type=int, default=500, help="Max sites this run")
    p.add_argument("--budget", type=float, default=None,
                   help="Stop if cost (USD) exceeds this; default: no cap")
    p.add_argument("--report", default=None,
                   help="Path for final JSON report (default: logs/batch_<ts>.json)")
    args = p.parse_args()

    sites = select_sites(args.categories, args.max_sites)
    logger.info(f"Selected {len(sites)} pending sites in categories: {args.categories}")
    if not sites:
        logger.info("Nothing to scrape — exiting.")
        return

    by_cat: Dict[str, int] = {}
    for s in sites:
        by_cat[s["category"]] = by_cat.get(s["category"], 0) + 1
    for c, n in sorted(by_cat.items(), key=lambda x: -x[1]):
        logger.info(f"  {c:24s}: {n}")

    orch = Orchestrator()
    overall_start = time.time()
    per_site: List[Dict[str, Any]] = []
    success_records_total = 0
    new_records_total = 0
    halted_for_budget = False

    for i, site in enumerate(sites, start=1):
        before_in = TOTAL_INPUT_TOKENS
        before_out = TOTAL_OUTPUT_TOKENS
        before_calls = TOTAL_CALLS
        before_t = time.time()

        cum_cost_before = before_in * INPUT_RATE + before_out * OUTPUT_RATE
        logger.info(
            f"\n[{i}/{len(sites)}] {site['category']:22s} {site['url']}"
            f"  (cum ${cum_cost_before:.3f})"
        )

        status = "exception"
        records = 0
        new_c = 0
        err_msg = ""
        try:
            result = orch.run(site["url"], force=True)
            status = result.status
            records = result.records_found or 0
            new_c = result.records_new or 0
            err_msg = result.error_message or ""
        except Exception as e:
            err_msg = str(e)
            logger.error(f"   exception: {e}")

        in_used = TOTAL_INPUT_TOKENS - before_in
        out_used = TOTAL_OUTPUT_TOKENS - before_out
        calls_used = TOTAL_CALLS - before_calls
        cost = in_used * INPUT_RATE + out_used * OUTPUT_RATE
        elapsed = time.time() - before_t

        success_records_total += records
        new_records_total += new_c

        per_site.append({
            "category": site["category"],
            "domain": site["domain"],
            "url": site["url"],
            "status": status,
            "records": records,
            "new": new_c,
            "calls": calls_used,
            "input_tokens": in_used,
            "output_tokens": out_used,
            "cost_usd": round(cost, 4),
            "elapsed_s": round(elapsed, 1),
            "error": err_msg[:200] if err_msg else "",
        })

        cum_cost = TOTAL_INPUT_TOKENS * INPUT_RATE + TOTAL_OUTPUT_TOKENS * OUTPUT_RATE
        logger.info(
            f"   → {status} | {records} rec ({new_c} new) | "
            f"${cost:.4f} | {elapsed:.0f}s | cum ${cum_cost:.2f}"
        )

        if args.budget is not None and cum_cost >= args.budget:
            logger.warning(
                f"BUDGET CAP HIT: ${cum_cost:.2f} >= ${args.budget:.2f}. Stopping after this site."
            )
            halted_for_budget = True
            break

    overall_elapsed = time.time() - overall_start
    overall_cost = TOTAL_INPUT_TOKENS * INPUT_RATE + TOTAL_OUTPUT_TOKENS * OUTPUT_RATE

    # ── Summary by category ────────────────────────────────────────
    cat_stats: Dict[str, Dict[str, Any]] = {}
    for s in per_site:
        c = s["category"]
        cs = cat_stats.setdefault(c, {
            "sites": 0, "successes": 0, "errors": 0,
            "records": 0, "new": 0, "cost_usd": 0.0, "elapsed_s": 0.0,
        })
        cs["sites"] += 1
        if s["status"] == "success":
            cs["successes"] += 1
        else:
            cs["errors"] += 1
        cs["records"] += s["records"]
        cs["new"] += s["new"]
        cs["cost_usd"] += s["cost_usd"]
        cs["elapsed_s"] += s["elapsed_s"]

    logger.info("\n" + "═" * 70)
    logger.info("BATCH SUMMARY")
    logger.info("═" * 70)
    logger.info(f"Categories:        {args.categories}")
    logger.info(f"Sites attempted:   {len(per_site)}{' (halted on budget)' if halted_for_budget else ''}")
    logger.info(f"Total records:     {success_records_total}")
    logger.info(f"Total NEW records: {new_records_total}")
    logger.info(f"Total LLM calls:   {TOTAL_CALLS}")
    logger.info(f"Total cost:        ${overall_cost:.4f}")
    logger.info(f"Avg cost/site:     ${overall_cost / max(len(per_site), 1):.4f}")
    logger.info(f"Total elapsed:     {overall_elapsed:.0f}s ({overall_elapsed/60:.1f} min)")
    logger.info("")
    logger.info("Per-category:")
    logger.info(f"  {'category':24s} {'sites':>5} {'ok':>3} {'err':>4} {'rec':>5} "
                f"{'new':>5} {'cost':>8} {'min':>5}")
    for c, cs in sorted(cat_stats.items()):
        logger.info(
            f"  {c:24s} {cs['sites']:>5d} {cs['successes']:>3d} {cs['errors']:>4d} "
            f"{cs['records']:>5d} {cs['new']:>5d} ${cs['cost_usd']:>6.2f} "
            f"{cs['elapsed_s']/60:>4.1f}"
        )

    # ── Persist JSON ────────────────────────────────────────────────
    report_path = args.report or f"logs/batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as fh:
        json.dump({
            "started_at": datetime.now(timezone.utc).isoformat(),
            "categories": args.categories,
            "sites_attempted": len(per_site),
            "halted_for_budget": halted_for_budget,
            "total_cost_usd": round(overall_cost, 4),
            "total_input_tokens": TOTAL_INPUT_TOKENS,
            "total_output_tokens": TOTAL_OUTPUT_TOKENS,
            "total_llm_calls": TOTAL_CALLS,
            "elapsed_s": round(overall_elapsed, 1),
            "total_records": success_records_total,
            "total_new_records": new_records_total,
            "per_category": cat_stats,
            "per_site": per_site,
        }, fh, indent=2, default=str)
    logger.info(f"\nReport saved: {report_path}")


if __name__ == "__main__":
    main()
