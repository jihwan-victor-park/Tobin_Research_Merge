"""
Genuine pivot vs AI-washing — LLM-classify the CB companies that adopted an AI
identity, using their REAL 2023 vs 2026 Crunchbase descriptions.

The identity panel found ~22% of AI-2026 companies present since 2023 were
NON-AI in 2023 and later category-tagged AI ("repackaged"). This script asks the
sharper question: of those, how many GENUINELY became AI vs just added AI to the
marketing? It runs the validated diff-classifier (scripts/ai_repackaging.py) on
each company's 2023 -> 2026 description pair.

Repackager set = uuid AI-tagged in cb2026 AND present-but-NOT-AI in cb2023, with
substantial descriptions in both years. Aggregates only; per-company verdicts are
written locally (no company names committed beyond the aggregate + a sample).

  python3 scripts/classify_repackagers_cb.py --limit 25    # pilot
  python3 scripts/classify_repackagers_cb.py --limit 500   # full sample
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.ai_repackaging import classify_change, CLASSES

D = ROOT / "data" / "pb_longitudinal"
OUT = ROOT / "output"

AICAT = ("(lower(category_list) LIKE '%artificial intelligence%' "
         "OR lower(category_list) LIKE '%machine learning%' "
         "OR lower(category_list) LIKE '%generative%' "
         "OR lower(category_list) LIKE '%natural language%' "
         "OR lower(category_list) LIKE '%computer vision%' "
         "OR lower(category_list) LIKE '%deep learning%' "
         "OR lower(category_list) LIKE '%neural network%' "
         "OR lower(category_groups_list) LIKE '%artificial intelligence%')")


def repackagers(limit: int):
    con = duckdb.connect(); con.execute("SET enable_progress_bar=false")
    con.execute("SELECT setseed(0.7)")
    return con.execute(f"""
        SELECT d23.name, d23.description AS desc23, d26.description AS desc26
        FROM (SELECT uuid FROM read_parquet('{D}/cb2026_organizations.parquet') WHERE {AICAT}) a26
        JOIN (SELECT uuid FROM read_parquet('{D}/cb2023_organizations.parquet') WHERE NOT {AICAT}) a23 USING(uuid)
        JOIN read_parquet('{D}/cb2023_organization_descriptions.parquet') d23 USING(uuid)
        JOIN read_parquet('{D}/cb2026_organization_descriptions.parquet') d26 USING(uuid)
        WHERE length(d23.description) > 60 AND length(d26.description) > 60
        ORDER BY random() LIMIT {limit}
    """).fetchall()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    rows = repackagers(a.limit)
    print(f"classifying {len(rows)} CB repackagers (2023 non-AI -> 2026 AI) via their real descriptions...")

    c = Counter(); done = 0; out_rows = []

    def work(row):
        name, d23, d26 = row
        return name, classify_change(name, d23, d26)

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(work, r) for r in rows]
        for f in as_completed(futs):
            name, res = f.result()
            cls = "PARSE_FAIL" if not res else res["change"]
            c[cls] += 1; done += 1
            out_rows.append({"company": name, "change": cls,
                             "confidence": (res or {}).get("confidence", ""),
                             "why": (res or {}).get("why", "")})
            if done % 50 == 0:
                print(f"  {done}/{len(rows)}  {dict(c)}", flush=True)

    OUT.mkdir(exist_ok=True)
    with open(OUT / "39_cb_repackager_verdicts_sample.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["company", "change", "confidence", "why"])
        w.writeheader(); w.writerows(out_rows)
    usable = sum(c[k] for k in CLASSES)
    with open(OUT / "40_cb_repackager_summary.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["class", "count", "pct_of_classified"])
        for cls in CLASSES + ["PARSE_FAIL"]:
            if c.get(cls):
                w.writerow([cls, c[cls], round(100*c[cls]/max(usable, 1), 1) if cls in CLASSES else ""])

    print(f"\n=== Repackager verdicts (n={len(rows)}, {usable} classified) ===")
    for cls in CLASSES + ["PARSE_FAIL"]:
        if c.get(cls):
            pct = f"{100*c[cls]/usable:.0f}%" if cls in CLASSES and usable else ""
            print(f"  {cls:18s}: {c[cls]:>4}  {pct}")
    genuine = c.get("repackaged_to_ai", 0) + c.get("added_ai_feature", 0)
    if usable:
        print(f"\n  genuine (repackaged_to_ai + added_ai_feature): {genuine} ({100*genuine/usable:.0f}%)")
        print(f"  ai_washing: {c.get('ai_washing',0)} ({100*c.get('ai_washing',0)/usable:.0f}%)")
    print("saved -> output/39_cb_repackager_verdicts_sample.csv, 40_cb_repackager_summary.csv")


if __name__ == "__main__":
    main()
