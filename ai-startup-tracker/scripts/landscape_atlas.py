"""Real coordinates for the Landscape map.

The map used to arrange companies by hand: domains as discs, clusters seated
inside them. It was honest about that — the caption said the positions carried
no meaning — but it looked like what it was, six circles, and a reader learns
nothing from a circle.

This computes positions that mean something. Companies that describe
themselves alike land near each other, so the shape of the picture is the
shape of the industry: dense where many firms do one thing, strung out where a
subject shades into its neighbours, islands where something stands apart.

    description text  ──TF-IDF──▶  sparse terms
                      ──SVD 60──▶  dense semantic vector
                      ──t-SNE───▶  (x, y)

TF-IDF and SVD rather than a neural embedding on purpose: the pipeline that
built `company_taxonomy` used sentence-transformers, which drags in torch and
2GB of wheels. This needs scikit-learn alone, runs on a laptop CPU, and for
"which companies talk alike" it is enough — the clusters it has to agree with
were already assigned.

Run it when descriptions have changed materially; the map is static between
runs, which is also what makes it trustworthy to look at twice.

    pip install scikit-learn
    python3 scripts/landscape_atlas.py                 # against $DATABASE_URL
    python3 scripts/landscape_atlas.py --limit 20000   # a faster dry run

Writes `company_atlas(company_id, x, y)`. The page falls back to the old
hand-made layout when the table is absent, so this is safe to run late.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SVD_COMPONENTS = 60
PERPLEXITY = 35


def log(msg: str) -> None:
    print(f"[atlas] {msg}", flush=True)


def _where(url: str) -> str:
    """The host this is about to talk to, without the password."""
    tail = url.split("@")[-1]
    return tail.split("?")[0] or "unknown host"


def preflight(engine) -> None:
    """Say plainly which database this is and what it is missing.

    Worth the twenty lines: the natural failure here is a raw SQLAlchemy
    traceback ending in `relation "company_taxonomy" does not exist`, which
    does not tell you the one thing you need to know — that you are pointed at
    the wrong database.
    """
    from sqlalchemy import text

    with engine.connect() as conn:
        present = {r[0] for r in conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'"))}

    missing = [t for t in ("companies", "company_taxonomy") if t not in present]
    if not missing:
        return

    log(f"this database has {len(present)} tables and none of them are {missing}")
    sys.exit(
        "\n".join([
            "",
            "Pointed at the wrong database.",
            "",
            "  The classified companies live on Railway, not locally. Pass that",
            "  connection string in front of the command — it wins over the",
            "  DATABASE_URL in .env:",
            "",
            "    DATABASE_PUBLIC_URL='postgresql://...' python3 scripts/landscape_atlas.py",
            "",
            "  Railway dashboard -> your Postgres service -> Variables ->",
            "  DATABASE_PUBLIC_URL (the proxy.rlwy.net one, not the internal host).",
        ])
    )


def compute(descriptions: pd.Series, *, seed: int = 7) -> np.ndarray:
    """(n, 2) coordinates for a series of description text.

    Importable on its own so the layout can be exercised without a database.
    """
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.manifold import TSNE

    t0 = time.time()
    # Bigrams matter here: "computer vision" and "language model" are the units
    # people actually describe themselves in, and unigrams alone put every firm
    # that says "model" in one heap.
    tfidf = TfidfVectorizer(max_features=40_000, stop_words="english",
                            ngram_range=(1, 2), min_df=3, sublinear_tf=True)
    X = tfidf.fit_transform(descriptions)
    log(f"tf-idf {X.shape[0]:,} docs x {X.shape[1]:,} terms  ({time.time() - t0:.0f}s)")

    t0 = time.time()
    k = min(SVD_COMPONENTS, X.shape[1] - 1, X.shape[0] - 1)
    Z = TruncatedSVD(n_components=k, random_state=seed).fit_transform(X)
    # Cosine distance is what matters for text; normalising the rows lets
    # t-SNE's Euclidean metric stand in for it.
    Z = Z / (np.linalg.norm(Z, axis=1, keepdims=True) + 1e-9)
    log(f"svd → {Z.shape[1]} dims  ({time.time() - t0:.0f}s)")

    t0 = time.time()
    xy = TSNE(n_components=2, perplexity=min(PERPLEXITY, max(5, len(Z) // 4)),
              init="pca", random_state=seed, max_iter=750, angle=0.6).fit_transform(Z)
    log(f"t-sne  ({time.time() - t0:.0f}s)")

    # Normalise into a unit square so the figure does not have to rescale and
    # a re-run cannot silently change the zoom level.
    xy = xy - xy.mean(axis=0)
    xy = xy / (np.abs(xy).max() + 1e-9)
    return xy


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="cap rows, for a dry run")
    ap.add_argument("--dry-run", action="store_true", help="compute but do not write")
    args = ap.parse_args()

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from sqlalchemy import create_engine, text

    url = (os.getenv("RAILWAY_DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL")
           or os.getenv("DATABASE_URL") or "")
    if not url:
        sys.exit("set DATABASE_URL (or DATABASE_PUBLIC_URL) first")
    engine = create_engine(url.replace("postgres://", "postgresql://"))
    log(f"connecting to {_where(url)}")
    preflight(engine)

    cap = f"LIMIT {int(args.limit)}" if args.limit else ""
    log("reading descriptions")
    df = pd.read_sql(f"""
        SELECT t.company_id, LEFT(c.description, 420) AS description
        FROM company_taxonomy t
        JOIN companies c ON c.id = t.company_id
        WHERE t.status IN ('mapped', 'category_mapped')
          AND c.description IS NOT NULL AND length(c.description) > 60
        ORDER BY t.company_id {cap}
    """, engine)
    if df.empty:
        sys.exit("no classified companies with a usable description")
    log(f"{len(df):,} companies")

    xy = compute(df["description"])
    out = pd.DataFrame({"company_id": df["company_id"].astype(int),
                        "x": xy[:, 0], "y": xy[:, 1]})

    if args.dry_run:
        log(f"dry run — x {out.x.min():.2f}..{out.x.max():.2f}, "
            f"y {out.y.min():.2f}..{out.y.max():.2f}")
        return

    log("writing company_atlas")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS company_atlas (
                company_id INTEGER PRIMARY KEY,
                x REAL NOT NULL, y REAL NOT NULL)"""))
        conn.execute(text("TRUNCATE company_atlas"))
    out.to_sql("company_atlas", engine, if_exists="append", index=False,
               chunksize=5000, method="multi")
    log(f"wrote {len(out):,} coordinates")


if __name__ == "__main__":
    main()
