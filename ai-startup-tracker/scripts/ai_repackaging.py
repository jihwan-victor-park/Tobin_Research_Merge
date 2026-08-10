"""
AI-repackaging longitudinal classifier — the core of the "how many companies
changed their business model because of AI?" study.

Takes a company's description at two time points (2021 "before" and current
"now") and classifies the change:

  born_ai            AI was core in 2021 already
  repackaged_to_ai   non-AI in 2021, AI-core now  <-- the headline metric
  added_ai_feature   core unchanged, AI bolted on as a feature
  ai_washing         "AI" added to the pitch but no substantive product change
  no_ai_change       no AI in either snapshot

Design:
  - The "now" description comes from the Railway DB (companies.description).
  - The "2021" description comes from the PitchBook 2021 snapshot (Dropbox).
    The loader for that file is a TODO until the 2021 schema is confirmed; the
    classifier itself is schema-agnostic (two strings in, verdict out).
  - Triangulation hook: pass ai_hiring_2022plus (from Revelio positions) to
    strengthen the ai_washing vs genuine-pivot call.

Run the self-test (no DB, ~5 LLM calls) to validate the method:
    python scripts/ai_repackaging.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.enrich_companies_with_ai import _call_llm, _parse_json  # reuse LLM transport

CLASSES = ["born_ai", "repackaged_to_ai", "added_ai_feature", "ai_washing", "no_ai_change"]


def classify_change(name: str, desc_2021: str, desc_now: str,
                    ai_hiring_signal: str | None = None) -> dict | None:
    """LLM-classify the 2021->now change for one company. Schema-agnostic."""
    hint = ""
    if ai_hiring_signal:
        hint = (f"\nExternal signal (independent of the text): {ai_hiring_signal}. "
                "Use it to distinguish a genuine pivot (real AI capability) from "
                "ai_washing (marketing only).")
    prompt = (
        f"Company: {name!r}. Compare how it described itself in 2021 vs now.\n\n"
        f"2021 description:\n{(desc_2021 or '(none)')[:1200]}\n\n"
        f"Current description:\n{(desc_now or '(none)')[:1200]}\n"
        f"{hint}\n\n"
        "STEP 1 — decide two booleans:\n"
        "  ai_2021: was AI/ML core to the product in the 2021 description?\n"
        "  ai_now:  is AI/ML core to the product in the current description?\n"
        "STEP 2 — pick the change class implied by those booleans:\n"
        "  born_ai          - ai_2021=true  (AI core already in 2021; still AI now)\n"
        "  repackaged_to_ai - ai_2021=false, ai_now=true, AND the core offering itself changed to be AI-driven (a real pivot)\n"
        "  added_ai_feature - ai_2021=false, ai_now=true, but the core business is the same with AI added as a feature\n"
        "  ai_washing       - ai_2021=false and the pitch now name-drops 'AI' but the actual product/offering looks UNCHANGED (marketing only)\n"
        "  no_ai_change     - ai_2021=false, ai_now=false (no AI in either)\n\n"
        "IMPORTANT: from text alone, repackaged_to_ai and ai_washing look similar. "
        "Only choose ai_washing if an external signal above indicates no real AI capability; "
        "otherwise prefer repackaged_to_ai / added_ai_feature.\n\n"
        "Return ONLY compact JSON: {\"change\": <one of the above>, "
        "\"ai_2021\": true|false, \"ai_now\": true|false, "
        "\"confidence\": 0.0-1.0, \"why\": \"<=15 words\"}"
    )
    data = _parse_json(_call_llm([{"role": "user", "content": prompt}], temperature=0.0) or "")
    if not data or data.get("change") not in CLASSES:
        return None
    return data


# ── self-test: synthetic before/after pairs, one per class ───────────────
_CASES = [
    ("Aidyn Labs",
     "Aidyn builds a machine-learning platform for real-time fraud detection using deep neural networks.",
     "Aidyn is an AI platform for real-time fraud detection powered by deep learning.",
     "born_ai"),
    ("DataForge",
     "DataForge provides ETL data-pipeline tooling and dashboards for analysts.",
     "DataForge is an AI-native data platform with autonomous LLM agents that build and run your pipelines.",
     "repackaged_to_ai"),
    ("ShopFlow",
     "ShopFlow is an e-commerce checkout and inventory SaaS for small retailers.",
     "ShopFlow is an e-commerce checkout and inventory SaaS, now with an AI product-recommendation add-on.",
     "added_ai_feature"),
    ("Consulting Co",
     "Consulting Co offers IT staffing and managed services for mid-market firms.",
     "Consulting Co is an AI-powered, AI-first IT services leader delivering AI transformation.",
     "ai_washing"),
    ("BrickMortar",
     "BrickMortar is a commercial real-estate brokerage serving the Midwest.",
     "BrickMortar is a commercial real-estate brokerage serving the Midwest.",
     "no_ai_change"),
]


def self_test() -> None:
    print("AI-repackaging classifier self-test (synthetic pairs):\n")
    ok = 0
    for name, d21, dnow, expected in _CASES:
        res = classify_change(name, d21, dnow)
        got = res.get("change") if res else "PARSE_FAIL"
        mark = "OK " if got == expected else "MISS"
        if got == expected:
            ok += 1
        print(f"  [{mark}] {name:14s} expected={expected:18s} got={got:18s} "
              f"({res.get('why','') if res else ''})")
    print(f"\n{ok}/{len(_CASES)} correct on text alone.")

    # Triangulation demo: the same 'Consulting Co' case, now WITH a hiring signal.
    print("\nTriangulation demo (same washing case + external hiring signal):")
    for signal, exp in [("this company hired 0 AI/ML engineers 2022-2025", "ai_washing"),
                        ("this company hired 40+ ML engineers since 2023", "repackaged_to_ai")]:
        res = classify_change("Consulting Co",
                              "Consulting Co offers IT staffing and managed services for mid-market firms.",
                              "Consulting Co is an AI-powered, AI-first IT services leader delivering AI transformation.",
                              ai_hiring_signal=signal)
        got = res.get("change") if res else "PARSE_FAIL"
        print(f"  signal={signal[:45]:45s} -> {got}  (expect ~{exp})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        self_test()
    else:
        print("2021 loader TODO — provide the PitchBook 2021 snapshot; then this "
              "runs classify_change over the CB/PB panel. Use --self-test to validate the method now.")


if __name__ == "__main__":
    main()
