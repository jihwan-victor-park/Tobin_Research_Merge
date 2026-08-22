"""RQ1 (time): how has AI-related startup formation changed?

Reports BOTH the count N_t^AI and the share AIShare_t, separately, because a
rising count does not imply a rising share. Runs on the commercial population,
which is the only one with near-complete founding years (98.8-100% vs 8% for
the unlisted layer -- see results/06_field_coverage_by_bucket.csv).

    railway run -s Postgres -- .venv/bin/python analysis/ai_trends.py
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _db import q, save
import pandas as pd

Z = 1.959963984540054
AI = "(cb_ai_tagged OR ai_score >= 0.5 OR ai_mentioned OR llm_ai_verified)"
MENTION = "(ai_mentioned)"
COMMERCIAL = "verification_status::text IN ('verified_cb','verified_pb')"


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
    print("1. Founding-year coverage by bucket -- who can be in a time series at all")
    print("=" * 74)
    cov = q("""select verification_status::text as bucket, count(*) n,
                 count(founded_year) with_year,
                 round(100.0*count(founded_year)/count(*),1) pct
               from companies group by 1 order by 2 desc""")
    print(cov.to_string(index=False))
    save(cov, "10_founding_year_coverage.csv")

    print("\n" + "=" * 74)
    print("2. AI formation by year, commercial population (canonical definition)")
    print("=" * 74)
    t = q(f"""select founded_year::int as year, count(*) n,
                     count(*) filter (where {AI}) ai,
                     count(*) filter (where {MENTION}) ai_mention
              from companies
              where {COMMERCIAL} and founded_year between 1995 and 2026
              group by 1 order by 1""")
    ci = t.apply(lambda r: wilson(int(r.ai), int(r.n)), axis=1)
    t["ai_share"] = [round(100 * c[0], 2) for c in ci]
    t["share_lo"] = [round(100 * c[1], 2) for c in ci]
    t["share_hi"] = [round(100 * c[2], 2) for c in ci]
    t["mention_share"] = (100 * t.ai_mention / t.n).round(2)
    print(t.to_string(index=False))
    save(t, "11_ai_formation_by_year.csv")

    print("\n" + "=" * 74)
    print("3. Same series split by commercial database (is it one vendor?)")
    print("=" * 74)
    tb = q(f"""select founded_year::int as year,
                 case verification_status::text when 'verified_cb' then 'A' else 'B' end db,
                 count(*) n, count(*) filter (where {AI}) ai
               from companies where {COMMERCIAL} and founded_year between 2000 and 2026
               group by 1,2 order by 1,2""")
    tb["ai_share"] = (100 * tb.ai / tb.n).round(2)
    piv = tb.pivot(index="year", columns="db", values="ai_share")
    npiv = tb.pivot(index="year", columns="db", values="n")
    both = piv.join(npiv, rsuffix="_n")
    print(both.to_string())
    save(tb, "12_ai_formation_by_year_by_db.csv")

    print("\n" + "=" * 74)
    print("4. Entry-lag diagnostic: how full is each recent cohort?")
    print("=" * 74)
    lag = q(f"""select founded_year::int as year, count(*) n,
                  round(avg(extract(year from first_seen_at))::numeric,1) mean_first_seen,
                  round(100.0*count(total_raised)/count(*),1) pct_with_funding
                from companies where {COMMERCIAL} and founded_year between 2010 and 2026
                group by 1 order by 1""")
    print(lag.to_string(index=False))
    save(lag, "13_cohort_entry_lag.csv")

    print("\n" + "=" * 74)
    print("4b. ROBUSTNESS: does the trend survive a constant-selection sample?")
    print("=" * 74)
    # The denominator collapses in recent years (54k firms founded in 2015 vs
    # 2.5k in 2025) and the share of firms with recorded funding rises from 17%
    # to 43%. That is selection: a recently founded firm enters a commercial
    # register mainly when it does something notable. If AI firms are more
    # notable, the rising AI share is partly mechanical. Holding the selection
    # rule fixed -- firms that DID record financing -- removes that channel.
    rb = q(f"""select founded_year::int as year,
                 count(*) filter (where total_raised is not null) n_funded,
                 count(*) filter (where total_raised is not null and {AI}) ai_funded,
                 count(*) filter (where domain is not null) n_domain,
                 count(*) filter (where domain is not null and {AI}) ai_domain,
                 count(*) n_all, count(*) filter (where {AI}) ai_all
               from companies
               where {COMMERCIAL} and founded_year between 2005 and 2025
               group by 1 order by 1""")
    rb["share_all"] = (100 * rb.ai_all / rb.n_all).round(2)
    rb["share_funded"] = (100 * rb.ai_funded / rb.n_funded.replace(0, pd.NA)).round(2)
    rb["share_domain"] = (100 * rb.ai_domain / rb.n_domain.replace(0, pd.NA)).round(2)
    print(rb[["year", "n_all", "share_all", "n_funded", "share_funded",
              "n_domain", "share_domain"]].to_string(index=False))
    save(rb, "14_trend_constant_selection.csv")

    print("\n" + "=" * 74)
    print("5. Counts vs shares -- the distinction that matters")
    print("=" * 74)
    peak = t.loc[t.n.idxmax()]
    print(f"Peak observed formation year (all firms): {int(peak.year)} with n={int(peak.n):,}")
    print(f"Peak observed AI count: {int(t.loc[t.ai.idxmax()].year)} "
          f"with {int(t.ai.max()):,} AI firms")
    big = t[t.n >= 1000]
    print(f"Highest AI share (years with n>=1000): {int(big.loc[big.ai_share.idxmax()].year)} "
          f"at {big.ai_share.max():.1f}%")
    sel = t[t.year.isin([2000, 2005, 2010, 2015, 2018, 2020, 2021, 2022, 2023, 2024, 2025])]
    print("\n" + sel[["year", "n", "ai", "ai_share", "share_lo", "share_hi"]].to_string(index=False))


if __name__ == "__main__":
    main()
