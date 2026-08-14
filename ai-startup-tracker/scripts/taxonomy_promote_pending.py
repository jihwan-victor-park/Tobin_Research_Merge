"""
Promote 'pending' hidden companies to mapped using Victor's ai_application/
ai_subfield — but ONLY where those categories confidently predict a domain.

We learn, from the hidden companies already text-mapped, which (ai_application,
ai_subfield) combos land reliably in one domain. Pending companies (no usable
text) that carry such a confident combo are promoted to status='category_mapped'
with that domain + capability + the combo's modal cluster label. Companies whose
combo is ambiguous (plurality < threshold) stay pending — guessing there would
pollute the map. Updates the parquet + Railway company_taxonomy.

    python3 scripts/taxonomy_promote_pending.py --write --min-plurality 0.55
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); load_dotenv(ROOT / ".env")
S = Path("/private/tmp/claude-502/-Users-alastairpage-ai-startup-scraper/17db0b8c-2f15-45a0-8e77-b90a1b367338/scratchpad")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--min-plurality", type=float, default=0.55)
    ap.add_argument("--min-support", type=int, default=15)
    a = ap.parse_args()

    f = pd.read_parquet(S / "taxonomy_full_with_hidden.parquet")

    # reset any prior promotion so this is idempotent / re-runnable
    prev = f.status == "category_mapped"
    if prev.any():
        f.loc[prev, "status"] = "pending"
        f.loc[prev, "domain"] = "Pending enrichment"
        f.loc[prev, "label"] = f.loc[prev, "ai_subfield"].fillna(f.loc[prev, "ai_application"]).fillna("unclassified")
        f.loc[prev, "capability"] = "Other"; f.loc[prev, "cluster"] = -1

    # learn combo -> domain from text-mapped hidden (only they have both signals).
    # require a REAL ai_subfield (a known capability) — 'other' carries no signal.
    train = f[(f.bucket == "hidden") & (f.status == "mapped")
              & f.ai_subfield.notna() & (f.ai_subfield != "other")]
    def modal(s): return s.value_counts().index[0]
    def plur(s): return s.value_counts(normalize=True).iloc[0]
    look = train.groupby(["ai_application", "ai_subfield"]).agg(
        n=("id", "size"), domain=("domain", modal), plurality=("domain", plur),
        capability=("capability", modal), label=("label", modal),
        cluster=("cluster", modal)).reset_index()
    good = look[(look.plurality >= a.min_plurality) & (look.n >= a.min_support)
                & (look.ai_subfield != "other")]
    print(f"confident combos (plurality>={a.min_plurality}, n>={a.min_support}): "
          f"{len(good)}/{len(look)}")

    pend = f[f.status == "pending"].copy()
    cand = pend[pend.ai_subfield.notna()].merge(
        good[["ai_application", "ai_subfield", "domain", "capability", "label", "cluster"]],
        on=["ai_application", "ai_subfield"], how="left", suffixes=("", "_new"))
    promote = cand[cand.domain_new.notna()].copy()
    print(f"pending: {len(pend):,} | with a category: {int(pend.ai_subfield.notna().sum()):,} | "
          f"promotable (confident combo): {len(promote):,}")

    # id -> (domain, capability, label, cluster) promotion map
    promo = {int(r.id): (r.domain_new, r.capability_new, r.label, int(r.cluster_new))
             for r in promote.itertuples()}

    # supplement: ai_application == 'healthcare' is a real domain (79% reliable)
    hc = f[(f.bucket == "hidden") & (f.status == "mapped") & (f.domain == "Healthcare")]
    hc_cluster = int(hc.cluster.value_counts().index[0])
    hc_label = hc[hc.cluster == hc_cluster].label.mode().iloc[0]
    n_hc = 0
    for r in pend[pend.ai_application == "healthcare"].itertuples():
        if int(r.id) not in promo:
            promo[int(r.id)] = ("Healthcare", "Other", hc_label, hc_cluster); n_hc += 1
    print(f"+ healthcare-application promotions: {n_hc}")

    def upd(row):
        if row["id"] in promo and row["status"] == "pending":
            dom, cap, lab, cl = promo[row["id"]]
            row["domain"] = dom; row["capability"] = cap
            row["label"] = lab; row["cluster"] = cl
            row["status"] = "category_mapped"
        return row
    f = f.apply(upd, axis=1)

    print("\n=== status after promotion ===")
    print(f.groupby(["bucket", "status"]).size().to_string())
    hid = f[f.bucket == "hidden"]
    still = int((hid.status == "pending").sum())
    print(f"\nhidden: mapped {int((hid.status=='mapped').sum()):,} | "
          f"category_mapped {int((hid.status=='category_mapped').sum()):,} | pending {still:,}")
    print(f"hidden NON-pending now: {len(hid)-still:,} / {len(hid):,} "
          f"({100*(len(hid)-still)/len(hid):.0f}%)")

    f.to_parquet(S / "taxonomy_full_with_hidden.parquet")
    if a.write:
        from scripts.taxonomy_add_hidden import _write
        _write(f)
    print("done")


if __name__ == "__main__":
    main()
