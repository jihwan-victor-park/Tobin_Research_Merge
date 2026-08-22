"""RQ3 (industry): which sectors are becoming AI-intensive, and where does
AI entrepreneurship specialise geographically?

Sector comes from the canonical 17-vertical taxonomy (backend/utils/industry.py),
stored in companies.categories. A firm can carry several categories, so shares
are computed per category and do not sum to one.

    railway run -s Postgres -- .venv/bin/python analysis/industry.py
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _db import q, save
import pandas as pd

Z = 1.959963984540054
AI = "(cb_ai_tagged OR ai_score >= 0.5 OR ai_mentioned OR llm_ai_verified)"
COMMERCIAL = "verification_status::text IN ('verified_cb','verified_pb')"
MIN_N = 300


def wilson(x, n):
    if n == 0:
        return (float("nan"),) * 3
    p = x / n
    d = 1 + Z**2 / n
    c = (p + Z**2 / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2)) / d
    return p, c - h, c + h


def main():
    print("=" * 74)
    print("1. AI intensity by sector, early vs late founding cohort")
    print("=" * 74)
    s = q(f"""select unnest(categories) as sector,
      count(*) filter (where founded_year between 2010 and 2016) n_early,
      count(*) filter (where founded_year between 2010 and 2016 and {AI}) ai_early,
      count(*) filter (where founded_year between 2020 and 2025) n_late,
      count(*) filter (where founded_year between 2020 and 2025 and {AI}) ai_late,
      count(*) n_all, count(*) filter (where {AI}) ai_all
      from companies where {COMMERCIAL} and categories is not null group by 1""")
    s = s[(s.n_early >= MIN_N) & (s.n_late >= MIN_N)].copy()
    s["share_early"] = (100 * s.ai_early / s.n_early).round(2)
    s["share_late"] = (100 * s.ai_late / s.n_late).round(2)
    s["change_pp"] = (s.share_late - s.share_early).round(2)
    s["ratio"] = (s.share_late / s.share_early).round(2)
    ci = s.apply(lambda r: wilson(int(r.ai_late), int(r.n_late)), axis=1)
    s["late_lo"] = [round(100 * x[1], 2) for x in ci]
    s["late_hi"] = [round(100 * x[2], 2) for x in ci]
    print(s.sort_values("share_late", ascending=False)[
        ["sector", "n_early", "share_early", "n_late", "share_late", "late_lo", "late_hi",
         "change_pp", "ratio"]].to_string(index=False))
    save(s.sort_values("share_late", ascending=False), "30_sector_ai.csv")

    print("\n" + "=" * 74)
    print("2. Sector AI share by year (the full panel)")
    print("=" * 74)
    sy = q(f"""select founded_year::int as year, unnest(categories) as sector,
                 count(*) n, count(*) filter (where {AI}) ai
               from companies
               where {COMMERCIAL} and categories is not null
                 and founded_year between 2010 and 2025
               group by 1,2""")
    sy["ai_share"] = (100 * sy.ai / sy.n).round(2)
    keep = s.sort_values("n_all", ascending=False).sector.head(10).tolist()
    piv = sy[sy.sector.isin(keep) & (sy.n >= 100)].pivot(
        index="year", columns="sector", values="ai_share")
    print(piv.round(1).to_string())
    save(sy, "31_sector_ai_by_year.csv")

    print("\n" + "=" * 74)
    print("3. Which sectors were early vs late to AI?")
    print("=" * 74)
    early_lead = s.nlargest(5, "share_early")[["sector", "share_early", "share_late", "change_pp"]]
    fastest = s.nlargest(5, "change_pp")[["sector", "share_early", "share_late", "change_pp"]]
    laggard = s.nsmallest(5, "share_late")[["sector", "share_early", "share_late", "change_pp"]]
    print("Highest AI share ALREADY in the 2010-16 cohort:")
    print(early_lead.to_string(index=False))
    print("\nLargest increase:")
    print(fastest.to_string(index=False))
    print("\nStill least AI-intensive:")
    print(laggard.to_string(index=False))

    print("\n" + "=" * 74)
    print("4. Location quotient: country x sector specialisation in AI")
    print("=" * 74)
    # LQ_{c,k} = (share of country c's AI firms in sector k) /
    #            (share of all AI firms in sector k)
    lq = q(f"""select country, unnest(categories) as sector, count(*) ai
               from companies
               where {COMMERCIAL} and country is not null and categories is not null
                 and founded_year between 2015 and 2025 and {AI}
               group by 1,2""")
    tot_c = lq.groupby("country").ai.sum()
    tot_k = lq.groupby("sector").ai.sum()
    grand = lq.ai.sum()
    big_c = tot_c[tot_c >= 400].index
    lq = lq[lq.country.isin(big_c)].copy()
    lq["lq"] = ((lq.ai / lq.country.map(tot_c)) / (lq.sector.map(tot_k) / grand)).round(3)
    lq = lq[lq.ai >= 40]
    print(f"countries with >=400 AI firms founded 2015-2025: {len(big_c)}")
    print("\nStrongest AI specialisations (LQ, cells with >=40 firms):")
    print(lq.nlargest(20, "lq")[["country", "sector", "ai", "lq"]].to_string(index=False))
    save(lq.sort_values("lq", ascending=False), "32_location_quotient.csv")

    print("\nSelected large ecosystems, their top specialisation:")
    for cty in ["United States", "China", "India", "United Kingdom", "Israel",
                "Germany", "Japan", "South Korea", "France", "Canada"]:
        sub = lq[lq.country == cty]
        if len(sub):
            t = sub.nlargest(1, "lq").iloc[0]
            print(f"  {cty:<16} {t.sector:<26} LQ={t.lq:.2f}  (n={int(t.ai)})")


if __name__ == "__main__":
    main()
