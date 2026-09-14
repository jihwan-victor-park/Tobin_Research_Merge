"""Bias-corrected coverage gap.

The AI label is imperfect and, worse, imperfect by DIFFERENT amounts in each
coverage bucket (experiments/ai_classifier_eval.py). An observed prevalence
difference between buckets can therefore be partly a difference in
classification error rather than in the underlying population.

Rogan-Gladen corrects an observed prevalence for known sensitivity and
specificity:

    p_true = (p_obs + specificity - 1) / (sensitivity + specificity - 1)

Sensitivity and specificity are estimated per bucket from the validation
sample, so the correction is bucket-specific. Confidence intervals come from a
parametric bootstrap that resamples BOTH the validation counts and the
population prevalence.

    railway run -s Postgres -- .venv/bin/python analysis/measurement_correction.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _db import q, save, RESULTS
import numpy as np
import pandas as pd

AI = "(cb_ai_tagged OR ai_score >= 0.5 OR ai_mentioned OR llm_ai_verified)"
B = 20000
RNG = np.random.default_rng(11)


def rogan_gladen(p_obs, sens, spec):
    denom = sens + spec - 1.0
    if denom <= 0:
        return np.nan
    return np.clip((p_obs + spec - 1.0) / denom, 0.0, 1.0)


def main():
    val = pd.read_csv(os.path.join(RESULTS, "60_ai_label_sample.csv"))
    val = val[val.ref_label.isin([0, 1])].copy()
    val["pred"] = (val.cb_tag.astype(bool) | (val.ai_score >= 0.5)
                   | val.ai_mentioned.astype(bool)
                   | val.llm_ai_verified.fillna(False).astype(bool))
    val["ref_label"] = val.ref_label.astype(int)

    # The validation sample was drawn from firms with a description of at least
    # 80 characters. Sensitivity and specificity estimated on that frame are only
    # valid on that frame, so the population prevalence must be measured on it
    # too. (Applying them to all firms -- 53% of the unlisted layer has no
    # description at all -- produced a corrected unlisted rate of 11.3% against a
    # directly measured reference rate of 19.0%, which is how the mismatch was
    # caught.) The corrected numbers therefore describe the DESCRIBED
    # subpopulation, and the paper says so.
    FRAME = "description is not null and length(description) >= 80"
    pop = q(f"""select case verification_status::text
                    when 'verified_cb' then 'Commercial A'
                    when 'verified_pb' then 'Commercial B'
                    else 'Unlisted' end as bucket,
                  count(*) n, count(*) filter (where {AI}) ai
                from companies where {FRAME} group by 1""").set_index("bucket")
    allpop = q(f"""select case verification_status::text
                    when 'verified_cb' then 'Commercial A'
                    when 'verified_pb' then 'Commercial B'
                    else 'Unlisted' end as bucket,
                  count(*) n from companies group by 1""").set_index("bucket")
    print("Validation frame = firms with a description of >=80 characters.")
    for b in pop.index:
        print(f"  {b:<14} {int(pop.loc[b,'n']):>8,} of {int(allpop.loc[b,'n']):>8,} firms "
              f"({100*pop.loc[b,'n']/allpop.loc[b,'n']:.1f}% of the bucket)")
    print()

    print("=" * 78)
    print("Per-bucket classification error, and the corrected prevalence")
    print("=" * 78)
    rows, draws = [], {}
    for b, g in val.groupby("bucket"):
        tp = int(((g.pred) & (g.ref_label == 1)).sum())
        fn = int(((~g.pred) & (g.ref_label == 1)).sum())
        tn = int(((~g.pred) & (g.ref_label == 0)).sum())
        fp = int(((g.pred) & (g.ref_label == 0)).sum())
        sens = tp / (tp + fn) if tp + fn else np.nan
        spec = tn / (tn + fp) if tn + fp else np.nan
        n_pop, ai_pop = int(pop.loc[b, "n"]), int(pop.loc[b, "ai"])
        p_obs = ai_pop / n_pop
        p_cor = rogan_gladen(p_obs, sens, spec)

        # Parametric bootstrap: resample validation counts (Beta on sens/spec)
        # and the population prevalence (Beta on p_obs), then re-correct.
        s_d = RNG.beta(tp + 0.5, fn + 0.5, B)
        c_d = RNG.beta(tn + 0.5, fp + 0.5, B)
        p_d = RNG.beta(ai_pop + 0.5, n_pop - ai_pop + 0.5, B)
        d = np.where(s_d + c_d - 1 > 0, (p_d + c_d - 1) / (s_d + c_d - 1), np.nan)
        d = np.clip(d, 0, 1)
        draws[b] = d
        rows.append(dict(bucket=b, val_n=len(g), sensitivity=round(sens, 3), specificity=round(spec, 3),
                         pop_n=n_pop, observed_ai_pct=round(100 * p_obs, 2),
                         corrected_ai_pct=round(100 * p_cor, 2),
                         corr_lo=round(100 * np.nanpercentile(d, 2.5), 2),
                         corr_hi=round(100 * np.nanpercentile(d, 97.5), 2)))
    res = pd.DataFrame(rows).sort_values("pop_n", ascending=False)
    print(res.to_string(index=False))
    save(res, "07_measurement_corrected_prevalence.csv")

    print("\n" + "=" * 78)
    print("Corrected gap: Unlisted minus each commercial database")
    print("=" * 78)
    grows = []
    for other in ("Commercial A", "Commercial B"):
        d = draws["Unlisted"] - draws[other]
        d = d[~np.isnan(d)]
        obs_gap = (res.set_index("bucket").loc["Unlisted", "observed_ai_pct"]
                   - res.set_index("bucket").loc[other, "observed_ai_pct"])
        grows.append(dict(comparison=f"Unlisted - {other}",
                          observed_gap_pp=round(obs_gap, 2),
                          corrected_gap_pp=round(100 * np.median(d), 2),
                          lo=round(100 * np.percentile(d, 2.5), 2),
                          hi=round(100 * np.percentile(d, 97.5), 2),
                          p_gap_gt_0=round(float((d > 0).mean()), 4)))
    gdf = pd.DataFrame(grows)
    print(gdf.to_string(index=False))
    save(gdf, "08_corrected_coverage_gap.csv")

    print("\nReading: compare the corrected gap and its interval against the raw gap.")
    print("Where the interval excludes zero the difference survives classification")
    print("error; where it does not, the raw gap cannot be separated from a")
    print("difference in how accurately the label works in each bucket.")

    print("\n" + "=" * 78)
    print("Direct check: reference-label prevalence on the validation sample itself")
    print("=" * 78)
    # This needs no correction machinery at all -- it is the reference label's own
    # prevalence, bucket by bucket, on a sample drawn identically from each.
    z = 1.959963984540054
    import math
    direct = []
    for b, g in val.groupby("bucket"):
        x, n = int(g.ref_label.sum()), len(g)
        p = x / n; d = 1 + z**2/n
        c = (p + z**2/(2*n))/d; h = z*math.sqrt(p*(1-p)/n + z**2/(4*n**2))/d
        direct.append(dict(bucket=b, n=n, ai=x, ref_ai_pct=round(100*p, 1),
                           lo=round(100*(c-h), 1), hi=round(100*(c+h), 1)))
    ddf = pd.DataFrame(direct)
    print(ddf.to_string(index=False))
    u = ddf[ddf.bucket == "Unlisted"].iloc[0]
    for other in ("Commercial A", "Commercial B"):
        o = ddf[ddf.bucket == other].iloc[0]
        p1, n1, p2, n2 = u.ai/u.n, u.n, o.ai/o.n, o.n
        pooled = (u.ai + o.ai) / (n1 + n2)
        se = math.sqrt(pooled*(1-pooled)*(1/n1 + 1/n2))
        zstat = (p1 - p2)/se if se else float("nan")
        print(f"  Unlisted vs {other}: {100*(p1-p2):+.1f} pp, z = {zstat:.2f}, "
              f"two-sided p = {2*(1-0.5*(1+math.erf(abs(zstat)/math.sqrt(2)))):.4f}")
    save(ddf, "09_reference_label_direct_comparison.csv")

    print("\n" + "=" * 78)
    print("Sensitivity of the conclusion to the validation sample size")
    print("=" * 78)
    print(f"validation n per bucket: {val.groupby('bucket').size().to_dict()}")
    print("The correction inherits the validation sample's uncertainty; the intervals")
    print("above are dominated by it, not by the population counts. Enlarging the")
    print("labelled set is the cheapest way to tighten them.")


if __name__ == "__main__":
    main()
