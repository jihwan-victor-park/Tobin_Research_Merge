#!/usr/bin/env python3
"""
Founder-level analysis: AI-company vs non-AI-company founders.

Reads the LOCAL Revelio founder parquets (person-level PII — names, LinkedIn
URLs, gender/ethnicity inferences — which are git-ignored and NEVER committed),
joins each founder to their company's AI status (by domain, from the DB's
canonical AI filter), and writes AGGREGATE-only CSVs to ./output/ (14-18).
Only the aggregates are safe to commit / show on the dashboard.

Founder detection is Revelio role_k17000_v3 in {"Executive Founder",
"Chief Executive Officer"} (the new linkedin_v20260612 export) — a real founder
signal, unlike the retired role_k1500 "senior officer" proxy.

Usage:
    python3 scripts/founder_analysis.py                       # local DB AI flags
    python3 scripts/founder_analysis.py --railway             # Railway AI flags
    python3 scripts/founder_analysis.py --founder-dir scripts/founder_poc
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")
from backend.utils.ai_filter import ai_filter_sql  # noqa: E402


def save(df: pd.DataFrame, name: str, out: Path):
    df.to_csv(out / f"{name}.csv", index=False)
    print(f"  ✓ {name}.csv  ({len(df):,} rows)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--railway", action="store_true")
    ap.add_argument("--founder-dir", default="scripts/founder_poc")
    ap.add_argument("--output-dir", default="./output")
    args = ap.parse_args()

    url = os.getenv("RAILWAY_DATABASE_URL") if args.railway else os.getenv("DATABASE_URL")
    fdir = Path(args.founder_dir)
    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)

    # domain -> is_ai (canonical filter)
    eng = create_engine(url)
    with eng.connect() as conn:
        rows = conn.execute(text(
            f"SELECT lower(domain) d, ({ai_filter_sql()}) a FROM companies WHERE domain IS NOT NULL"
        )).all()
    ai_by_dom = {d: bool(a) for d, a in rows}
    print(f"AI flags loaded for {len(ai_by_dom):,} domains")

    pos = pd.read_parquet(fdir / "founder_positions_new.parquet")
    usr = pd.read_parquet(fdir / "founder_users_new.parquet")
    edu = pd.read_parquet(fdir / "founder_education_new.parquet")

    pos["is_ai"] = pos["company_domain"].astype(str).str.lower().map(ai_by_dom)
    pos_m = pos.dropna(subset=["is_ai"])
    # each founder → founded an AI company (any)
    u_ai = pos_m.groupby("user_id")["is_ai"].max()

    # ── 14. coverage ──────────────────────────────────────────────────
    cov = pd.DataFrame([{
        "companies_with_founder": int(pos["company_id"].nunique()),
        "distinct_founders": int(pos["user_id"].nunique()),
        "founders_with_demographics": int(usr["user_id"].nunique()),
        "founders_with_education": int(edu["user_id"].nunique()),
        "founder_positions_ai_company": int(pos_m["is_ai"].sum()),
        "founder_positions_nonai_company": int((~pos_m["is_ai"]).sum()),
    }])
    save(cov, "14_founder_coverage", out)

    # ── 15. gender + prestige, AI vs non-AI ───────────────────────────
    u = usr.merge(u_ai.rename("is_ai"), on="user_id", how="inner")
    g = u.groupby("is_ai").apply(lambda x: pd.Series({
        "founders": len(x),
        "pct_female": round(100 * (x["sex_predicted"] == "F").mean(), 1),
        "prestige_mean": round(x["prestige"].mean(), 3),
        "prestige_median": round(x["prestige"].median(), 3),
    }), include_groups=False).reset_index()
    g["cohort"] = g["is_ai"].map({True: "AI", False: "non-AI"})
    save(g[["cohort", "founders", "pct_female", "prestige_mean", "prestige_median"]],
         "15_founder_gender_prestige", out)

    # ── 16. highest degree distribution ───────────────────────────────
    deg = (pd.crosstab(u["is_ai"], u["highest_degree"], normalize="index") * 100).round(1)
    deg.index = deg.index.map({True: "AI", False: "non-AI"})
    save(deg.reset_index().rename(columns={"is_ai": "cohort"}), "16_founder_degree", out)

    # ── 17. field of study distribution ───────────────────────────────
    e = edu.merge(u_ai.rename("is_ai"), on="user_id", how="inner")
    fld = (pd.crosstab(e["is_ai"], e["field"], normalize="index") * 100).round(1)
    fld.index = fld.index.map({True: "AI", False: "non-AI"})
    # keep the most common fields as columns
    top_fields = e["field"].value_counts().head(15).index.tolist()
    save(fld[[c for c in top_fields if c in fld.columns]].reset_index().rename(
        columns={"is_ai": "cohort"}), "17_founder_field", out)

    # ── 18. top universities (AI founders vs all) ─────────────────────
    uni_ai = e[e["is_ai"]]["university_name"].value_counts().head(25)
    uni_all = e["university_name"].value_counts().head(25)
    uni = pd.DataFrame({
        "university": uni_all.index,
        "all_founders": uni_all.values,
    }).merge(
        pd.DataFrame({"university": uni_ai.index, "ai_founders": uni_ai.values}),
        on="university", how="outer"
    ).fillna(0)
    uni[["all_founders", "ai_founders"]] = uni[["all_founders", "ai_founders"]].astype(int)
    save(uni.sort_values("ai_founders", ascending=False), "18_founder_top_universities", out)

    print("\nHeadline: AI founders vs non-AI —")
    print(g[["cohort", "founders", "pct_female", "prestige_mean"]].to_string(index=False))


if __name__ == "__main__":
    main()
