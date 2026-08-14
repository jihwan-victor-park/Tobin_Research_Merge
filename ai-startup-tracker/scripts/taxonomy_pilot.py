"""
Taxonomy pilot — discover 'what AI companies really do' bottom-up from their
descriptions, hierarchically, for hidden + published samples.

Pilot uses TF-IDF + KMeans (dependency-light) to prove the pipeline; production
would swap in neural embeddings. Steps:
  cluster   pull corpus, TF-IDF, KMeans(k), print each cluster (size, hidden%, top
            terms, sample names) + save assignments to scratchpad
  (labeling + t-SNE atlas handled in later steps)

    python3 scripts/taxonomy_pilot.py --k 50 --published 15000
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); load_dotenv(ROOT / ".env")
from backend.utils.ai_filter import ai_filter_sql

SCRATCH = Path(os.environ.get("SCRATCH", "/private/tmp/claude-502/-Users-alastairpage-ai-startup-scraper/17db0b8c-2f15-45a0-8e77-b90a1b367338/scratchpad"))
AI = ai_filter_sql()

# domain-noise terms to down-weight (they say nothing about WHAT the company does)
EXTRA_STOP = """ai artificial intelligence machine learning ml platform company solution solutions
using use uses based provides provider technology tech powered driven enable enables help helps
software product products service services business businesses customers users data model models
startup startups build builds building make makes offer offers world leading innovative""".split()


def pull(published_n: int) -> pd.DataFrame:
    eng = create_engine(os.getenv("RAILWAY_DATABASE_URL"))
    hidden = pd.read_sql(text(f"""
        SELECT id, name, description, 'hidden' AS bucket FROM companies
        WHERE {AI} AND verification_status::text='emerging_github'
          AND description IS NOT NULL AND length(description) > 60
    """), eng)
    pub = pd.read_sql(text(f"""
        SELECT id, name, description, 'published' AS bucket FROM companies
        WHERE {AI} AND verification_status::text LIKE 'verified%'
          AND description IS NOT NULL AND length(description) > 60
        ORDER BY random() LIMIT {published_n}
    """), eng)
    df = pd.concat([hidden, pub], ignore_index=True)
    print(f"corpus: {len(df):,}  (hidden {len(hidden):,} + published {len(pub):,})")
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=50)
    ap.add_argument("--published", type=int, default=15000)
    a = ap.parse_args()

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.cluster import MiniBatchKMeans

    df = pull(a.published)
    df["description"] = df["description"].str.slice(0, 1200)

    vec = TfidfVectorizer(ngram_range=(1, 2), max_features=8000, min_df=8, max_df=0.35,
                          stop_words=list(set(EXTRA_STOP)) + ["english"], sublinear_tf=True)
    # (sklearn wants stop_words='english' OR a list; combine by adding english stops)
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
    vec = TfidfVectorizer(ngram_range=(1, 2), max_features=8000, min_df=8, max_df=0.35,
                          stop_words=list(ENGLISH_STOP_WORDS | set(EXTRA_STOP)), sublinear_tf=True)
    X = vec.fit_transform(df["description"].fillna(""))
    print(f"tf-idf matrix: {X.shape}")

    km = MiniBatchKMeans(n_clusters=a.k, random_state=0, n_init=5, batch_size=2048)
    df["cluster"] = km.fit_predict(X)

    terms = np.array(vec.get_feature_names_out())
    centroids = km.cluster_centers_
    print(f"\n=== {a.k} clusters (size | hidden% | top terms | samples) ===")
    rows = []
    for k in range(a.k):
        sub = df[df.cluster == k]
        top = terms[centroids[k].argsort()[::-1][:8]]
        hid = 100 * (sub.bucket == "hidden").mean()
        names = " · ".join(sub.name.dropna().head(3).tolist())
        rows.append((len(sub), hid, k, ", ".join(top), names))
    for n, hid, k, top, names in sorted(rows, reverse=True):
        print(f"  [{k:>2}] n={n:>5} hid={hid:>4.0f}%  {top}")
        print(f"        e.g. {names[:90]}")

    SCRATCH.mkdir(parents=True, exist_ok=True)
    df.to_parquet(SCRATCH / "taxonomy_pilot_assignments.parquet")
    # persist top terms per cluster for the labeling step
    tt = pd.DataFrame({"cluster": range(a.k),
                       "top_terms": [", ".join(terms[centroids[k].argsort()[::-1][:14]]) for k in range(a.k)],
                       "size": [int((df.cluster == k).sum()) for k in range(a.k)],
                       "hidden_pct": [round(100*(df[df.cluster==k].bucket=="hidden").mean(),1) for k in range(a.k)]})
    tt.to_parquet(SCRATCH / "taxonomy_pilot_clusters.parquet")
    print(f"\nsaved assignments + cluster terms to {SCRATCH}")


if __name__ == "__main__":
    main()
