"""
Research Analysis Script
========================
Produces paper-ready statistics for the AI entrepreneurship study.
Queries the Railway production DB and writes CSV outputs to ./output/.

Sections:
  1. AI formation timeline (by year)
  2. Geographic concentration (country × AI%)
  3. Industry vertical breakdown
  4. Funding analysis (AI vs non-AI deals, sizes, rounds)
  5. US vs International comparison
  6. Data-lag correction estimate (recent years undercounted)
  7. Full research export (AI companies, all fields)

Usage:
    python3 scripts/research_analysis.py [--output-dir ./output]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.utils.ai_filter import ai_filter_sql  # noqa: E402

load_dotenv()

def _db_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("RAILWAY_URL")
    if not url:
        raise RuntimeError("Set DATABASE_URL or RAILWAY_URL env var")
    return url

# Canonical AI predicate — see backend/utils/ai_filter.py for the single
# source of truth (also used by the dashboard).
AI_FILTER = ai_filter_sql()
C_AI_FILTER = ai_filter_sql("c")

# Companies NOT covered by Crunchbase or PitchBook — same definition as
# Victor's Info Sheet _load_contribution_stats() in pipeline_dashboard.py,
# collapsed to a single bucket (scraper-unique + GitHub-unique).
NON_CB_PB_FILTER = "verification_status NOT IN ('verified_cb', 'verified_pb', 'verified_cb_pb')"
BUCKET_CASE = (
    "CASE WHEN verification_status = 'verified_cb' THEN 'cb' "
    "WHEN verification_status = 'verified_pb' THEN 'pb' "
    "ELSE 'hidden' END"
)


# ── helpers ──────────────────────────────────────────────────────────────────

def q(engine, sql: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.DataFrame(conn.execute(text(sql)).mappings().all())


def pct(num, denom):
    return round(100.0 * num / denom, 1) if denom else 0.0


def save(df: pd.DataFrame, name: str, out: Path):
    path = out / f"{name}.csv"
    df.to_csv(path, index=False)
    print(f"  ✓ {name}.csv  ({len(df):,} rows)")
    return df


# ── Section 1: Formation timeline ────────────────────────────────────────────

def formation_timeline(engine, out: Path):
    print("\n=== 1. AI Formation Timeline ===")
    df = q(engine, f"""
        SELECT
            founded_year,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE {AI_FILTER}) AS ai,
            ROUND(100.0 * COUNT(*) FILTER (WHERE {AI_FILTER}) / COUNT(*), 1) AS ai_pct
        FROM companies
        WHERE founded_year BETWEEN 2000 AND 2025
        GROUP BY founded_year
        ORDER BY founded_year
    """)
    print(df.to_string(index=False))
    save(df, "01_formation_timeline", out)

    # Inflection analysis
    recent = df[df["founded_year"] >= 2018]
    pre_chatgpt = df[(df["founded_year"] >= 2018) & (df["founded_year"] <= 2022)]["ai_pct"].mean()
    post_chatgpt = df[df["founded_year"] >= 2023]["ai_pct"].mean()
    print(f"\n  Pre-ChatGPT avg AI% (2018-2022): {pre_chatgpt:.1f}%")
    print(f"  Post-ChatGPT avg AI% (2023-2025): {post_chatgpt:.1f}%")
    print(f"  Multiplier: {post_chatgpt/pre_chatgpt:.1f}x")
    return df


# ── Section 2: Geographic concentration ──────────────────────────────────────

def geographic_concentration(engine, out: Path):
    print("\n=== 2. Geographic AI Concentration ===")
    df = q(engine, f"""
        SELECT
            country,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE {AI_FILTER}) AS ai,
            ROUND(100.0 * COUNT(*) FILTER (WHERE {AI_FILTER}) / COUNT(*), 1) AS ai_pct,
            COUNT(*) FILTER (WHERE founded_year >= 2020 AND {AI_FILTER}) AS ai_since_2020
        FROM companies
        WHERE country IS NOT NULL AND country != ''
        GROUP BY country
        HAVING COUNT(*) >= 100
        ORDER BY ai DESC
    """)
    df["ai_share_of_global"] = (df["ai"] / df["ai"].sum() * 100).round(2)
    print(f"  {len(df):,} countries with ≥100 companies")
    print(df.head(20).to_string(index=False))
    save(df, "02_geographic_concentration", out)

    # Top 5 countries' share of global AI startups
    top5_share = df.head(5)["ai_share_of_global"].sum()
    print(f"\n  Top 5 countries' share of global AI: {top5_share:.1f}%")
    print(df.head(5)[["country", "ai", "ai_pct", "ai_share_of_global"]].to_string(index=False))
    return df


# ── Section 3: Country × Year AI% matrix ─────────────────────────────────────

def country_year_matrix(engine, out: Path):
    print("\n=== 3. Country × Year AI% Matrix ===")
    df = q(engine, f"""
        WITH top20 AS (
            SELECT country FROM companies
            WHERE country IS NOT NULL AND country != ''
            GROUP BY country ORDER BY COUNT(*) DESC LIMIT 20
        )
        SELECT
            c.country,
            c.founded_year,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE {AI_FILTER}) AS ai,
            ROUND(100.0 * COUNT(*) FILTER (WHERE {AI_FILTER}) / COUNT(*), 1) AS ai_pct
        FROM companies c
        JOIN top20 ON c.country = top20.country
        WHERE c.founded_year BETWEEN 2015 AND 2025
        GROUP BY c.country, c.founded_year
        ORDER BY c.country, c.founded_year
    """)
    save(df, "03_country_year_matrix", out)

    # Pivot for readability
    pivot = df.pivot(index="country", columns="founded_year", values="ai_pct").fillna(0)
    print(pivot.to_string())
    return df


# ── Section 4: Industry vertical breakdown ───────────────────────────────────

def vertical_breakdown(engine, out: Path):
    print("\n=== 4. Industry Vertical Breakdown ===")
    df = q(engine, f"""
        SELECT
            unnest(categories) AS vertical,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE {AI_FILTER}) AS ai,
            ROUND(100.0 * COUNT(*) FILTER (WHERE {AI_FILTER}) / COUNT(*), 1) AS ai_pct
        FROM companies
        WHERE categories IS NOT NULL AND array_length(categories, 1) > 0
        GROUP BY vertical
        HAVING COUNT(*) >= 500
        ORDER BY ai_pct DESC
    """)
    print(df.to_string(index=False))
    save(df, "04_vertical_breakdown", out)
    return df


# ── Section 5: Funding analysis ───────────────────────────────────────────────

def funding_analysis(engine, out: Path):
    print("\n=== 5. Funding Analysis ===")

    # Deal counts and sizes by AI vs non-AI and year
    deals = q(engine, f"""
        SELECT
            EXTRACT(year FROM fs.deal_date)::int AS deal_year,
            CASE WHEN {C_AI_FILTER} THEN 'AI' ELSE 'Non-AI' END AS company_type,
            COUNT(*) AS deals,
            ROUND((AVG(fs.deal_size)/1e6)::numeric, 2) AS avg_deal_usd_m,
            ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY fs.deal_size)/1e6)::numeric, 2) AS median_deal_usd_m,
            ROUND((SUM(fs.deal_size)/1e6)::numeric, 0) AS total_raised_usd_m
        FROM funding_signals fs
        JOIN companies c ON c.id = fs.company_id
        WHERE fs.deal_date IS NOT NULL
          AND EXTRACT(year FROM fs.deal_date) BETWEEN 2015 AND 2025
          AND fs.deal_size IS NOT NULL
        GROUP BY deal_year, company_type
        ORDER BY deal_year, company_type
    """)
    print("Deal volume and size by year:")
    print(deals.to_string(index=False))
    save(deals, "05a_funding_by_year", out)

    # Round type distribution AI vs non-AI
    rounds = q(engine, f"""
        SELECT
            fs.round_type,
            CASE WHEN {C_AI_FILTER} THEN 'AI' ELSE 'Non-AI' END AS company_type,
            COUNT(*) AS deals,
            ROUND((AVG(fs.deal_size)/1e6)::numeric, 2) AS avg_deal_usd_m
        FROM funding_signals fs
        JOIN companies c ON c.id = fs.company_id
        WHERE fs.round_type IS NOT NULL
        GROUP BY fs.round_type, company_type
        HAVING COUNT(*) >= 10
        ORDER BY deals DESC
    """)
    save(rounds, "05b_funding_by_round_type", out)

    # Total raised distribution: AI vs non-AI companies
    raised = q(engine, f"""
        SELECT
            CASE WHEN {AI_FILTER} THEN 'AI' ELSE 'Non-AI' END AS company_type,
            COUNT(*) AS companies,
            ROUND(AVG(total_raised)::numeric, 2) AS avg_raised_m,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_raised)::numeric, 2) AS median_raised_m,
            ROUND(SUM(total_raised)::numeric, 0) AS total_m
        FROM companies
        WHERE total_raised IS NOT NULL AND total_raised > 0
        GROUP BY company_type
    """)
    print("\nTotal raised AI vs Non-AI:")
    print(raised.to_string(index=False))
    save(raised, "05c_total_raised_ai_vs_nonai", out)
    return deals


# ── Section 6: US vs International ──────────────────────────────────────────

def us_vs_international(engine, out: Path):
    print("\n=== 6. US vs International ===")
    df = q(engine, f"""
        SELECT
            CASE
                WHEN country = 'United States' THEN 'United States'
                WHEN country IS NOT NULL AND country != '' THEN 'International'
                ELSE 'Unknown'
            END AS region,
            founded_year,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE {AI_FILTER}) AS ai,
            ROUND(100.0 * COUNT(*) FILTER (WHERE {AI_FILTER}) / COUNT(*), 1) AS ai_pct
        FROM companies
        WHERE founded_year BETWEEN 2015 AND 2025
        GROUP BY region, founded_year
        ORDER BY region, founded_year
    """)
    print(df.to_string(index=False))
    save(df, "06_us_vs_international", out)
    return df


# ── Section 7: Data lag correction ───────────────────────────────────────────

def data_lag_note(engine, out: Path):
    print("\n=== 7. Data Lag / Coverage Note ===")
    # Compare company formation to peak years to estimate undercounting
    df = q(engine, """
        SELECT founded_year, COUNT(*) AS total
        FROM companies
        WHERE founded_year BETWEEN 2015 AND 2025
        GROUP BY founded_year ORDER BY founded_year
    """)
    peak = int(df.loc[df["total"].idxmax(), "total"])
    peak_year = int(df.loc[df["total"].idxmax(), "founded_year"])
    print(f"  Peak coverage year: {peak_year} ({peak:,} companies)")
    for _, row in df[df["founded_year"] >= 2021].iterrows():
        lag_pct = 100 - round(row["total"] / peak * 100, 1)
        print(f"  {int(row['founded_year'])}: {int(row['total']):,} companies  "
              f"(~{lag_pct:.0f}% undercounted vs peak)")
    df["pct_of_peak"] = (df["total"] / peak * 100).round(1)
    df["est_undercount_pct"] = (100 - df["pct_of_peak"]).clip(lower=0)
    save(df, "07_data_lag_estimate", out)
    return df


# ── Section 8: Full AI company export ────────────────────────────────────────

def full_ai_export(engine, out: Path):
    print("\n=== 8. Full AI Company Export ===")
    df = q(engine, f"""
        SELECT
            name, domain, country, city, founded_year,
            ai_score, cb_ai_tagged, ai_mentioned, llm_ai_verified,
            total_raised, team_size, stage,
            categories, description
        FROM companies
        WHERE {AI_FILTER}
        ORDER BY founded_year DESC NULLS LAST, country
    """)
    print(f"  {len(df):,} AI companies exported")
    save(df, "08_ai_companies_full", out)
    return df


# ── Section 9: Hidden-company formation & survival trends ───────────────────

def hidden_formation_survival(engine, out: Path):
    print("\n=== 9. Non-CB/PB ('Hidden') Formation & Survival Trends ===")
    print("  CAVEATS: founded_year covers a minority of this population (enrichment")
    print("  is bounded by the ~41% that even have a domain). domain_status is a")
    print("  liveness PROXY for survival (see scripts/check_domain_liveness.py's")
    print("  docstring) — not a verified operating-status field. Treat both as")
    print("  descriptive/exploratory, not a rigorous survival-analysis input.")

    timeline = q(engine, f"""
        SELECT
            founded_year,
            CASE WHEN s.company_id IS NOT NULL THEN 'scraper' ELSE 'github' END AS source,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE {C_AI_FILTER}) AS ai
        FROM companies c
        LEFT JOIN (SELECT DISTINCT company_id FROM incubator_signals) s ON s.company_id = c.id
        WHERE {NON_CB_PB_FILTER}
          AND founded_year BETWEEN 2000 AND 2025
        GROUP BY founded_year, source
        ORDER BY founded_year, source
    """)
    print(f"\n  Formation timeline ({timeline['total'].sum():,} companies with founded_year):")
    print(timeline.to_string(index=False))
    save(timeline, "09a_hidden_formation_timeline", out)

    survival = q(engine, f"""
        SELECT
            founded_year,
            COUNT(*) FILTER (WHERE domain_status IS NOT NULL) AS total_checked,
            COUNT(*) FILTER (WHERE domain_status = 'live') AS live,
            COUNT(*) FILTER (WHERE domain_status = 'dead') AS dead,
            ROUND(100.0 * COUNT(*) FILTER (WHERE domain_status = 'live')
                  / NULLIF(COUNT(*) FILTER (WHERE domain_status IS NOT NULL), 0), 1) AS live_pct
        FROM companies c
        WHERE {NON_CB_PB_FILTER}
          AND founded_year BETWEEN 2000 AND 2025
        GROUP BY founded_year
        HAVING COUNT(*) FILTER (WHERE domain_status IS NOT NULL) > 0
        ORDER BY founded_year
    """)
    print(f"\n  Domain-liveness ('survival proxy') by founding cohort "
          f"({survival['total_checked'].sum():,} checked):")
    print(survival.to_string(index=False))
    save(survival, "09b_hidden_survival_proxy_by_cohort", out)
    return timeline, survival


# ── Sections 10-13: Hidden vs. institutional (CB/PB) comparison ─────────────

def hidden_vs_institutional_founding_year(engine, out: Path):
    print("\n=== 10. Hidden vs. Institutional: Founding-Year Distribution ===")
    df = q(engine, f"""
        SELECT founded_year, {BUCKET_CASE} AS bucket, COUNT(*) AS n
        FROM companies
        WHERE founded_year BETWEEN 2005 AND 2025
        GROUP BY founded_year, bucket
        ORDER BY founded_year, bucket
    """)
    df["share_of_bucket_pct"] = (
        df.groupby("bucket")["n"].transform(lambda s: 100.0 * s / s.sum())
    ).round(2)
    print(df.pivot(index="founded_year", columns="bucket", values="share_of_bucket_pct")
            .fillna(0).to_string())
    save(df, "10_hidden_vs_institutional_founding_year", out)
    return df


def hidden_vs_institutional_geography(engine, out: Path, top_n: int = 20):
    print("\n=== 11. Hidden vs. Institutional: Geography ===")
    df = q(engine, f"""
        SELECT country, {BUCKET_CASE} AS bucket, COUNT(*) AS n
        FROM companies
        WHERE country IS NOT NULL AND country != ''
        GROUP BY country, bucket
    """)
    df["share_of_bucket_pct"] = (
        df.groupby("bucket")["n"].transform(lambda s: 100.0 * s / s.sum())
    ).round(2)
    top_countries = (
        df.groupby("country")["n"].sum().sort_values(ascending=False).head(top_n).index
    )
    view = df[df["country"].isin(top_countries)]
    pivot = view.pivot(index="country", columns="bucket", values="share_of_bucket_pct").fillna(0)
    print(pivot.reindex(top_countries).to_string())
    save(df, "11_hidden_vs_institutional_geography", out)
    return df


def hidden_vs_institutional_verticals(engine, out: Path):
    print("\n=== 12. Hidden vs. Institutional: Industry Verticals ===")
    df = q(engine, f"""
        SELECT unnest(categories) AS vertical, {BUCKET_CASE} AS bucket, COUNT(*) AS n
        FROM companies
        WHERE categories IS NOT NULL AND array_length(categories, 1) > 0
        GROUP BY vertical, bucket
    """)
    df["share_of_bucket_pct"] = (
        df.groupby("bucket")["n"].transform(lambda s: 100.0 * s / s.sum())
    ).round(2)
    pivot = df.pivot(index="vertical", columns="bucket", values="share_of_bucket_pct").fillna(0)
    print(pivot.sort_values("hidden", ascending=False).to_string())
    save(df, "12_hidden_vs_institutional_verticals", out)
    return df


def hidden_vs_institutional_ai_adoption(engine, out: Path):
    print("\n=== 13. Hidden vs. Institutional: AI Adoption Rate ===")
    df = q(engine, f"""
        SELECT
            {BUCKET_CASE} AS bucket,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE {AI_FILTER}) AS ai,
            ROUND(100.0 * COUNT(*) FILTER (WHERE {AI_FILTER}) / COUNT(*), 1) AS ai_pct
        FROM companies
        GROUP BY bucket
        ORDER BY ai_pct DESC
    """)
    print(df.to_string(index=False))
    save(df, "13_hidden_vs_institutional_ai_adoption", out)
    return df


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="./output", help="Directory for CSV output")
    parser.add_argument("--skip-full-export", action="store_true",
                        help="Skip the large full-company export (section 8)")
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {out.resolve()}")

    engine = create_engine(_db_url())
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM companies")).scalar()
        ai_total = conn.execute(text(
            f"SELECT COUNT(*) FROM companies WHERE {AI_FILTER}"
        )).scalar()
        countries = conn.execute(text(
            "SELECT COUNT(DISTINCT country) FROM companies WHERE country IS NOT NULL AND country != ''"
        )).scalar()
    print(f"\nDB snapshot: {total:,} companies | "
          f"{ai_total:,} AI ({pct(ai_total,total)}%) | "
          f"{countries} countries")

    formation_timeline(engine, out)
    geographic_concentration(engine, out)
    country_year_matrix(engine, out)
    vertical_breakdown(engine, out)

    try:
        funding_analysis(engine, out)
    except Exception as e:
        print(f"  [funding] Error: {e} — skipping")

    us_vs_international(engine, out)
    data_lag_note(engine, out)

    hidden_formation_survival(engine, out)
    hidden_vs_institutional_founding_year(engine, out)
    hidden_vs_institutional_geography(engine, out)
    hidden_vs_institutional_verticals(engine, out)
    hidden_vs_institutional_ai_adoption(engine, out)

    if not args.skip_full_export:
        full_ai_export(engine, out)

    print(f"\n✓ All outputs written to {out.resolve()}/")


if __name__ == "__main__":
    main()
