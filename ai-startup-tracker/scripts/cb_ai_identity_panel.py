"""
CB AI-IDENTITY panel — for AI companies, WHEN did they become AI, and what were
they before? Uses the Crunchbase 2023 / 2024 / 2025 dumps as a 3-point panel
joined on the stable org uuid (98% of 2023 orgs persist to 2025).

Focus: the AI population and how its identity changed over time (not AI-vs-non-AI).
AI identity = CB's own category taxonomy (category_list / category_groups_list).
For each org we know is_ai in 2023, 2024, 2025, so we can DATE when the AI
identity was adopted and decompose the growth of "AI companies" into:

  born/persistent  AI-tagged already in the 2023 dump (adopted <= 2023)
  repackaged       in CB in 2023 as NON-AI, AI-tagged by 2024 or 2025
  new-to-CB        not in the 2023 dump at all (formed / added later)

Outputs (aggregates only):
  34_cb_ai_identity_timing.csv       when AI-2025 companies became AI
  35_cb_ai_repackaged_origins.csv    top prior (2023) categories of repackagers
  36_cb_ai_identity_by_cohort.csv    repackaged vs born AI by founding cohort

    python3 scripts/cb_ai_identity_panel.py
"""
from __future__ import annotations

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
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


def _view(con, yr):
    con.execute(f"""CREATE TABLE y{yr} AS SELECT uuid, {AICAT} AS is_ai,
        category_list AS cats,
        TRY_CAST(EXTRACT(year FROM TRY_CAST(founded_on AS DATE)) AS INT) AS fy
        FROM read_parquet('{D}/cb{yr}_organizations.parquet')""")


def main() -> None:
    con = duckdb.connect(); con.execute("SET enable_progress_bar=false")
    for yr in ("2023", "2024", "2025"):
        _view(con, yr)

    # panel keyed on 2025 AI companies, with their 2023/2024 identity
    con.execute("""CREATE TABLE panel AS
        SELECT a.uuid, a.fy,
               a.is_ai AS ai25, b.is_ai AS ai24, c.is_ai AS ai23,
               (c.uuid IS NOT NULL) AS in23, (b.uuid IS NOT NULL) AS in24,
               c.cats AS cats23
        FROM y2025 a
        LEFT JOIN y2024 b ON a.uuid=b.uuid
        LEFT JOIN y2023 c ON a.uuid=c.uuid
        WHERE a.is_ai""")
    n = con.execute("SELECT count(*) FROM panel").fetchone()[0]
    print(f"AI companies in CB 2025 (category taxonomy): {n:,}\n")

    # 1. identity timing / decomposition ----------------------------------
    timing = con.execute("""
        SELECT
          CASE
            WHEN NOT in23 AND NOT in24 THEN '3 new to CB in 2025'
            WHEN NOT in23 AND in24     THEN '2 new to CB in 2024'
            WHEN in23 AND ai23         THEN '0 AI already in 2023 (<=2023)'
            WHEN in23 AND NOT ai23 AND COALESCE(ai24,false)     THEN '1a repackaged: added AI by 2024'
            WHEN in23 AND NOT ai23 AND NOT COALESCE(ai24,false) THEN '1b repackaged: added AI in 2025'
          END AS ai_identity_origin,
          COUNT(*) companies,
          ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER (),1) pct
        FROM panel GROUP BY 1 ORDER BY 1""").fetchdf()
    print("=== When did 2025's AI companies acquire their AI identity? ===")
    print(timing.to_string(index=False))
    timing.to_csv(OUT / "34_cb_ai_identity_timing.csv", index=False)

    # headline repackaging rate among companies present since 2023
    hl = con.execute("""
        SELECT
          COUNT(*) FILTER (WHERE in23) present_since_2023,
          COUNT(*) FILTER (WHERE in23 AND ai23) already_ai_2023,
          COUNT(*) FILTER (WHERE in23 AND NOT ai23) repackaged_to_ai,
          ROUND(100.0*COUNT(*) FILTER (WHERE in23 AND NOT ai23)
                /NULLIF(COUNT(*) FILTER (WHERE in23),0),1) repackaged_pct
        FROM panel""").fetchdf().iloc[0]
    print(f"\nOf AI-2025 companies present in CB since 2023 ({int(hl.present_since_2023):,}): "
          f"{int(hl.repackaged_to_ai):,} ({hl.repackaged_pct}%) were NON-AI in 2023 and "
          f"adopted an AI identity by 2025 (repackaged); the rest were already AI.")

    # 2. what were the repackagers BEFORE? top 2023 categories -------------
    origins = con.execute("""
        WITH rep AS (
            SELECT unnest(string_split(cats23, ',')) AS cat
            FROM panel WHERE in23 AND NOT ai23 AND cats23 IS NOT NULL
        )
        SELECT trim(cat) AS category_2023, COUNT(*) n
        FROM rep
        WHERE lower(trim(cat)) NOT LIKE '%artificial intelligence%'
          AND lower(trim(cat)) NOT LIKE '%machine learning%'
          AND trim(cat) <> ''
        GROUP BY 1 ORDER BY 2 DESC LIMIT 25""").fetchdf()
    print("\n=== What repackagers were BEFORE adopting AI (top 2023 categories) ===")
    print(origins.head(15).to_string(index=False))
    origins.to_csv(OUT / "35_cb_ai_repackaged_origins.csv", index=False)

    # 3. repackaged vs born-AI by founding cohort -------------------------
    cohort = con.execute("""
        SELECT CASE WHEN fy < 2010 THEN 'pre-2010' WHEN fy < 2015 THEN '2010-2014'
                    WHEN fy < 2020 THEN '2015-2019' WHEN fy <= 2025 THEN '2020+' END cohort,
               COUNT(*) FILTER (WHERE in23) present_since_2023,
               ROUND(100.0*COUNT(*) FILTER (WHERE in23 AND NOT ai23)
                     /NULLIF(COUNT(*) FILTER (WHERE in23),0),1) repackaged_pct
        FROM panel WHERE fy BETWEEN 1990 AND 2025 GROUP BY 1
        HAVING COUNT(*) FILTER (WHERE in23) >= 50 ORDER BY 1""").fetchdf()
    print("\n=== Repackaging rate by founding cohort (AI-2025 cos present since 2023) ===")
    print(cohort.to_string(index=False))
    cohort.to_csv(OUT / "36_cb_ai_identity_by_cohort.csv", index=False)

    print("\nsaved -> output/34_cb_ai_identity_timing.csv, 35_cb_ai_repackaged_origins.csv, "
          "36_cb_ai_identity_by_cohort.csv")


if __name__ == "__main__":
    main()
