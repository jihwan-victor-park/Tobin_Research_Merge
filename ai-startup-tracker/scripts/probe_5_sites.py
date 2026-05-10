"""
Probe 5 pending hard sites (one per category mix) and measure cost+yield.

Picks sites we haven't yet scraped in last 7 days, samples diversely:
  - 1 vc_portfolio (Tier-1 React)
  - 1 accelerator
  - 1 university_incubator (often static HTML, easier)
  - 1 government_program
  - 1 from any remaining category

Wraps the Anthropic client with a token counter so we can compute the
actual $ cost from real usage, not estimates.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── Patch anthropic client BEFORE engine import ─────────────────────
import anthropic

_orig_create = anthropic.Anthropic.messages.fget(anthropic.Anthropic) if hasattr(anthropic.Anthropic.messages, "fget") else None

# Token counters
TOTAL_INPUT_TOKENS = 0
TOTAL_OUTPUT_TOKENS = 0
TOTAL_CALLS = 0


def _wrap_messages_create(client_cls):
    """Monkey-patch the SDK's messages.create to record usage."""
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


_wrap_messages_create(anthropic.Anthropic)

# ── Now import engine ────────────────────────────────────────────────
from backend.db.connection import session_scope
from backend.db.models import SiteHealth
from backend.orchestrator.orchestrator import Orchestrator


# Claude Haiku 4.5 pricing (as of late-2025): $1 / 1M input, $5 / 1M output
INPUT_RATE = 1.0 / 1_000_000
OUTPUT_RATE = 5.0 / 1_000_000


def pick_probes() -> list[tuple[str, str, str]]:
    """Pick (domain, url, category) — at most 1 per category, 5 total."""
    wanted = [
        "university_incubator",
        "vc_portfolio",
        "accelerator",
        "government_program",
        "vc_portfolio",  # second VC for variance
    ]
    picks: list[tuple[str, str, str]] = []
    used_domains: set[str] = set()

    with session_scope() as s:
        for cat in wanted:
            row = (
                s.query(SiteHealth)
                .filter(
                    SiteHealth.worker_state == "pending",
                    SiteHealth.difficulty == "hard",
                    SiteHealth.category == cat,
                    ~SiteHealth.domain.in_(used_domains) if used_domains else True,
                )
                .order_by(SiteHealth.id)
                .first()
            )
            if row:
                picks.append((row.domain, row.url, row.category))
                used_domains.add(row.domain)

    return picks


def main() -> None:
    global TOTAL_INPUT_TOKENS, TOTAL_OUTPUT_TOKENS, TOTAL_CALLS

    probes = pick_probes()
    print(f"\n=== Probing {len(probes)} sites ===\n")
    for d, u, c in probes:
        print(f"  [{c:22s}] {u}")
    print()

    orch = Orchestrator()
    per_site_stats = []

    overall_start = time.time()
    for domain, url, category in probes:
        before_in = TOTAL_INPUT_TOKENS
        before_out = TOTAL_OUTPUT_TOKENS
        before_calls = TOTAL_CALLS
        before_t = time.time()

        print(f"\n────────── [{category}] {url}")
        try:
            result = orch.run(url, force=True)
            status = result.status
            records = result.records_found or 0
            new_c = result.records_new or 0
        except Exception as e:
            status = "exception"
            records = 0
            new_c = 0
            print(f"    EXCEPTION: {e}")

        in_used = TOTAL_INPUT_TOKENS - before_in
        out_used = TOTAL_OUTPUT_TOKENS - before_out
        calls_used = TOTAL_CALLS - before_calls
        cost = in_used * INPUT_RATE + out_used * OUTPUT_RATE
        elapsed = time.time() - before_t

        per_site_stats.append({
            "category": category,
            "url": url,
            "status": status,
            "records": records,
            "new": new_c,
            "calls": calls_used,
            "input_tokens": in_used,
            "output_tokens": out_used,
            "cost_usd": cost,
            "elapsed_s": elapsed,
        })
        print(f"    → {status}: {records} records, {new_c} new")
        print(f"    Tokens: {in_used:,} in / {out_used:,} out  ({calls_used} LLM calls)")
        print(f"    Cost: ${cost:.4f}   Elapsed: {elapsed:.1f}s")

    overall_elapsed = time.time() - overall_start
    overall_cost = TOTAL_INPUT_TOKENS * INPUT_RATE + TOTAL_OUTPUT_TOKENS * OUTPUT_RATE

    print("\n" + "═" * 70)
    print("SUMMARY")
    print("═" * 70)
    print(f"Sites probed:       {len(probes)}")
    print(f"Total LLM calls:    {TOTAL_CALLS}")
    print(f"Total input tokens: {TOTAL_INPUT_TOKENS:,}")
    print(f"Total output tokens:{TOTAL_OUTPUT_TOKENS:,}")
    print(f"Total cost:         ${overall_cost:.4f}")
    print(f"Avg cost/site:      ${overall_cost / max(len(probes), 1):.4f}")
    print(f"Total elapsed:      {overall_elapsed:.1f}s ({overall_elapsed/60:.1f} min)")
    print()
    print("Extrapolation to 434 remaining pending hard sites:")
    avg_cost = overall_cost / max(len(probes), 1)
    print(f"  Estimated total cost: ${avg_cost * 434:.2f}")
    print(f"  Estimated time:       {(overall_elapsed/max(len(probes),1)) * 434 / 60:.0f} min")
    print()

    print("Per-site detail:")
    print(f"  {'category':22s} {'status':12s} {'rec':>4} {'new':>4} {'$':>8} {'sec':>6}")
    for s in per_site_stats:
        print(f"  {s['category']:22s} {s['status']:12s} {s['records']:>4} {s['new']:>4} "
              f"${s['cost_usd']:>7.4f} {s['elapsed_s']:>5.0f}s")


if __name__ == "__main__":
    main()
