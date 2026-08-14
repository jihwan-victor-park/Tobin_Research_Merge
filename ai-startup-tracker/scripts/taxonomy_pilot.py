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
import html
import os
import re
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
startup startups build builds building make makes offer offers world leading innovative
nan specializes develops developer designed enabling clients located industry companies""".split()


# ── corpus cleaning: strip scraping boilerplate that clustered as noise ──
_URLS = re.compile(r"https?://\S+|www\.\S+|\b\S+\.com\S*|twitter\s+com|https\s+twitter", re.I)
_ENTITY = re.compile(r"\b(x2f|x27|x3d|x2d|x3a|x26|quot|amp|nbsp|gt|lt|apos|8217|8220|8221)\b", re.I)
_BOILER = re.compile(
    r"sbir|sttr|awardee|framework programme|participant sme|horizon 2020|\bh2020\b|"
    r"hugging\s*face organization|\d+\s+followers|followers twitter|eu framework|"
    r"project\s+20\d{2}|20\d{2}\s+project", re.I)


def clean_text(t: str) -> str:
    if not t:
        return ""
    t = html.unescape(str(t))
    t = _URLS.sub(" ", t)
    t = _ENTITY.sub(" ", t)
    t = _BOILER.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


# grant/award abstracts are not product descriptions — detect and drop wholesale
_GRANT_STRONG = ("sbir", "sttr", "framework programme", "horizon 2020", "department of defense",
                 "grant agreement", "cordis", "awardee", "defense award", "phase ii project",
                 "european commission", "department of commerce", "commerce award",
                 "department commerce", "project phase", "award project")
_GRANT_WEAK = ("programme", " sme ", "phase i", "phase ii", "consortium", "work package",
               "deliverable", "project aim", "participant", "funded under", "this project",
               "the project", "sme instrument")


def is_grant(t: str) -> bool:
    lt = f" {t.lower()} "
    if any(s in lt for s in _GRANT_STRONG):
        return True
    return sum(1 for s in _GRANT_WEAK if s in lt) >= 2


def clean_and_filter(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["raw_len"] = df["description"].str.len()
    df["description"] = df["description"].apply(clean_text)
    df["clean_len"] = df["description"].str.len()
    df["grant"] = df["description"].apply(is_grant)
    # drop grant abstracts + rows that were mostly boilerplate (little real text survives)
    keep = (~df["grant"]) & (df["clean_len"] >= 40) & (df["clean_len"] / df["raw_len"].clip(lower=1) >= 0.4)
    removed = df[~keep]
    print(f"cleaning: dropped {len(removed):,} rows "
          f"({int(df['grant'].sum()):,} grant/award abstracts, rest boilerplate/low-signal) — "
          f"hidden {int((removed.bucket=='hidden').sum()):,}, published {int((removed.bucket=='published').sum()):,}")
    return df[keep].drop(columns=["raw_len", "clean_len", "grant"]).reset_index(drop=True)


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
    df = clean_and_filter(df)
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
