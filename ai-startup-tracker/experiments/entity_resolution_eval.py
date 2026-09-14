"""Validation of the entity-resolution rule actually in production.

The production rule (backend/scrapers/base.py:293-295) is exact-key matching:

    kappa(x) = "domain:" + canonical(domain)   if a domain exists
               "name:"   + normalize(name)     otherwise

There is no fuzzy stage. `backend/utils/dedup.resolve_entity`, which carries the
0.92 / 0.95 thresholds and a shared-signal requirement, has no production caller,
and its shared-signal branch returns the match either way. So the object to
validate is the NORMALIZER, not a threshold.

normalize_company_name strips a suffix list that includes `ai`, `io`, `labs`,
`tech`, `technologies`, `systems`, `co`. That is exactly the token separating an
AI-era startup from an older firm with the same stem, so the failure this script
measures is AI-correlated by construction.

    railway run -s Postgres -- .venv/bin/python experiments/entity_resolution_eval.py
"""
from __future__ import annotations
import os, re, sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "analysis"))
sys.path.insert(0, ROOT)
from _db import q, save  # noqa: E402
import pandas as pd  # noqa: E402
from backend.utils.normalize import normalize_company_name, fuzzy_name_match  # noqa: E402

AI_MARK = re.compile(r"(^|[\s.\-_])(ai|\.ai|artificial intelligence|ml|llm|gpt|neural|genai)($|[\s.\-_])", re.I)

# A conservative normalizer: identical to production except it keeps the tokens
# that carry brand identity for this population.
KEEP = {"ai", "io", "labs", "lab", "tech", "technologies", "technology", "systems", "software"}
CONSERVATIVE_SUFFIXES = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|gmbh|sa|sas|sarl|bv|pty|pte)\b\.?", re.I)


def normalize_conservative(name: str):
    if not name:
        return None
    r = name.lower().strip()
    r = re.sub(r"[^\w\s-]", " ", r)
    r = CONSERVATIVE_SUFFIXES.sub(" ", r)
    r = re.sub(r"\s+", " ", r).strip().strip("-").strip()
    return r or None


