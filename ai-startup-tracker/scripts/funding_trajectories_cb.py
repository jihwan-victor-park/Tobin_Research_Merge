"""
Funding TRAJECTORIES from Crunchbase 2023 round history — the per-company
funding-dynamics layer of the "VC behavior" question that our Railway
funding_signals could NOT support (it stores ~1 summary deal/company).

CB's funding_rounds is real round-by-round history: 538K rounds across 273K
funded orgs, with clean investment_type labels (seed / series_a..j / PE / IPO).
That makes graduation rates and inter-round timing genuinely computable.

Join path (verified 100% coverage): funding_rounds.org_uuid -> organizations.uuid
-> domain -> our Railway companies (canonical AI flag + founded_year). Aggregates
only; no company-level rows are written.

  entry ladder (rank): 0 seed/angel/grant/pre_seed/crowdfunding/convertible
    1 series_a  2 series_b  3 series_c  4 series_d  5 series_e  6 series_f+/PE
    9 post-IPO.  (series_unknown / debt / secondary / undisclosed are NOT ranked)

    python3 scripts/funding_trajectories_cb.py
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

RANK = {
    "pre_seed": 0, "seed": 0, "angel": 0, "grant": 0, "non_equity_assistance": 0,
    "equity_crowdfunding": 0, "product_crowdfunding": 0, "convertible_note": 0,
    "series_a": 1, "series_b": 2, "series_c": 3, "series_d": 4, "series_e": 5,
    "series_f": 6, "series_g": 6, "series_h": 6, "series_i": 6, "series_j": 6,
    "private_equity": 6, "corporate_round": 6,
    "post_ipo_equity": 9, "post_ipo_debt": 9, "post_ipo_secondary": 9,
}  # series_unknown, debt_financing, secondary_market, undisclosed, ico -> unranked


def _pct(n, d):
    return round(100 * n / d, 1) if d else 0.0


def main() -> None:
    eng = create_engine(os.getenv("RAILWAY_DATABASE_URL") or os.getenv("DATABASE_URL"))
    print("pulling (domain, is_ai, founded_year) from Railway...")
    comp = pd.read_sql(text(f"""
        SELECT lower(domain) AS domain,
               bool_or(COALESCE({AI}, FALSE)) AS is_ai,
               max(founded_year) AS founded_year
        FROM companies c WHERE domain IS NOT NULL GROUP BY lower(domain)
    """), eng)
    print(f"  {len(comp):,} distinct domains")

    con = duckdb.connect(); con.execute("SET enable_progress_bar=false")
    rounds = con.execute(f"""
        SELECT lower(o.domain) AS domain, fr.investment_type AS it,
               TRY_CAST(fr.announced_on AS DATE) AS dt
        FROM read_parquet('{D}/cb2023_funding_rounds.parquet') fr
        JOIN read_parquet('{D}/cb2023_organizations.parquet') o ON fr.org_uuid = o.uuid
        WHERE o.domain IS NOT NULL AND fr.announced_on IS NOT NULL
    """).fetchdf()
    print(f"  {len(rounds):,} dated CB rounds with a domain")

    rounds["rank"] = rounds["it"].map(RANK)
    rounds = rounds.dropna(subset=["rank", "dt"]).copy()
    rounds["rank"] = rounds["rank"].astype(int)
    rounds = rounds.merge(comp, on="domain", how="inner")
    rounds["is_ai"] = rounds["is_ai"].fillna(False).astype(bool)
    print(f"  {len(rounds):,} ranked rounds matched to our companies "
          f"({rounds['domain'].nunique():,} companies)")

    rounds = rounds.sort_values(["domain", "dt"])
    g = rounds.groupby("domain")
    per = pd.DataFrame({
        "is_ai": g["is_ai"].first(),
        "founded_year": g["founded_year"].first(),
        "n_rounds": g.size(),
        "first_rank": g["rank"].first(),
        "max_rank": g["rank"].max(),
    })

    # ---- graduation: companies that ENTERED at seed (first ranked round == 0) ----
    seed = per[per["first_rank"] == 0].copy()
    seed["reached_A"] = seed["max_rank"] >= 1
    seed["reached_B"] = seed["max_rank"] >= 2
    seed["reached_C"] = seed["max_rank"] >= 3
    seed["reached_ipo"] = seed["max_rank"] >= 9
    rows = []
    for label, sub in [("AI", seed[seed.is_ai]), ("Non-AI", seed[~seed.is_ai])]:
        n = len(sub)
        rows.append({"company_type": label, "seed_entrants": n,
                     "reached_series_A_pct": _pct(sub.reached_A.sum(), n),
                     "reached_series_B_pct": _pct(sub.reached_B.sum(), n),
                     "reached_series_C_pct": _pct(sub.reached_C.sum(), n),
                     "reached_IPO_pct": _pct(sub.reached_ipo.sum(), n)})
    grad = pd.DataFrame(rows)
    print("\n=== Graduation — companies entering at SEED (CB round history) ===")
    print(grad.to_string(index=False))
    grad.to_csv(OUT / "30_cb_graduation_by_ai.csv", index=False)

    # ---- inter-round timing (months) by AI ----
    rounds["prev_dt"] = g["dt"].shift(1)
    rounds["gap_m"] = (rounds["dt"] - rounds["prev_dt"]).dt.days / 30.44

    def _step_gap(from_rank, to_rank):
        """median months between first round at from_rank and first later round at to_rank."""
        res = {}
        for label in ["AI", "Non-AI"]:
            sub = rounds[rounds.is_ai == (label == "AI")]
            a = sub[sub["rank"] == from_rank].groupby("domain")["dt"].min()
            b = sub[sub["rank"] == to_rank].groupby("domain")["dt"].min()
            j = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
            j = j[j["b"] > j["a"]]
            res[label] = round(((j["b"] - j["a"]).dt.days / 30.44).median(), 1) if len(j) else None
        return res

    seedA = _step_gap(0, 1); AB = _step_gap(1, 2); BC = _step_gap(2, 3)
    rows = []
    for label in ["AI", "Non-AI"]:
        sub_multi = per[(per.is_ai == (label == "AI")) & (per.n_rounds >= 2)]
        med_gap = rounds[rounds.is_ai == (label == "AI")].dropna(subset=["gap_m"])
        rows.append({
            "company_type": label,
            "median_seed_to_A_months": seedA[label],
            "median_A_to_B_months": AB[label],
            "median_B_to_C_months": BC[label],
            "median_gap_all_rounds_months": round(med_gap["gap_m"].median(), 1),
            "median_rounds_per_company": float(per[per.is_ai == (label == "AI")]["n_rounds"].median()),
        })
    timing = pd.DataFrame(rows)
    print("\n=== Financing velocity / timing (CB round history) ===")
    print(timing.to_string(index=False))
    timing.to_csv(OUT / "31_cb_round_timing_by_ai.csv", index=False)

    # ---- graduation (seed -> series_B+) by founding cohort x AI ----
    seed2 = seed.copy()
    seed2["cohort"] = pd.cut(seed2["founded_year"],
                             bins=[0, 2009, 2014, 2019, 2100],
                             labels=["pre-2010", "2010-2014", "2015-2019", "2020+"])
    rows = []
    for label in ["AI", "Non-AI"]:
        sub = seed2[seed2.is_ai == (label == "AI")]
        for c0 in ["pre-2010", "2010-2014", "2015-2019", "2020+"]:
            s = sub[sub.cohort == c0]
            if len(s) >= 30:
                rows.append({"company_type": label, "cohort": c0, "seed_entrants": len(s),
                             "reached_series_B_pct": _pct(s.reached_B.sum(), len(s))})
    cohort = pd.DataFrame(rows)
    print("\n=== Seed -> Series-B+ graduation by founding cohort x AI ===")
    print(cohort.to_string(index=False))
    cohort.to_csv(OUT / "32_cb_graduation_by_cohort_ai.csv", index=False)

    print("\nsaved -> output/30_cb_graduation_by_ai.csv, 31_cb_round_timing_by_ai.csv, "
          "32_cb_graduation_by_cohort_ai.csv")


if __name__ == "__main__":
    main()
