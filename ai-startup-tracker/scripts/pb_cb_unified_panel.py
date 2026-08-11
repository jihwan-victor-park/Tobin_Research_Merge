"""
Unified PitchBook + Crunchbase AI-identity panel — adds a TRUE pre-ChatGPT (2021)
baseline to the CB story by bridging PitchBook 2021 to Crunchbase on domain.

CB dumps start at 2023 (already post-ChatGPT, Nov 2022), so CB alone cannot tell
"was AI before ChatGPT" from "became AI 2021-2023". PitchBook 2021 is the only
pre-ChatGPT snapshot we have. Bridge: PB Website domain <-> CB domain (no shared
ID exists). ~241K companies overlap.

Definitional consistency: AI is measured the SAME way at every time point — a
keyword test on the DESCRIPTION text (PB 2021 description+keywords; CB 2023 &
2025 organization_descriptions) — so the pre/post-ChatGPT split is not confounded
by PB-keyword-vs-CB-category drift. Restricted to companies present in all three
(domain-matched) so the transitions are real, not coverage.

Question answered: of today's AI companies (2025), what share were ALREADY AI
before ChatGPT (2021) vs converted 2021->2023 vs 2023->2025? Aggregates only.

  python3 scripts/pb_cb_unified_panel.py
"""
from __future__ import annotations

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "pb_longitudinal"
OUT = ROOT / "output"

# consistent keyword-AI on description text at every time point
AIKW = ("(lower(t) LIKE '%artificial intelligence%' OR lower(t) LIKE '%machine learning%' "
        "OR lower(t) LIKE '% ai %' OR lower(t) LIKE '%ai-powered%' OR lower(t) LIKE '%deep learning%' "
        "OR lower(t) LIKE '%neural network%' OR lower(t) LIKE '%generative ai%' "
        "OR lower(t) LIKE '%large language model%' OR lower(t) LIKE '%computer vision%')")


def NORM(col):
    return (f"nullif(split_part(regexp_replace(regexp_replace(lower(trim({col})),"
            f"'^https?://',''),'^www[.]',''),'/',1),'')")


def main() -> None:
    con = duckdb.connect(); con.execute("SET enable_progress_bar=false")

    # 2021 PitchBook: domain -> AI (keyword on description+keywords)
    con.execute(f"""CREATE TABLE y21 AS
        SELECT {NORM('Website')} dom, max(CASE WHEN {AIKW.replace('t','descr')} THEN 1 ELSE 0 END) ai
        FROM (SELECT Website, coalesce(Description,'')||' '||coalesce(Keywords,'') descr
              FROM read_csv('{D}/pb2021_company.dat', delim='|', header=true, quote=chr(7),
                            ignore_errors=true, all_varchar=true))
        WHERE {NORM('Website')} IS NOT NULL GROUP BY 1""")

    # CB vintage: domain (from organizations) -> AI (keyword on description)
    def cb(yr):
        con.execute(f"""CREATE TABLE y{yr} AS
            SELECT {NORM('o.domain')} dom,
                   max(CASE WHEN {AIKW.replace('t','d.description')} THEN 1 ELSE 0 END) ai
            FROM read_parquet('{D}/cb{yr}_organizations.parquet') o
            JOIN read_parquet('{D}/cb{yr}_organization_descriptions.parquet') d ON o.uuid=d.uuid
            WHERE {NORM('o.domain')} IS NOT NULL AND d.description IS NOT NULL GROUP BY 1""")
    cb("2023"); cb("2025")

    # inner-join all three by domain -> real transitions only
    con.execute("""CREATE TABLE panel AS
        SELECT a.dom, a.ai ai21, b.ai ai23, c.ai ai25
        FROM y21 a JOIN y2023 b USING(dom) JOIN y2025 c USING(dom)""")
    n = con.execute("SELECT count(*) FROM panel").fetchone()[0]
    print(f"companies matched across PB2021 + CB2023 + CB2025 (by domain): {n:,}\n")

    # headline: AI-language prevalence over time (same definition each year)
    prev = con.execute("""SELECT
        ROUND(100.0*avg(ai21),1) ai_2021, ROUND(100.0*avg(ai23),1) ai_2023,
        ROUND(100.0*avg(ai25),1) ai_2025 FROM panel""").fetchdf().iloc[0]
    print(f"AI-language prevalence (consistent keyword defn): "
          f"2021 {prev.ai_2021}%  ->  2023 {prev.ai_2023}%  ->  2025 {prev.ai_2025}%")

    # decompose TODAY's AI companies (ai25) by when they first showed AI
    dec = con.execute("""
        SELECT CASE
                 WHEN ai21=1 THEN '0 AI before ChatGPT (already AI in 2021)'
                 WHEN ai23=1 THEN '1 converted 2021->2023'
                 ELSE            '2 converted 2023->2025'
               END AS became_ai_when,
               COUNT(*) companies,
               ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER (),1) pct
        FROM panel WHERE ai25=1 GROUP BY 1 ORDER BY 1""").fetchdf()
    print("\n=== When did 2025's AI companies first show AI language? ===")
    print(dec.to_string(index=False))
    dec.to_csv(OUT / "41_pb_cb_ai_adoption_timing.csv", index=False)

    tot_ai25 = con.execute("SELECT count(*) FROM panel WHERE ai25=1").fetchone()[0]
    pre = con.execute("SELECT count(*) FROM panel WHERE ai25=1 AND ai21=1").fetchone()[0]
    print(f"\nof {tot_ai25:,} companies AI in 2025: {pre:,} ({100*pre/tot_ai25:.0f}%) were already "
          f"AI PRE-ChatGPT (2021); {tot_ai25-pre:,} ({100*(tot_ai25-pre)/tot_ai25:.0f}%) converted after.")

    # transition matrix (full), for the record
    mat = con.execute("""SELECT ai21, ai23, ai25, COUNT(*) n,
        ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER (),2) pct
        FROM panel GROUP BY 1,2,3 ORDER BY 1,2,3""").fetchdf()
    mat.to_csv(OUT / "42_pb_cb_transition_matrix.csv", index=False)
    print("\nsaved -> output/41_pb_cb_ai_adoption_timing.csv, 42_pb_cb_transition_matrix.csv")


if __name__ == "__main__":
    main()