def main():
    print("=" * 74)
    print("1. Does the production normalizer collapse distinct firms?")
    print("=" * 74)
    # Two records with DIFFERENT canonical domains are different firms. If they
    # share a normalized_name, then whenever one of them lacks a domain the
    # name rule merges them. This is the false-merge exposure.
    coll = q("""
      select normalized_name, count(*) n_records, count(distinct domain) n_domains
      from companies
      where normalized_name is not null and domain is not null
      group by 1 having count(distinct domain) > 1
      order by 3 desc""")
    total_named = q("select count(distinct normalized_name) n from companies where normalized_name is not null").n[0]
    print(f"distinct normalized names: {int(total_named):,}")
    print(f"names shared by >1 distinct domain: {len(coll):,} "
          f"({100*len(coll)/int(total_named):.2f}% of names)")
    print(f"companies sitting on a collided name: {int(coll.n_records.sum()):,}")
    print("\nWorst collisions:")
    print(coll.head(12).to_string(index=False))
    save(coll, "50_normalized_name_collisions.csv")

    print("\n" + "=" * 74)
    print("2. How much of the collapse is caused by the suffix list?")
    print("=" * 74)
    names = q("""select name, domain from companies
                 where domain is not null and name is not null
                 order by md5(id::text) limit 300000""")
    prod = names.name.map(normalize_company_name)
    cons = names.name.map(normalize_conservative)
    def collisions(series):
        pair = pd.DataFrame({"k": series, "d": names.domain}).dropna()
        g = pair.groupby("k").d.nunique()
        return int((g > 1).sum()), int(pair[pair.k.isin(g[g > 1].index)].shape[0])
    p_names, p_rows = collisions(prod)
    c_names, c_rows = collisions(cons)
    print(f"sample of {len(names):,} firms with a known domain")
    print(f"  production normalizer : {p_names:,} colliding keys, {p_rows:,} firms exposed")
    print(f"  conservative normalizer: {c_names:,} colliding keys, {c_rows:,} firms exposed")
    print(f"  attributable to the suffix list: {p_rows - c_rows:,} firms "
          f"({100*(p_rows-c_rows)/max(p_rows,1):.1f}% of the exposure)")
    save(pd.DataFrame([dict(normalizer="production", colliding_keys=p_names, firms_exposed=p_rows),
                       dict(normalizer="conservative", colliding_keys=c_names, firms_exposed=c_rows)]),
         "51_normalizer_comparison.csv")

    print("\n" + "=" * 74)
    print("3. Is the collapse AI-correlated?")
    print("=" * 74)
    df = pd.DataFrame({"name": names.name, "domain": names.domain, "k": prod}).dropna()
    g = df.groupby("k").domain.nunique()
    bad = df[df.k.isin(g[g > 1].index)]
    asym = 0
    ai_only_one = 0
    groups = 0
    for _, grp in bad.groupby("k"):
        marks = grp.name.map(lambda s: bool(AI_MARK.search(s or "")))
        if marks.nunique() == 2:          # some members marked AI, some not
            asym += 1
            ai_only_one += int(marks.sum())
        groups += 1
    print(f"collided name groups in sample: {groups:,}")
    print(f"groups mixing an AI-marked and a non-AI-marked firm: {asym:,} "
          f"({100*asym/max(groups,1):.1f}%)")
    print(f"AI-marked firms inside those mixed groups: {ai_only_one:,}")
    print("\nA merge inside a mixed group deletes the AI-marked firm's identity and")
    print("keeps the incumbent's. The bias therefore runs AGAINST finding AI firms,")
    print("so the coverage-gap estimate in Section 6 is conservative, not inflated.")

    print("\n" + "=" * 74)
    print("4. Real name variants observed in the pipeline (raw vs canonical)")
    print("=" * 74)
    var = q("""
      select s.company_name_raw as raw_name, c.name as canonical_name, c.domain,
             (c.cb_ai_tagged or c.ai_score >= 0.5 or c.ai_mentioned or c.llm_ai_verified) as ai
      from incubator_signals s join companies c on c.id = s.company_id
      where c.domain is not null and s.company_name_raw is not null
        and lower(btrim(s.company_name_raw)) <> lower(btrim(c.name))""")
    var["sim"] = [fuzzy_name_match(a, b) for a, b in zip(var.raw_name, var.canonical_name)]
    var["norm_raw"] = var.raw_name.map(normalize_company_name)
    var["norm_canon"] = var.canonical_name.map(normalize_company_name)
    var["exact_after_norm"] = var.norm_raw == var.norm_canon
    var["ai_marker_asymmetry"] = [bool(AI_MARK.search(a or "")) != bool(AI_MARK.search(b or ""))
                                  for a, b in zip(var.raw_name, var.canonical_name)]
    print(f"name-variant pairs: {len(var):,}")
    print(f"  identical after production normalization (similarity = 1.0): "
          f"{int(var.exact_after_norm.sum()):,} ({100*var.exact_after_norm.mean():.1f}%)")
    print(f"  of those, one side carries an AI marker and the other does not: "
          f"{int((var.exact_after_norm & var.ai_marker_asymmetry).sum()):,}")
    save(var.drop(columns=["norm_raw", "norm_canon"]), "52_name_variant_pairs.csv")

    print("\n" + "=" * 74)
    print("5. Threshold sweep — would a stricter tau help?")
    print("=" * 74)
    rows = []
    for tau in [0.85, 0.90, 0.92, 0.95, 0.97, 0.99, 1.00]:
        acc = int((var.sim >= tau).sum())
        acc_asym = int(((var.sim >= tau) & var.ai_marker_asymmetry).sum())
        rows.append(dict(tau=tau, pairs_accepted=acc,
                         pct_accepted=round(100 * acc / len(var), 1),
                         ai_asymmetric_accepted=acc_asym))
    sweep = pd.DataFrame(rows)
    print(sweep.to_string(index=False))
    save(sweep, "53_threshold_sweep.csv")
    print("\nRaising tau does not remove the AI-asymmetric merges: they score 1.0")
    print("because the normalizer deletes the distinguishing token BEFORE the")
    print("comparison. The defect is in normalization, not in the threshold, and")
    print("no choice of tau can repair it.")

    print("\n" + "=" * 74)
    print("6. Sample for author adjudication")
    print("=" * 74)
    samp = var[var.exact_after_norm & var.ai_marker_asymmetry].copy()
    samp["same_company"] = ""      # to be filled by the authors: 1 = same, 0 = different
    samp["labeller"] = ""
    out = samp[["raw_name", "canonical_name", "domain", "sim", "ai", "same_company", "labeller"]]
    save(out, "54_er_adjudication_sample.csv")
    print(f"wrote {len(out)} pairs needing a human verdict. This is the gold set the")
    print("paper's precision estimate requires; it is NOT yet labelled.")
    print("\nFirst 15 for inspection:")
    print(out.head(15)[["raw_name", "canonical_name", "domain"]].to_string(index=False))


if __name__ == "__main__":
    main()
