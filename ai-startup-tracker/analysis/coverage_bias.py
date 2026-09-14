"""RQ5 + RQ6: how much do commercial databases under-observe AI startups?

Reproduces the headline 20.4 / 12.3 / 10.6 comparison from live data, adds
Wilson intervals, difference intervals, odds ratios, and a leave-one-channel-out
check on the unlisted layer.

    railway run -s Postgres -- .venv/bin/python analysis/coverage_bias.py
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _db import q, save
import pandas as pd

Z = 1.959963984540054  # 95%


def wilson(x, n):
    """Wilson score interval — correct at the small counts in the unlisted cells."""
    if n == 0:
        return (float("nan"),) * 3
    p = x / n
    d = 1 + Z**2 / n
    c = (p + Z**2 / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2)) / d
    return p, c - h, c + h


def diff_ci(x1, n1, x2, n2):
    """Newcombe hybrid-score interval for p1 - p2."""
    p1, l1, u1 = wilson(x1, n1)
    p2, l2, u2 = wilson(x2, n2)
    lo = (p1 - p2) - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = (p1 - p2) + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return p1 - p2, lo, hi


def odds_ratio(x1, n1, x2, n2):
    a, b, c, d = x1, n1 - x1, x2, n2 - x2
    if min(a, b, c, d) == 0:
        a, b, c, d = a + .5, b + .5, c + .5, d + .5
    orr = (a / b) / (c / d)
    se = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    return orr, math.exp(math.log(orr) - Z * se), math.exp(math.log(orr) + Z * se)


# ── AI definitions. The pipeline filter is the primary; the others are
# robustness variants reported side by side in the paper. ────────────────
AI_DEFS = {
    # The pipeline's single source of truth: backend/utils/ai_filter.py
    "canonical":  "(cb_ai_tagged OR ai_score >= 0.5 OR ai_mentioned OR llm_ai_verified)",
    # Drops the broad free-text mention flag — the most likely false-positive term.
    "no_mention": "(cb_ai_tagged OR ai_score >= 0.5 OR llm_ai_verified)",
    # What the predicate was before the LLM pass existed. Shows the structural
    # exclusion of database B documented in the project handoff.
    "pre_llm":    "(cb_ai_tagged OR ai_score >= 0.5)",
    # Keyword mention alone — the cheapest baseline.
    "mention":    "(ai_mentioned)",
    # Evidence-based only: a vendor taxonomy tag or a model verdict, no keyword score.
    "evidence":   "(cb_ai_tagged OR llm_ai_verified)",
}

BUCKET = """
CASE verification_status::text
  WHEN 'verified_cb' THEN 'Commercial A'
  WHEN 'verified_pb' THEN 'Commercial B'
  ELSE 'Unlisted'
END"""

# Unlisted firms split by how they entered, for leave-one-out.
CHANNEL = """
CASE
  WHEN grant_first_award_year IS NOT NULL THEN 'public_funder'
  WHEN EXISTS (SELECT 1 FROM incubator_signals s WHERE s.company_id = c.id) THEN 'portfolio_or_accelerator'
  WHEN source_domain IS NOT NULL THEN 'scraped_site'
  ELSE 'code_host_scan'
