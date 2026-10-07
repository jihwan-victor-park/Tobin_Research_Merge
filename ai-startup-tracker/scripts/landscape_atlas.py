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

**Two things were tried and rejected, so they are not tried again.**

*Feeding the sector in with the text* (`--sector-weight`, off by default). The
idea was that position should reflect the classification as well as the prose.
It does not survive contact: repeating a sector term makes every company in it
a near-duplicate signature, and the projection answers correctly by collapsing
each one into its own tight island on an empty field. Faithful, and unreadable
as a map. Sector already reaches the picture twice over — companies in a sector
share vocabulary, and the colour is the sector.

*UMAP instead of t-SNE* (`--umap`, off by default). The usual argument is that
UMAP keeps more global structure. On this corpus it does the opposite of what
is wanted: it finds the clusters and then pushes them apart, so the figure
becomes a scatter of specks with black between them. t-SNE gives the connected
mass with filaments and outlying islands that actually reads as a landscape.
Both switches remain, because the right answer may change as the descriptions
do — but the default is what was measured to look like the data.

TF-IDF and SVD rather than a neural embedding on purpose: the pipeline that
built `company_taxonomy` used sentence-transformers, which drags in torch and
2GB of wheels. This needs scikit-learn alone, runs on a laptop CPU, and for
"which companies talk alike" it is enough — the clusters it has to agree with
were already assigned.

Run it when descriptions have changed materially; the map is static between
runs, which is also what makes it trustworthy to look at twice.

    pip install scikit-learn        # umap-learn only for --umap
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


# Only the broad domain rides along, not the cluster label. Repeating one of
# ~200 cluster names makes every cluster a near-duplicate signature, and the
# projection answers by scattering them as a few hundred islands on an empty
# field — technically faithful, unreadable as a map. The handful of domains
# gives the sectors enough pull to hold regions together without that.
SECTOR_WEIGHT = 0


def documents(descriptions: pd.Series, sectors: pd.Series | None = None) -> pd.Series:
    """What actually gets vectorised: the description, plus its sector terms.

    The sector is repeated a few times so that TF-IDF gives it the weight of a
    recurring theme rather than of one passing word in a 60-word paragraph.
    """
    text = descriptions.fillna("")
    if sectors is None:
        return text
    tag = (sectors.fillna("").astype(str)
                  .str.replace(r"[^A-Za-z0-9 ]", " ", regex=True)
                  .str.strip() + " ")
    return text + " " + tag.str.repeat(SECTOR_WEIGHT)


def _project(Z: np.ndarray, seed: int, use_umap: bool = False) -> np.ndarray:
    """Sixty dimensions down to two."""
    if use_umap:
        import umap
        return umap.UMAP(n_components=2, n_neighbors=50, min_dist=0.35,
                         metric="cosine", random_state=seed).fit_transform(Z)

    from sklearn.manifold import TSNE
    return TSNE(n_components=2, perplexity=min(PERPLEXITY, max(5, len(Z) // 4)),
                init="pca", random_state=seed, max_iter=750,
                angle=0.6).fit_transform(Z)


def compute(descriptions: pd.Series, sectors: pd.Series | None = None, *,
            seed: int = 7, use_umap: bool = False) -> np.ndarray:
    """(n, 2) coordinates for description text, optionally weighted by sector.

    Importable on its own so the layout can be exercised without a database.
    """
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer

    descriptions = documents(descriptions, sectors)
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
    xy = _project(Z, seed, use_umap)
    log(f"projected to 2d  ({time.time() - t0:.0f}s)")

    return _normalise(xy)


def _normalise(xy: np.ndarray) -> np.ndarray:
    """Into a unit square, robustly.

    Scaling by the furthest point lets a dozen strays decide the zoom: the
    projection throws off a few far outliers, and dividing by their distance
    shrinks the hundred thousand companies that matter into a thumbnail in one
    corner. The 99th percentile sets the frame instead, and the strays are
    pulled to the edge rather than allowed to define it.
    """
    xy = xy - np.median(xy, axis=0)
    radius = np.quantile(np.hypot(xy[:, 0], xy[:, 1]), 0.99)
    xy = xy / (radius + 1e-9)
    return np.clip(xy, -1.0, 1.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="cap rows, for a dry run")
    ap.add_argument("--dry-run", action="store_true", help="compute but do not write")
    ap.add_argument("--umap", action="store_true",
                    help="project with UMAP instead of t-SNE (see the note above)")
    ap.add_argument("--sector-weight", type=int, default=0,
                    help="fold the sector into the text this many times (see above)")
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
        SELECT t.company_id, LEFT(c.description, 420) AS description,
               t.domain_l1 AS sector
        FROM company_taxonomy t
        JOIN companies c ON c.id = t.company_id
        WHERE t.status IN ('mapped', 'category_mapped')
          AND t.domain_l1 <> 'Pending enrichment'
          AND c.description IS NOT NULL AND length(c.description) > 60
        ORDER BY t.company_id {cap}
    """, engine)
    if df.empty:
        sys.exit("no classified companies with a usable description")
    log(f"{len(df):,} companies")

    global SECTOR_WEIGHT
    SECTOR_WEIGHT = args.sector_weight
    xy = compute(df["description"], df["sector"] if args.sector_weight else None,
                 use_umap=args.umap)
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
