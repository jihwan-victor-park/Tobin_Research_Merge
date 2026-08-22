"""RQ2 + RQ4 (geography, concentration): where is AI entrepreneurship growing,
and is it concentrating or spreading?

Distinguishes two different questions the literature often conflates:
  - size:      N_c^AI, the number of AI firms a country has
  - intensity: AIShare_c, the share of that country's firms that are AI

Concentration is measured on the distribution of AI firms across countries with
the Herfindahl-Hirschman index and Shannon entropy, computed per founding cohort.

    railway run -s Postgres -- .venv/bin/python analysis/geography.py
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _db import q, save
import numpy as np
import pandas as pd

Z = 1.959963984540054
AI = "(cb_ai_tagged OR ai_score >= 0.5 OR ai_mentioned OR llm_ai_verified)"
COMMERCIAL = "verification_status::text IN ('verified_cb','verified_pb')"
MIN_N = 200  # a country-level share on fewer firms than this is noise


def wilson(x, n):
    if n == 0:
        return (float("nan"),) * 3
    p = x / n
    d = 1 + Z**2 / n
    c = (p + Z**2 / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2)) / d
    return p, c - h, c + h


def hhi(shares):
    s = np.asarray(shares, dtype=float)
    return float((s ** 2).sum())


def entropy(shares):
    s = np.asarray(shares, dtype=float)
    s = s[s > 0]
    return float(-(s * np.log(s)).sum())


def main():
    print("=" * 74)
    print("1. Size vs intensity: top countries two different ways")
    print("=" * 74)
    c = q(f"""select country, count(*) n, count(*) filter (where {AI}) ai
              from companies where {COMMERCIAL} and country is not null
              group by 1 having count(*) >= {MIN_N} order by 2 desc""")
    ci = c.apply(lambda r: wilson(int(r.ai), int(r.n)), axis=1)
    c["ai_share"] = [round(100 * x[0], 2) for x in ci]
    c["lo"] = [round(100 * x[1], 2) for x in ci]
    c["hi"] = [round(100 * x[2], 2) for x in ci]
    c["world_ai_share"] = (100 * c.ai / c.ai.sum()).round(2)
    print("\nBY SIZE (number of AI firms):")
    print(c.nlargest(15, "ai")[["country", "n", "ai", "ai_share", "world_ai_share"]].to_string(index=False))
    print("\nBY INTENSITY (AI share of that country's firms), n>=200:")
    print(c.nlargest(15, "ai_share")[["country", "n", "ai", "ai_share", "lo", "hi"]].to_string(index=False))
    print("\nLOWEST INTENSITY:")
    print(c.nsmallest(10, "ai_share")[["country", "n", "ai", "ai_share"]].to_string(index=False))
    save(c.sort_values("ai", ascending=False), "20_country_ai.csv")

    print("\n" + "=" * 74)
    print("2. Growth: AI share by country, early vs late cohort")
    print("=" * 74)
    g = q(f"""select country,
                count(*) filter (where founded_year between 2010 and 2016) n_early,
                count(*) filter (where founded_year between 2010 and 2016 and {AI}) ai_early,
                count(*) filter (where founded_year between 2020 and 2025) n_late,
                count(*) filter (where founded_year between 2020 and 2025 and {AI}) ai_late
              from companies where {COMMERCIAL} and country is not null
              group by 1""")
    g = g[(g.n_early >= MIN_N) & (g.n_late >= MIN_N)].copy()
    g["share_early"] = (100 * g.ai_early / g.n_early).round(2)
    g["share_late"] = (100 * g.ai_late / g.n_late).round(2)
    g["change_pp"] = (g.share_late - g.share_early).round(2)
    g["ratio"] = (g.share_late / g.share_early).round(2)
    print(f"countries meeting n>={MIN_N} in both windows: {len(g)}")
    print("\nFASTEST RISING (pp change in AI share):")
    print(g.nlargest(15, "change_pp")[["country", "n_early", "share_early", "n_late", "share_late", "change_pp", "ratio"]].to_string(index=False))
    print("\nSLOWEST:")
    print(g.nsmallest(8, "change_pp")[["country", "n_early", "share_early", "n_late", "share_late", "change_pp"]].to_string(index=False))
    save(g.sort_values("change_pp", ascending=False), "21_country_ai_growth.csv")

    print("\n" + "=" * 74)
    print("3. Concentration of AI entrepreneurship over founding cohorts")
    print("=" * 74)
    cy = q(f"""select founded_year::int as year, country, count(*) n,
                 count(*) filter (where {AI}) ai
               from companies
               where {COMMERCIAL} and country is not null
                 and founded_year between 2000 and 2025
               group by 1,2""")
    rows = []
    for yr, grp in cy.groupby("year"):
        ai_tot = grp.ai.sum()
        all_tot = grp.n.sum()
        if ai_tot < 100:
            continue
        s_ai = grp.ai / ai_tot
        s_all = grp.n / all_tot
        us = grp.loc[grp.country == "United States", "ai"].sum() / ai_tot
        top5 = grp.nlargest(5, "ai").ai.sum() / ai_tot
        rows.append(dict(year=yr, ai_firms=int(ai_tot), countries=int((grp.ai > 0).sum()),
                         hhi_ai=round(hhi(s_ai), 4), hhi_all=round(hhi(s_all), 4),
                         entropy_ai=round(entropy(s_ai), 4), entropy_all=round(entropy(s_all), 4),
                         us_share=round(100 * us, 2), top5_share=round(100 * top5, 2)))
    conc = pd.DataFrame(rows)
    print(conc.to_string(index=False))
    save(conc, "22_concentration_by_cohort.csv")

    print("\nReading: HHI on the AI distribution vs HHI on ALL firms in the same")
    print("cohort. If AI concentration falls faster than overall concentration,")
    print("AI activity is spreading beyond the incumbent hubs.")

    print("\n" + "=" * 74)
    print("4. Regional aggregation (robustness to country-level noise)")
    print("=" * 74)
    reg = q(f"""select
      case
        when country in ('United States','Canada') then 'North America'
        when country in ('United Kingdom','Germany','France','Netherlands','Sweden','Switzerland',
                         'Spain','Italy','Belgium','Denmark','Norway','Finland','Ireland','Austria',
                         'Portugal','Poland') then 'Europe'
        when country in ('China','Japan','South Korea','Taiwan','Hong Kong') then 'East Asia'
        when country in ('India','Singapore','Indonesia','Malaysia','Thailand','Vietnam','Philippines',
                         'Pakistan','Bangladesh') then 'South & Southeast Asia'
        when country in ('Israel','United Arab Emirates','Saudi Arabia','Turkey','Egypt') then 'Middle East'
        when country in ('Brazil','Mexico','Argentina','Chile','Colombia','Peru') then 'Latin America'
        when country in ('South Africa','Nigeria','Kenya','Ghana','Egypt') then 'Africa'
        when country in ('Australia','New Zealand') then 'Oceania'
        else 'Other' end as region,
      count(*) filter (where founded_year between 2010 and 2016) n_early,
      count(*) filter (where founded_year between 2010 and 2016 and {AI}) ai_early,
      count(*) filter (where founded_year between 2020 and 2025) n_late,
      count(*) filter (where founded_year between 2020 and 2025 and {AI}) ai_late
      from companies where {COMMERCIAL} and country is not null group by 1""")
    reg["share_early"] = (100 * reg.ai_early / reg.n_early).round(2)
    reg["share_late"] = (100 * reg.ai_late / reg.n_late).round(2)
    reg["change_pp"] = (reg.share_late - reg.share_early).round(2)
    reg["world_ai_early"] = (100 * reg.ai_early / reg.ai_early.sum()).round(2)
    reg["world_ai_late"] = (100 * reg.ai_late / reg.ai_late.sum()).round(2)
    print(reg.sort_values("world_ai_late", ascending=False).to_string(index=False))
    save(reg, "23_region_ai.csv")


if __name__ == "__main__":
    main()