END"""


def main():
    print("=" * 74)
    print("1. AI share by coverage bucket, four AI definitions")
    print("=" * 74)
    rows = []
    for label, expr in AI_DEFS.items():
        df = q(f"""select {BUCKET} as bucket, count(*) n,
                          count(*) filter (where {expr}) ai
                   from companies c group by 1 order by 2 desc""")
        for _, r in df.iterrows():
            p, lo, hi = wilson(int(r.ai), int(r.n))
            rows.append(dict(ai_definition=label, bucket=r.bucket, n=int(r.n), ai=int(r.ai),
                             ai_pct=round(100 * p, 2), ci_lo=round(100 * lo, 2), ci_hi=round(100 * hi, 2)))
    main_df = pd.DataFrame(rows)
    print(main_df.to_string(index=False))
    save(main_df, "01_ai_share_by_bucket.csv")

    print("\n" + "=" * 74)
    print("2. Unlisted vs each commercial database: difference, CI, odds ratio")
    print("=" * 74)
    comps = []
    for label in AI_DEFS:
        sub = main_df[main_df.ai_definition == label].set_index("bucket")
        u = sub.loc["Unlisted"]
        for other in ("Commercial A", "Commercial B"):
            o = sub.loc[other]
            d, dlo, dhi = diff_ci(int(u.ai), int(u.n), int(o.ai), int(o.n))
            orr, olo, ohi = odds_ratio(int(u.ai), int(u.n), int(o.ai), int(o.n))
            comps.append(dict(ai_definition=label, comparison=f"Unlisted - {other}",
                              diff_pp=round(100 * d, 2), diff_lo=round(100 * dlo, 2),
                              diff_hi=round(100 * dhi, 2), odds_ratio=round(orr, 3),
                              or_lo=round(olo, 3), or_hi=round(ohi, 3)))
    cdf = pd.DataFrame(comps)
    print(cdf.to_string(index=False))
    save(cdf, "02_coverage_gap_tests.csv")

    print("\n" + "=" * 74)
    print("3. Strict unlisted (also absent from the employment database)")
    print("=" * 74)
    strict = q(f"""
      select case
               when verification_status::text = 'verified_cb' then 'Commercial A'
               when verification_status::text = 'verified_pb' then 'Commercial B'
               when naics_code is null then 'Unlisted (strict)'
               else 'Unlisted but on employment DB' end as bucket,
             count(*) n, count(*) filter (where {AI_DEFS['canonical']}) ai_canonical,
             count(*) filter (where {AI_DEFS['pre_llm']}) ai_pre_llm
      from companies c group by 1 order by 2 desc""")
    strict["canonical_pct"] = (100 * strict.ai_canonical / strict.n).round(2)
    strict["pre_llm_pct"] = (100 * strict.ai_pre_llm / strict.n).round(2)
    print(strict.to_string(index=False))
    save(strict, "03_ai_share_strict_buckets.csv")

    print("\n" + "=" * 74)
    print("4. Unlisted layer by entry channel (leave-one-channel-out)")
    print("=" * 74)
    ch = q(f"""select {CHANNEL} as channel, count(*) n,
                      count(*) filter (where {AI_DEFS['canonical']}) ai
               from companies c
               where verification_status::text = 'emerging_github'
               group by 1 order by 2 desc""")
    ch["ai_pct"] = (100 * ch.ai / ch.n).round(2)
    print(ch.to_string(index=False))
    save(ch, "04_unlisted_by_channel.csv")

    tot_n, tot_ai = int(ch.n.sum()), int(ch.ai.sum())
    loo = []
    cb = main_df[(main_df.ai_definition == "canonical") & (main_df.bucket == "Commercial A")].iloc[0]
    pb = main_df[(main_df.ai_definition == "canonical") & (main_df.bucket == "Commercial B")].iloc[0]
    loo.append(dict(dropped="(none)", n=tot_n, ai=tot_ai, ai_pct=round(100 * tot_ai / tot_n, 2),
                    gap_vs_A=round(100 * tot_ai / tot_n - 100 * cb.ai / cb.n, 2),
                    gap_vs_B=round(100 * tot_ai / tot_n - 100 * pb.ai / pb.n, 2)))
    for _, r in ch.iterrows():
        n2, a2 = tot_n - int(r.n), tot_ai - int(r.ai)
        loo.append(dict(dropped=r.channel, n=n2, ai=a2, ai_pct=round(100 * a2 / n2, 2),
                        gap_vs_A=round(100 * a2 / n2 - 100 * cb.ai / cb.n, 2),
                        gap_vs_B=round(100 * a2 / n2 - 100 * pb.ai / pb.n, 2)))
    ldf = pd.DataFrame(loo)
    print("\nLeave-one-channel-out (unlisted AI share, canonical definition):")
    print(ldf.to_string(index=False))
    save(ldf, "05_leave_one_channel_out.csv")

    print("\n" + "=" * 74)
    print("4b. Leave-one-channel-out under COMMON SUPPORT (mention-only)")
    print("=" * 74)
    # The canonical predicate is not available symmetrically: cb_ai_tagged exists
    # only for database-A rows and llm_ai_verified was only ever run on database-B
    # rows, so unlisted firms can satisfy neither. `ai_mentioned` is computed from
    # name+description by the same code for every row, so it is the only predicate
    # applied identically to all three buckets. This is the apples-to-apples test.
    chm = q(f"""select {CHANNEL} as channel, count(*) n,
                       count(*) filter (where {AI_DEFS['mention']}) ai
                from companies c
                where verification_status::text = 'emerging_github'
                group by 1 order by 2 desc""")
    tot_n2, tot_ai2 = int(chm.n.sum()), int(chm.ai.sum())
    cbm = main_df[(main_df.ai_definition == "mention") & (main_df.bucket == "Commercial A")].iloc[0]
    pbm = main_df[(main_df.ai_definition == "mention") & (main_df.bucket == "Commercial B")].iloc[0]
    rows2 = []
    for drop, n2, a2 in [("(none)", tot_n2, tot_ai2)] + [
            (r.channel, tot_n2 - int(r.n), tot_ai2 - int(r.ai)) for _, r in chm.iterrows()]:
        d, dlo, dhi = diff_ci(a2, n2, int(cbm.ai), int(cbm.n))
        orr, olo, ohi = odds_ratio(a2, n2, int(cbm.ai), int(cbm.n))
        rows2.append(dict(dropped=drop, n=n2, ai=a2, ai_pct=round(100 * a2 / n2, 2),
                          gap_vs_A=round(100 * d, 2), gap_lo=round(100 * dlo, 2),
                          gap_hi=round(100 * dhi, 2), odds_ratio=round(orr, 3),
                          or_lo=round(olo, 3), or_hi=round(ohi, 3),
                          gap_vs_B=round(100 * a2 / n2 - 100 * pbm.ai / pbm.n, 2)))
    l2 = pd.DataFrame(rows2)
    print(l2.to_string(index=False))
    save(l2, "05b_leave_one_out_common_support.csv")

    print("\n" + "=" * 74)
    print("4c. Why the 'evidence' predicate reverses: it is source-specific")
    print("=" * 74)
    av = q(f"""select {BUCKET} as bucket, count(*) n,
        round(100.0*count(*) filter (where cb_ai_tagged)/count(*),2) has_vendor_tag,
        round(100.0*count(*) filter (where llm_ai_verified is not null)/count(*),2) has_llm_verdict,
        round(100.0*count(*) filter (where ai_score is not null)/count(*),2) has_score,
        round(100.0*count(*) filter (where description is not null)/count(*),2) has_description
      from companies c group by 1 order by 2 desc""")
    print(av.to_string(index=False))
    print("\nOnly `description` (and therefore ai_mentioned / ai_score) is available")
    print("to every bucket. Vendor tags and LLM verdicts are structurally absent")
    print("from the unlisted layer, so predicates built on them cannot be compared.")
    save(av, "05c_ai_signal_availability_by_bucket.csv")

    print("\n" + "=" * 74)
    print("5. Field coverage by bucket — where the enrichment problem lives")
    print("=" * 74)
    cov = q(f"""select {BUCKET} as bucket, count(*) n,
        round(100.0*count(founded_year)/count(*),1) founded_year,
        round(100.0*count(coalesce(founded_year,cohort_year,grant_first_award_year))/count(*),1) founded_effective,
        round(100.0*count(country)/count(*),1) country,
        round(100.0*count(domain)/count(*),1) domain,
        round(100.0*count(description)/count(*),1) description,
        round(100.0*count(categories)/count(*),1) categories
      from companies c group by 1 order by 2 desc""")
    print(cov.to_string(index=False))
    save(cov, "06_field_coverage_by_bucket.csv")


if __name__ == "__main__":
    main()
