"""
Taxonomy re-label — fix the labeling layer without re-embedding/re-clustering.

Verification showed the k=150 clusters are coherent, but LLM labels/domains were
wrong (labeled from only 8 members, no distinctive terms; false-positive noise).
This re-labels each cluster with MORE context: 20 nearest-centroid members +
the cluster's most distinctive TF-IDF terms, a majority-fit rule, an explicit
'Mixed' escape, and NO aggressive noise flag (corpus cleaning already removed
boilerplate). Reads cached corpus + embeddings + cluster ids; rewrites labels to
the assignments parquet, Railway company_taxonomy, and the CSVs.

    python3 scripts/taxonomy_relabel.py --write
"""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); load_dotenv(ROOT / ".env")
from scripts.taxonomy_pilot_label import L1, CAP
from scripts.enrich_companies_with_ai import _call_llm, _parse_json

S = Path("/private/tmp/claude-502/-Users-alastairpage-ai-startup-scraper/17db0b8c-2f15-45a0-8e77-b90a1b367338/scratchpad")


def label(cid, members, terms):
    prompt = (
        f"One cluster of AI companies. Its most distinctive words: {terms}.\n"
        f"{len(members)} representative companies (name: description):\n- "
        + "\n- ".join(m[:170] for m in members) + "\n\n"
        f"Choose the DOMAIN that fits the MAJORITY, from: {L1}\n"
        f"Choose the CAPABILITY (main AI method) that fits the majority, from: {CAP}\n"
        "Give a LABEL (2-5 words) naming what the MAJORITY do — general enough to fit most, "
        "not a detail from one company. If the companies are genuinely unrelated, set "
        "label='Mixed / General AI' and domain='Other'.\n"
        "Return ONLY JSON: {\"label\":..., \"domain\":<DOMAIN>, \"capability\":<CAP>}"
    )
    d = _parse_json(_call_llm([{"role": "user", "content": prompt}], temperature=0.0) or "")
    if isinstance(d, list):
        d = next((x for x in d if isinstance(x, dict)), None)
    if not isinstance(d, dict) or d.get("domain") not in L1:
        d = {"label": "Mixed / General AI", "domain": "Other", "capability": "Other"}
    return cid, d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    corpus = pd.read_parquet(S / "taxonomy_corpus.parquet").reset_index(drop=True)
    assign = pd.read_parquet(S / "taxonomy_full_assignments.parquet").reset_index(drop=True)
    emb = np.load(S / "taxonomy_emb.npy")
    assert len(corpus) == len(emb) == len(assign)
    corpus["cluster"] = assign["cluster"].values

    # distinctive terms per cluster (TF-IDF, top by cluster-mean weight vs global)
    from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS
    stop = list(ENGLISH_STOP_WORDS | set("ai artificial intelligence machine learning platform "
               "company solution using data provider technology powered driven based".split()))
    vec = TfidfVectorizer(ngram_range=(1, 2), max_features=12000, min_df=6, max_df=0.4, stop_words=stop)
    X = vec.fit_transform(corpus["description"].fillna("").str.slice(0, 1000))
    terms = np.array(vec.get_feature_names_out())

    clusters = sorted(corpus["cluster"].unique())
    ctx = {}
    for cl in clusters:
        idx = np.where(corpus["cluster"].values == cl)[0]
        cen = emb[idx].mean(0); cen /= np.linalg.norm(cen) + 1e-9
        near = idx[np.argsort(emb[idx] @ cen)[::-1][:20]]
        members = [f"{corpus.iloc[i]['name']}: {str(corpus.iloc[i]['description'])[:150]}" for i in near]
        tw = np.asarray(X[idx].mean(0)).ravel()
        top = ", ".join(terms[tw.argsort()[::-1][:12]])
        ctx[cl] = (members, top)

    print(f"re-labeling {len(clusters)} clusters (20 members + distinctive terms each)...")
    out = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(label, cl, *ctx[cl]) for cl in clusters]
        for f in as_completed(futs):
            cid, d = f.result(); out[cid] = d
    lab = pd.DataFrame([{"cluster": k, "label": v["label"], "domain": v["domain"],
                         "capability": v.get("capability", "Other")} for k, v in out.items()])
    new = assign.drop(columns=["label", "domain", "capability", "is_noise"], errors="ignore").merge(lab, on="cluster")
    new["is_noise"] = False
    new.to_parquet(S / "taxonomy_full_assignments.parquet")

    print(f"\nmapped {len(new):,} companies | domains {new.domain.nunique()} | "
          f"'Mixed/Other' {int((new.domain=='Other').sum()):,}")
    g = new.groupby("domain").agg(n=("id", "size")).sort_values("n", ascending=False)
    print(g.to_string())

    new.groupby(["domain", "label"]).agg(n=("id", "size"), capability=("capability", "first")).reset_index()\
        .to_csv(ROOT / "output" / "48_taxonomy_full_hierarchy.csv", index=False)
    if a.write:
        from scripts.taxonomy_build import write_railway
        write_railway(new[["id", "name", "bucket", "cluster", "domain", "label", "capability", "is_noise"]])
    print("done")


if __name__ == "__main__":
    main()
