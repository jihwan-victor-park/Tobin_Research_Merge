"""
Rebuild the taxonomy so ALL hidden AI companies are retained (none dropped).

Published companies keep their cached embedding assignments. Hidden companies are
re-mapped using the BEST available text — company_enrichment.problem_solved (Victor's
classify tier) when the raw description is missing/boilerplate — then assigned to the
nearest existing cluster. Hidden companies with no text at all are still written, with
domain='Pending enrichment', carrying Victor's ai_application/ai_subfield so they're
categorized and re-map automatically once enriched.

    python3 scripts/taxonomy_add_hidden.py --write
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
from scripts.taxonomy_pilot import clean_text, is_grant

S = Path("/private/tmp/claude-502/-Users-alastairpage-ai-startup-scraper/17db0b8c-2f15-45a0-8e77-b90a1b367338/scratchpad")
PENDING = "Pending enrichment"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--model", default="all-MiniLM-L6-v2")
    a = ap.parse_args()

    # cached full build (published + old hidden), post-relabel labels
    assign = pd.read_parquet(S / "taxonomy_full_assignments.parquet").reset_index(drop=True)
    emb = np.load(S / "taxonomy_emb.npy")
    assert len(assign) == len(emb)

    # cluster -> (label, domain, capability) and centroids from cached embeddings
    meta = assign.groupby("cluster").agg(label=("label", "first"), domain=("domain", "first"),
                                         capability=("capability", "first"))
    clusters = sorted(assign["cluster"].unique())
    cents = np.vstack([_norm(emb[assign["cluster"].values == cl].mean(0)) for cl in clusters])
    cl_index = {i: cl for i, cl in enumerate(clusters)}

    # published rows: keep exactly as cached
    pub = assign[assign.bucket == "published"].copy()
    pub["ai_application"] = None; pub["ai_subfield"] = None; pub["status"] = "mapped"
    print(f"published kept: {len(pub):,}")

    # pull ALL hidden AI with best text + Victor's categories
    eng = create_engine(os.getenv("RAILWAY_DATABASE_URL"))
    AI = ai_filter_sql("co")
    hid = _chunked_hidden(eng, AI)
    hid["bucket"] = "hidden"
    print(f"hidden AI pulled: {len(hid):,}")

    hid["text"] = hid.apply(lambda r: _pick_text(r["description"], r["problem_solved"]), axis=1)
    has = hid[hid["text"].str.len() >= 40].copy()
    pend = hid[hid["text"].str.len() < 40].copy()
    print(f"  hidden with usable text: {len(has):,} | pending (no text): {len(pend):,}")

    # embed hidden-with-text, assign to nearest existing cluster
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(a.model)
    hemb = model.encode((has["name"].fillna("") + ". " + has["text"].str.slice(0, 900)).tolist(),
                        batch_size=256, show_progress_bar=True, convert_to_numpy=True, normalize_embeddings=True)
    nearest = (hemb @ cents.T).argmax(1)
    has["cluster"] = [cl_index[i] for i in nearest]
    has = has.merge(meta, left_on="cluster", right_index=True, how="left")
    has["status"] = "mapped"

    # pending: keep, categorized by Victor where available
    pend = pend.copy()
    pend["cluster"] = -1
    pend["domain"] = PENDING
    pend["label"] = pend["ai_subfield"].fillna(pend["ai_application"]).fillna("unclassified")
    pend["capability"] = "Other"
    pend["status"] = "pending"

    cols = ["id", "name", "bucket", "cluster", "domain", "label", "capability",
            "ai_application", "ai_subfield", "status"]
    hidden_out = pd.concat([has[cols], pend[cols]], ignore_index=True)
    full = pd.concat([pub[cols], hidden_out], ignore_index=True)
    full["is_noise"] = False

    print(f"\n=== full taxonomy: {len(full):,} companies ===")
    print(f"  published mapped: {len(pub):,}")
    print(f"  hidden mapped:    {len(has):,}")
    print(f"  hidden pending:   {len(pend):,}  (retained, categorized by Victor where available)")
    print(f"  hidden total:     {len(hidden_out):,}  (target 13,579)")
    print("\nhidden mapped by domain:")
    print(has.groupby("domain").size().sort_values(ascending=False).head(12).to_string())

    full.to_parquet(S / "taxonomy_full_with_hidden.parquet")
    if a.write:
        _write(full)
    print("done")


def _norm(v):
    return v / (np.linalg.norm(v) + 1e-9)


def _pick_text(desc, prob):
    d = clean_text(desc or "")
    if len(d) >= 60 and not is_grant(d):
        return d
    p = clean_text(prob or "")
    return p if len(p) >= 40 else ""


def _chunked_hidden(eng, AI, chunk=20000):
    import time, psycopg2
    url = os.getenv("RAILWAY_DATABASE_URL")
    ka = dict(connect_timeout=20, keepalives=1, keepalives_idle=20, keepalives_interval=10, keepalives_count=5)
    def q(sql):
        for _ in range(6):
            try:
                c = psycopg2.connect(url, **ka)
                try: return pd.read_sql(sql, c)
                finally: c.close()
            except Exception: time.sleep(3)
        raise RuntimeError("pull failed")
    mx = int(q(f"SELECT COALESCE(max(id),0) m FROM companies co WHERE {AI} AND verification_status::text='emerging_github'")["m"][0])
    parts = []
    for lo in range(0, mx + 1, chunk):
        parts.append(q(f"""SELECT co.id, co.name, co.description, en.problem_solved,
            en.ai_application, en.ai_subfield
            FROM companies co LEFT JOIN company_enrichment en ON en.company_id=co.id
            WHERE {AI} AND co.verification_status::text='emerging_github'
              AND co.id>={lo} AND co.id<{lo+chunk}"""))
    return pd.concat(parts, ignore_index=True)


def _write(full):
    import psycopg2, psycopg2.extras
    url = os.getenv("RAILWAY_DATABASE_URL")
    conn = psycopg2.connect(url); cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS company_taxonomy")
    cur.execute("""CREATE TABLE company_taxonomy (
        company_id INTEGER PRIMARY KEY, bucket VARCHAR(12), domain_l1 VARCHAR(48),
        cluster_label VARCHAR(90), capability VARCHAR(40), cluster_id INTEGER,
        ai_application VARCHAR(40), ai_subfield VARCHAR(40), status VARCHAR(20))""")
    conn.commit()
    rows = [(int(r.id), r.bucket, r.domain, str(r.label)[:90], r.capability, int(r.cluster),
             r.ai_application, r.ai_subfield, r.status) for r in full.itertuples()]
    psycopg2.extras.execute_values(cur,
        "INSERT INTO company_taxonomy (company_id,bucket,domain_l1,cluster_label,capability,cluster_id,ai_application,ai_subfield,status) VALUES %s",
        rows, page_size=2000)
    conn.commit(); conn.close()
    print(f"wrote company_taxonomy to Railway ({len(rows):,} rows)")


if __name__ == "__main__":
    main()
