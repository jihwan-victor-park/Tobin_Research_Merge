"""
Match our companies to Crunchbase 2023 exit outcomes (acquired / IPO / closed)
by domain. Fills the exit-outcome gap flagged all session — CB `status` plus
the acquisitions/ipos tables give real survival/exit signal, keyed cleanly by
domain (CB org.domain <-> companies.domain).

Free (pure joins, no LLM). Reads CB parquets from data/pb_longitudinal/
(git-ignored) and our companies from Railway. Writes an aggregate CSV; does
NOT modify the DB (report only) unless --write-status is passed.

    python scripts/match_cb_exits.py
"""
from __future__ import annotations
import os, sys
from pathlib import Path
import duckdb, pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); load_dotenv(ROOT / ".env")
D = str(ROOT / "data" / "pb_longitudinal") + "/"


def main() -> None:
    eng = create_engine(os.getenv("RAILWAY_DATABASE_URL"))
    ours = pd.read_sql(text("""
        SELECT lower(domain) dom,
          CASE WHEN verification_status::text LIKE 'verified%' THEN 'commercial' ELSE 'hidden' END bucket,
          (cb_ai_tagged OR ai_score>=0.5 OR ai_mentioned OR llm_ai_verified) is_ai
        FROM companies WHERE domain IS NOT NULL
    """), eng)
    print(f"our companies with domain: {len(ours):,}")

    con = duckdb.connect()
    con.register("ours", ours)
    cb = con.execute(f"""
        SELECT o.bucket, o.is_ai,
               COUNT(*) n_matched,
               COUNT(*) FILTER (WHERE cb.status='acquired') acquired,
               COUNT(*) FILTER (WHERE cb.status='ipo') ipo,
               COUNT(*) FILTER (WHERE cb.status='closed') closed,
               COUNT(*) FILTER (WHERE cb.status='operating') operating
        FROM ours o
        JOIN read_parquet('{D}cb2023_organizations.parquet') cb ON o.dom = lower(cb.domain)
        GROUP BY 1,2 ORDER BY 1,2
    """).fetchdf()
    print("\nExit outcomes (our companies matched to CB 2023 by domain):")
    print(cb.to_string(index=False))
    cb["exit_rate_pct"] = (100*(cb.acquired+cb.ipo)/cb.n_matched).round(1)
    out = ROOT / "output" / "23_exit_outcomes.csv"
    cb.to_csv(out, index=False)
    tot_m, tot_a, tot_i, tot_c = cb.n_matched.sum(), cb.acquired.sum(), cb.ipo.sum(), cb.closed.sum()
    print(f"\nTOTAL matched to CB: {tot_m:,} | acquired {tot_a:,} | ipo {tot_i:,} | closed {tot_c:,}")
    print(f"  -> exit (acq+ipo) rate among matched: {100*(tot_a+tot_i)/tot_m:.1f}%")
    print(f"saved -> {out}")


if __name__ == "__main__":
    main()
