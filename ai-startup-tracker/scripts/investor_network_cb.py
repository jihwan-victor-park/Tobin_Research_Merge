"""
Investor-side VC-behavior analysis from Crunchbase 2023 — the "which VCs back
AI, and how" layer, unblocked by the CB investments/investors tables.

874K investment links (investor <-> funding_round, with lead flag) tagged by
whether the PORTFOLIO company is AI (canonical Railway flag, via
funding_round -> org_uuid -> organizations.domain). Then aggregated to answer:

  1. Top investors by number of AI-company investments (30_*).
  2. Investor AI-specialization: share of each active investor's portfolio that
     is AI, and how many are AI-specialists vs generalists (31_*).
  3. Syndication: investors-per-round and lead behavior, AI vs non-AI (32_*).
  4. The investor-side AI surge: AI share of all new investments by year (33_*).

Aggregates only (investor = firm/entity, public CB data); no portfolio-company
rows written.

    python3 scripts/investor_network_cb.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import duckdb
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); load_dotenv(ROOT / ".env")
from backend.utils.ai_filter import ai_filter_sql

D = ROOT / "data" / "pb_longitudinal"
OUT = ROOT / "output"
AI = ai_filter_sql("c")


def main() -> None:
    eng = create_engine(os.getenv("RAILWAY_DATABASE_URL") or os.getenv("DATABASE_URL"))
    print("pulling (domain, is_ai) from Railway...")
    comp = pd.read_sql(text(f"""
        SELECT lower(domain) AS domain, bool_or(COALESCE({AI}, FALSE)) AS is_ai
        FROM companies c WHERE domain IS NOT NULL GROUP BY lower(domain)
    """), eng)
    print(f"  {len(comp):,} domains")

    con = duckdb.connect(); con.execute("SET enable_progress_bar=false")
    con.register("comp", comp)
    print("tagging 874K investments by portfolio-company AI status...")
    con.execute(f"""
        CREATE TABLE inv AS
        SELECT iv.investor_uuid, iv.investor_name, iv.investor_type,
               (iv.is_lead_investor = 'true' OR iv.is_lead_investor = TRUE) AS is_lead,
               fr.uuid AS round_uuid, fr.investment_type AS it,
               EXTRACT(year FROM TRY_CAST(fr.announced_on AS DATE)) AS yr,
               COALESCE(c.is_ai, FALSE) AS is_ai
        FROM read_parquet('{D}/cb2023_investments.parquet') iv
        JOIN read_parquet('{D}/cb2023_funding_rounds.parquet') fr ON iv.funding_round_uuid = fr.uuid
        JOIN read_parquet('{D}/cb2023_organizations.parquet') o ON fr.org_uuid = o.uuid
        LEFT JOIN comp c ON lower(o.domain) = c.domain
        WHERE o.domain IS NOT NULL
    """)
    n = con.execute("SELECT count(*) FROM inv").fetchone()[0]
    print(f"  {n:,} investments tagged")

    # 1. Top investors by AI investments -----------------------------------
    top = con.execute("""
        SELECT investor_name,
               COUNT(*) total_investments,
               COUNT(*) FILTER (WHERE is_ai) ai_investments,
               ROUND(100.0*COUNT(*) FILTER (WHERE is_ai)/COUNT(*), 1) ai_share_pct
        FROM inv WHERE investor_name IS NOT NULL
        GROUP BY investor_name
        HAVING COUNT(*) FILTER (WHERE is_ai) >= 5
        ORDER BY ai_investments DESC LIMIT 40
    """).fetchdf()
    print("\n=== Top 15 investors by # AI-company investments ===")
    print(top.head(15).to_string(index=False))
    top.to_csv(OUT / "30_cb_top_ai_investors.csv", index=False)

    # 2. AI specialization among active investors (>=10 investments) --------
    spec = con.execute("""
        WITH per AS (
            SELECT investor_name, COUNT(*) tot, COUNT(*) FILTER (WHERE is_ai) ai
            FROM inv WHERE investor_name IS NOT NULL GROUP BY investor_name
            HAVING COUNT(*) >= 10
        )
        SELECT
          COUNT(*) active_investors,
          COUNT(*) FILTER (WHERE ai=0) no_ai,
          COUNT(*) FILTER (WHERE 1.0*ai/tot BETWEEN 0.0001 AND 0.25) low,
          COUNT(*) FILTER (WHERE 1.0*ai/tot BETWEEN 0.2501 AND 0.5) mid,
          COUNT(*) FILTER (WHERE 1.0*ai/tot > 0.5) ai_specialist,
          ROUND(AVG(100.0*ai/tot),1) avg_ai_share_pct
        FROM per
    """).fetchdf()
    print("\n=== Investor AI-specialization (investors with >=10 deals) ===")
    print(spec.to_string(index=False))
    spec.to_csv(OUT / "31_cb_investor_ai_specialization.csv", index=False)

    # 3. Syndication: investors per round + lead behavior, AI vs non-AI -----
    synd = con.execute("""
        WITH rnd AS (
            SELECT round_uuid, bool_or(is_ai) is_ai, COUNT(*) n_investors,
                   COUNT(*) FILTER (WHERE is_lead) n_leads
            FROM inv GROUP BY round_uuid
        )
        SELECT CASE WHEN is_ai THEN 'AI' ELSE 'Non-AI' END company_type,
               COUNT(*) rounds,
               ROUND(AVG(n_investors),2) avg_investors_per_round,
               ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY n_investors),1) median_investors,
               ROUND(AVG(n_leads),2) avg_leads_per_round
        FROM rnd GROUP BY 1 ORDER BY 1
    """).fetchdf()
    print("\n=== Syndication (investors per round) ===")
    print(synd.to_string(index=False))
    synd.to_csv(OUT / "32_cb_syndication_by_ai.csv", index=False)

    # 4. Investor-side AI surge: AI share of new investments by year --------
    yr = con.execute("""
        SELECT CAST(yr AS INT) AS yr_int, COUNT(*) investments,
               COUNT(*) FILTER (WHERE is_ai) ai_investments,
               ROUND(100.0*COUNT(*) FILTER (WHERE is_ai)/COUNT(*),1) ai_share_pct
        FROM inv WHERE yr BETWEEN 2010 AND 2023 GROUP BY yr ORDER BY yr
    """).fetchdf()
    print("\n=== AI share of new investments by year (investor-side) ===")
    print(yr.to_string(index=False))
    yr.to_csv(OUT / "33_cb_ai_investment_by_year.csv", index=False)

    print("\nsaved -> output/30_cb_top_ai_investors.csv, 31_cb_investor_ai_specialization.csv, "
          "32_cb_syndication_by_ai.csv, 33_cb_ai_investment_by_year.csv")


if __name__ == "__main__":
    main()
