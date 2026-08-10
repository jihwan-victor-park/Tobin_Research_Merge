"""
PitchBook longitudinal AI-repackaging: 2021 -> 2025 panel.

Joins the 2021 PitchBook Company.dat and the 2025 PitchBook company parquets on
CompanyID (same ID system -> exact join, no fuzzy matching), finds companies
that ADDED AI language to their description over the 4 years, and runs the
validated diff-classifier (scripts/ai_repackaging.py) on a sample to sort them:
repackaged_to_ai / added_ai_feature / ai_washing.

Data (git-ignored, under data/pb_longitudinal/, pulled from the shared Dropbox):
  pb2021_company.dat                    (pipe-delimited, CompanyID|...|Description|Keywords|...)
  pitchbook_{vc,pe,other}_glob_company.parquet   (2025, same columns)

    python scripts/pb_longitudinal_repackaging.py --panel-only    # free keyword transition matrix
    python scripts/pb_longitudinal_repackaging.py --classify 150  # LLM-classify a sample (~$0.20)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.ai_repackaging import classify_change, CLASSES

DATA = ROOT / "data" / "pb_longitudinal"
PB2021 = str(DATA / "pb2021_company.dat")
PB2025 = [str(DATA / f"pitchbook_{seg}_glob_company.parquet") for seg in ("vc", "pe", "other")]

_AI = ("(lower(x) LIKE '%artificial intelligence%' OR lower(x) LIKE '%machine learning%' "
       "OR lower(x) LIKE '% ai %' OR lower(x) LIKE '%ai-%' OR lower(x) LIKE '%deep learning%' "
       "OR lower(x) LIKE '%neural network%' OR lower(x) LIKE '%generative ai%' "
       "OR lower(x) LIKE '%large language model%' OR lower(x) LIKE '%llm%')")


def _con():
    con = duckdb.connect()
    con.execute(f"""CREATE VIEW y21 AS SELECT CAST(CompanyID AS VARCHAR) id, CompanyName AS cname,
        coalesce(Description,'') descr, coalesce(Description,'')||' '||coalesce(Keywords,'') x
        FROM read_csv('{PB2021}', delim='|', header=true, quote=chr(7), ignore_errors=true, all_varchar=true)""")
    con.execute(f"""CREATE VIEW y25 AS SELECT CAST(CompanyID AS VARCHAR) id,
        coalesce(Description,'') descr, coalesce(Description,'')||' '||coalesce(Keywords,'') x
        FROM read_parquet({PB2025})""")
    return con


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel-only", action="store_true")
    ap.add_argument("--classify", type=int, default=0, help="classify N 'added-AI' companies")
    a = ap.parse_args()
    con = _con()

    con.execute(f"""CREATE TABLE p AS
        SELECT a.id, a.cname, a.descr d21, b.descr d25,
               {_AI.replace('x','a.x')} ai21, {_AI.replace('x','b.x')} ai25
        FROM y21 a JOIN y25 b USING(id)""")
    r = con.execute("""SELECT COUNT(*) n_both, COUNT(*) FILTER (WHERE ai21) ai21,
        COUNT(*) FILTER (WHERE ai25) ai25, COUNT(*) FILTER (WHERE NOT ai21 AND ai25) added,
        COUNT(*) FILTER (WHERE ai21 AND ai25) stayed, COUNT(*) FILTER (WHERE ai21 AND NOT ai25) dropped
        FROM p""").fetchdf().iloc[0]
    tot = int(r["n_both"])
    print(f"Panel (2021->2025, matched CompanyID): {tot:,} companies")
    print(f"  AI language: 2021 {100*r['ai21']/tot:.1f}%  ->  2025 {100*r['ai25']/tot:.1f}%")
    print(f"  added AI: {int(r['added']):,} | stayed AI: {int(r['stayed']):,} | dropped AI: {int(r['dropped']):,}")

    if a.panel_only or not a.classify:
        return

    sample = con.execute("""SELECT cname, d21, d25 FROM p
        WHERE NOT ai21 AND ai25 AND length(d21)>40 AND length(d25)>40
        ORDER BY random() LIMIT ?""", [a.classify]).fetchall()
    print(f"\nClassifying {len(sample)} 'added-AI' companies (real 2021 vs 2025 descriptions)...")
    from collections import Counter
    c = Counter(); shown = 0
    for name, d21, d25 in sample:
        res = classify_change(name, d21, d25)
        if not res:
            c["PARSE_FAIL"] += 1; continue
        c[res["change"]] += 1
        if shown < 8 and res["change"] in ("repackaged_to_ai", "ai_washing"):
            print(f"  [{res['change']:16s}] {name[:26]:26s} {res.get('why','')[:50]}")
            shown += 1
    print("\nRepackaging breakdown of the 'added-AI' pool:")
    for cls in CLASSES + ["PARSE_FAIL"]:
        if c.get(cls):
            print(f"  {cls:18s}: {c[cls]:>3}  ({100*c[cls]/len(sample):.0f}%)")


if __name__ == "__main__":
    main()
