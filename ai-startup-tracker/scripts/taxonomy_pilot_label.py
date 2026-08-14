"""
Taxonomy pilot step 2 — LLM-label the discovered clusters into a 2-level
hierarchy (domain L1 -> cluster label L2), flag scraping-noise clusters, and
render the t-SNE atlas (hidden vs published overlaid).

    python3 scripts/taxonomy_pilot_label.py
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); load_dotenv(ROOT / ".env")
from scripts.enrich_companies_with_ai import _call_llm, _parse_json

SCRATCH = Path("/private/tmp/claude-502/-Users-alastairpage-ai-startup-scraper/17db0b8c-2f15-45a0-8e77-b90a1b367338/scratchpad")

L1 = ["Healthcare", "Finance", "Legal", "Security", "Marketing/Media", "Retail/Commerce",
      "Education", "Science/Research", "Energy/Climate", "Manufacturing/Industrial",
      "Developer Tools/Infra", "Productivity/Work", "Data/Analytics", "Robotics/Hardware",
      "Consumer/Lifestyle", "Government/Public", "Agriculture/Food", "Transport/Logistics", "Other"]
CAP = ["LLM/NLP", "Computer Vision", "Agents", "Predictive/Analytics", "Generative Media",
       "Robotics", "Speech/Audio", "ML Infra", "Other"]


def label_cluster(row, samples):
    prompt = (
        "A cluster of AI companies, grouped by their descriptions.\n"
        f"Top terms: {row['top_terms']}\n"
        f"Example descriptions:\n- " + "\n- ".join(s[:200] for s in samples) + "\n\n"
        f"Pick the DOMAIN (what they serve) from: {L1}\n"
        f"Pick the CAPABILITY (main AI method) from: {CAP}\n"
        "Return ONLY JSON: {\"label\": \"2-4 word name of what these companies DO\", "
        "\"domain\": <one from DOMAIN>, \"capability\": <one from CAP>, "
        "\"is_noise\": true|false}  "
        "is_noise=true ONLY if the cluster is scraping boilerplate (government grant text, "
        "social-media/HuggingFace metadata, HTML junk) rather than real product descriptions."
    )
    data = _parse_json(_call_llm([{"role": "user", "content": prompt}], temperature=0.0) or "")
    if not data:
        return {"label": "?", "domain": "Other", "capability": "Other", "is_noise": False}
    return data


def main() -> None:
    clusters = pd.read_parquet(SCRATCH / "taxonomy_pilot_clusters.parquet")
    assign = pd.read_parquet(SCRATCH / "taxonomy_pilot_assignments.parquet")
    samples = {k: assign[assign.cluster == k]["description"].dropna().head(6).tolist()
               for k in clusters.cluster}

    print(f"labeling {len(clusters)} clusters with Haiku...")
    out = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(label_cluster, r, samples[r["cluster"]]): r["cluster"]
                for _, r in clusters.iterrows()}
        for f in as_completed(futs):
            out[futs[f]] = f.result()
    lab = pd.DataFrame([{"cluster": k, **v} for k, v in out.items()])
    clusters = clusters.merge(lab, on="cluster")
    clusters.to_parquet(SCRATCH / "taxonomy_pilot_labeled.parquet")

    real = clusters[~clusters.is_noise]
    noise = clusters[clusters.is_noise]
    print(f"\n{len(noise)} noise clusters flagged ({noise['size'].sum():,} companies) — "
          f"{', '.join(noise.label.head(6))}")

    print("\n=== DISCOVERED HIERARCHY (domain -> cluster) ===")
    for dom in sorted(real.domain.unique()):
        d = real[real.domain == dom].sort_values("size", ascending=False)
        print(f"\n{dom}  ({d['size'].sum():,} companies)")
        for _, r in d.iterrows():
            print(f"   - {r['label']:32s} n={r['size']:>5}  hidden={r['hidden_pct']:>4.0f}%  [{r['capability']}]")

    # hidden vs published tilt by domain
    assign = assign.merge(clusters[["cluster", "domain", "is_noise"]], on="cluster")
    real_a = assign[~assign.is_noise]
    tab = (real_a.groupby(["domain", "bucket"]).size().unstack(fill_value=0))
    tab["hidden_share_%"] = (100 * tab.get("hidden", 0) / tab.sum(axis=1)).round(0)
    tab = tab.sort_values("hidden_share_%", ascending=False)
    print("\n=== hidden vs published tilt by domain (real clusters only) ===")
    print(tab.to_string())
    tab.to_csv(ROOT / "output" / "47_taxonomy_pilot_domain_tilt.csv")

    # ---- t-SNE atlas ----
    print("\nrendering atlas (SVD -> t-SNE)...")
    from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS
    from sklearn.decomposition import TruncatedSVD
    from sklearn.manifold import TSNE
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    extra = "ai artificial intelligence machine learning platform company solution using data".split()
    vec = TfidfVectorizer(ngram_range=(1, 2), max_features=8000, min_df=8, max_df=0.35,
                          stop_words=list(ENGLISH_STOP_WORDS | set(extra)), sublinear_tf=True)
    X = vec.fit_transform(assign["description"].fillna("").str.slice(0, 1200))
    svd = TruncatedSVD(n_components=50, random_state=0).fit_transform(X)
    xy = TSNE(n_components=2, random_state=0, perplexity=35, init="pca").fit_transform(svd)
    assign["x"], assign["y"] = xy[:, 0], xy[:, 1]

    plot = assign[~assign.is_noise]
    doms = sorted(plot.domain.unique())
    cmap = plt.get_cmap("tab20", len(doms))
    fig, ax = plt.subplots(figsize=(15, 11))
    for i, dom in enumerate(doms):
        d = plot[plot.domain == dom]
        ax.scatter(d.x, d.y, s=5, color=cmap(i), label=f"{dom} ({len(d)})", alpha=0.55, linewidths=0)
    # outline hidden companies
    h = plot[plot.bucket == "hidden"]
    ax.scatter(h.x, h.y, s=16, facecolors="none", edgecolors="black", linewidths=0.35, alpha=0.5)
    ax.set_title("What AI companies do — TF-IDF atlas (color=domain, ○=hidden)", fontsize=14)
    ax.set_xticks([]); ax.set_yticks([])
    ax.legend(markerscale=2, fontsize=8, loc="center left", bbox_to_anchor=(1, 0.5))
    fig.tight_layout()
    out_png = SCRATCH / "taxonomy_atlas.png"
    fig.savefig(out_png, dpi=110, bbox_inches="tight")
    print(f"saved atlas -> {out_png}")


if __name__ == "__main__":
    main()
