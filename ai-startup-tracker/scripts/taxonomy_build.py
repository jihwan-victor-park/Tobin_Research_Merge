"""
Taxonomy build (production) — neural-embedding version of the pilot, over ALL
AI companies with a real description (hidden + published). Discovers a 2-level
'what they do' hierarchy, assigns every company, writes it to Railway
(company_taxonomy), and renders an atlas on a sample.

Pipeline: pull -> clean (reuse taxonomy_pilot) -> embed (sentence-transformers)
-> KMeans(k) -> LLM-label each cluster into domain(L1)+label(L2)+capability
-> assign all -> persist to Railway + CSV -> t-SNE atlas on a stratified sample.

    python3 scripts/taxonomy_build.py --k 150 --model all-MiniLM-L6-v2
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); load_dotenv(ROOT / ".env")
from backend.utils.ai_filter import ai_filter_sql
from scripts.taxonomy_pilot import clean_and_filter        # reuse cleaning
from scripts.taxonomy_pilot_label import L1, CAP           # reuse label vocab
from scripts.enrich_companies_with_ai import _call_llm, _parse_json

SCRATCH = Path("/private/tmp/claude-502/-Users-alastairpage-ai-startup-scraper/17db0b8c-2f15-45a0-8e77-b90a1b367338/scratchpad")
AI = ai_filter_sql()


def pull_all(chunk: int = 20000) -> pd.DataFrame:
    """Chunked, retrying pull — Railway's proxy hangs a single 117K-row read, so
    read short id-ranges over fresh keepalive connections and retry on drop."""
    import time
    import psycopg2
    url = os.getenv("RAILWAY_DATABASE_URL")
    ka = dict(connect_timeout=20, keepalives=1, keepalives_idle=20,
              keepalives_interval=10, keepalives_count=5)

    def q(sql: str) -> pd.DataFrame:
        last = None
        for attempt in range(6):
            try:
                conn = psycopg2.connect(url, **ka)
                try:
                    return pd.read_sql(sql, conn)
                finally:
                    conn.close()
            except Exception as ex:  # dropped/timed-out -> retry a fresh connection
                last = ex; print(f"    retry {attempt}: {type(ex).__name__}", flush=True); time.sleep(3)
        raise RuntimeError(f"pull failed after retries: {last}")

    max_id = int(q(f"SELECT COALESCE(max(id),0) m FROM companies WHERE {AI}")["m"][0])
    parts, total = [], 0
    for lo in range(0, max_id + 1, chunk):
        d = q(f"""SELECT id, name, description,
              CASE WHEN verification_status::text LIKE 'verified%' THEN 'published'
                   WHEN verification_status::text='emerging_github' THEN 'hidden'
                   ELSE 'other' END AS bucket
            FROM companies WHERE {AI} AND description IS NOT NULL AND length(description) > 60
              AND id >= {lo} AND id < {lo + chunk}""")
        parts.append(d); total += len(d)
        print(f"  pulled id<{lo + chunk:>7}: +{len(d):<5} (total {total:,})", flush=True)
    df = pd.concat(parts, ignore_index=True)
    print(f"pulled {len(df):,} AI companies with a description")
    return df


def label_cluster(cid, terms, samples):
    prompt = (
        f"A cluster of AI companies. Representative name/description snippets:\n- "
        + "\n- ".join(s[:200] for s in samples) + "\n\n"
        f"Pick DOMAIN from: {L1}\nPick CAPABILITY from: {CAP}\n"
        "Return ONLY JSON: {\"label\":\"2-4 word name of what they DO\","
        "\"domain\":<DOMAIN>,\"capability\":<CAP>,\"is_noise\":true|false} "
        "is_noise=true only if boilerplate (grant/social/HTML), not real products."
    )
    d = _parse_json(_call_llm([{"role": "user", "content": prompt}], temperature=0.0) or "")
    if isinstance(d, list):
        d = next((x for x in d if isinstance(x, dict)), None)
    if not isinstance(d, dict) or "domain" not in d:
        d = {"label": "?", "domain": "Other", "capability": "Other", "is_noise": False}
    return cid, d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=150)
    ap.add_argument("--model", default="all-MiniLM-L6-v2")
    ap.add_argument("--write", action="store_true", help="persist company_taxonomy to Railway")
    a = ap.parse_args()

    corpus_p, emb_p = SCRATCH / "taxonomy_corpus.parquet", SCRATCH / "taxonomy_emb.npy"
    if corpus_p.exists() and emb_p.exists():
        df = pd.read_parquet(corpus_p); emb = np.load(emb_p)
        print(f"loaded cached corpus ({len(df):,}) + embeddings — skipping pull/embed")
    else:
        df = clean_and_filter(pull_all()).reset_index(drop=True)
        texts = (df["name"].fillna("") + ". " + df["description"].str.slice(0, 900)).tolist()
        print(f"embedding {len(texts):,} with {a.model} ...")
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(a.model)
        emb = model.encode(texts, batch_size=256, show_progress_bar=True,
                           convert_to_numpy=True, normalize_embeddings=True)
        df.to_parquet(corpus_p); np.save(emb_p, emb)

    from sklearn.cluster import MiniBatchKMeans
    print(f"clustering into k={a.k} ...")
    km = MiniBatchKMeans(n_clusters=a.k, random_state=0, n_init=5, batch_size=4096)
    df["cluster"] = km.fit_predict(emb)

    # representative snippets per cluster (closest to centroid)
    reps = {}
    for k in range(a.k):
        idx = np.where(df["cluster"].values == k)[0]
        if len(idx) == 0:
            reps[k] = []
            continue
        sims = emb[idx] @ km.cluster_centers_[k]
        top = idx[np.argsort(sims)[::-1][:8]]
        reps[k] = [f"{df.iloc[i]['name']}: {str(df.iloc[i]['description'])[:180]}" for i in top]

    print(f"LLM-labeling {a.k} clusters ...")
    labels = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(label_cluster, k, None, reps[k]) for k in range(a.k)]
        for f in as_completed(futs):
            cid, d = f.result(); labels[cid] = d
    lab = pd.DataFrame([{"cluster": k, **v} for k, v in labels.items()])
    df = df.merge(lab, on="cluster")

    real = df[~df.is_noise]
    print(f"\nnoise clusters: {df.is_noise.sum()} rows flagged")
    print(f"companies mapped: {len(real):,}  domains: {real.domain.nunique()}  clusters: {real.cluster.nunique()}")
    print("\n=== domain sizes (hidden share) ===")
    g = real.groupby("domain").agg(n=("id", "size"), hidden=("bucket", lambda s: round(100*(s == "hidden").mean(), 0)))
    print(g.sort_values("n", ascending=False).to_string())

    # persist assignments
    keep = df[["id", "name", "bucket", "cluster", "domain", "label", "capability", "is_noise"]]
    keep.to_parquet(SCRATCH / "taxonomy_full_assignments.parquet")
    # aggregate CSVs (committable)
    real.groupby(["domain", "label"]).agg(
        n=("id", "size"), hidden_pct=("bucket", lambda s: round(100*(s == "hidden").mean(), 1)),
        capability=("capability", "first")).reset_index().to_csv(ROOT / "output" / "48_taxonomy_full_hierarchy.csv", index=False)
    g.reset_index().to_csv(ROOT / "output" / "49_taxonomy_full_domain_tilt.csv", index=False)
    print("saved -> output/48_taxonomy_full_hierarchy.csv, 49_taxonomy_full_domain_tilt.csv")

    if a.write:
        write_railway(keep)
    render_atlas(df, emb)


def write_railway(keep: pd.DataFrame) -> None:
    import psycopg2, psycopg2.extras
    url = os.getenv("RAILWAY_DATABASE_URL")
    conn = psycopg2.connect(url); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS company_taxonomy (
        company_id INTEGER PRIMARY KEY, domain_l1 VARCHAR(48), cluster_label VARCHAR(80),
        capability VARCHAR(40), cluster_id INTEGER, is_noise BOOLEAN)""")
    conn.commit()
    rows = [(int(r.id), r.domain, r.label, r.capability, int(r.cluster), bool(r.is_noise))
            for r in keep.itertuples()]
    sql = ("INSERT INTO company_taxonomy (company_id,domain_l1,cluster_label,capability,cluster_id,is_noise) "
           "VALUES %s ON CONFLICT (company_id) DO UPDATE SET domain_l1=EXCLUDED.domain_l1, "
           "cluster_label=EXCLUDED.cluster_label, capability=EXCLUDED.capability, "
           "cluster_id=EXCLUDED.cluster_id, is_noise=EXCLUDED.is_noise")
    psycopg2.extras.execute_values(cur, sql, rows, page_size=2000); conn.commit(); conn.close()
    print(f"wrote company_taxonomy to Railway ({len(rows):,} rows)")


def render_atlas(df: pd.DataFrame, emb: np.ndarray) -> None:
    print("rendering atlas (t-SNE on stratified sample)...")
    real = df[~df.is_noise].copy()
    real_idx = real.index.values
    samp = real.sample(min(18000, len(real)), random_state=0).index.values
    from sklearn.manifold import TSNE
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    xy = TSNE(n_components=2, random_state=0, perplexity=40, init="pca").fit_transform(emb[samp])
    s = df.loc[samp].copy(); s["x"], s["y"] = xy[:, 0], xy[:, 1]
    doms = sorted(s.domain.unique())
    cmap = plt.get_cmap("tab20", len(doms))
    fig, ax = plt.subplots(figsize=(15, 11))
    for i, d in enumerate(doms):
        sd = s[s.domain == d]
        ax.scatter(sd.x, sd.y, s=5, color=cmap(i), label=f"{d} ({len(sd)})", alpha=0.55, linewidths=0)
    h = s[s.bucket == "hidden"]
    ax.scatter(h.x, h.y, s=16, facecolors="none", edgecolors="black", linewidths=0.35, alpha=0.5)
    ax.set_title("What AI companies do — neural-embedding atlas (color=domain, o=hidden)", fontsize=14)
    ax.set_xticks([]); ax.set_yticks([])
    ax.legend(markerscale=2, fontsize=8, loc="center left", bbox_to_anchor=(1, 0.5))
    fig.tight_layout(); fig.savefig(SCRATCH / "taxonomy_atlas_full.png", dpi=110, bbox_inches="tight")
    print(f"saved atlas -> {SCRATCH / 'taxonomy_atlas_full.png'}")


if __name__ == "__main__":
    main()
