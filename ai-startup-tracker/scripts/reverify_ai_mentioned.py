"""
Re-verify the 'ai_mentioned-only' companies — those in the AI population solely
because their text mentions AI (no CB tag, no prior LLM verify, keyword score
< 0.5). Many are real AI companies other signals missed (ZEFR, LAMPI, Anny AI);
some are intruders (a software training institute, grant boilerplate).

For each, ask Haiku "is AI/ML the CORE product?" (packed ~20/call). Write:
  confirmed AI      -> companies.llm_ai_verified = TRUE   (reusable everywhere)
  confirmed non-AI  -> companies.llm_ai_rejected = TRUE   (explicit exclusion)

    python3 scripts/reverify_ai_mentioned.py --limit 40     # pilot
    python3 scripts/reverify_ai_mentioned.py --write        # full run + persist
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); load_dotenv(ROOT / ".env")
from scripts.enrich_companies_with_ai import _call_llm, _parse_json

URL = os.getenv("RAILWAY_DATABASE_URL")
KA = dict(connect_timeout=20, keepalives=1, keepalives_idle=20, keepalives_interval=10, keepalives_count=5)
SEL = ("ai_mentioned=TRUE AND NOT COALESCE(cb_ai_tagged,false) "
       "AND NOT COALESCE(llm_ai_verified,false) AND COALESCE(ai_score,0)<0.5 "
       "AND description IS NOT NULL AND length(description)>40")


def _conn():
    for _ in range(6):
        try: return psycopg2.connect(URL, **KA)
        except Exception: time.sleep(3)
    return psycopg2.connect(URL, **KA)


def classify_batch(batch):
    lines = "\n".join(f"{i+1}. {n}: {str(d)[:220]}" for i, (_, n, d) in enumerate(batch))
    prompt = (
        "For each company, decide if AI or machine learning is the CORE of its product/"
        "technology — not just a passing mention or a buzzword. A software training institute, "
        "a consultancy, or a grant abstract that name-drops AI is NOT core-AI.\n\n"
        f"{lines}\n\n"
        "Return ONLY a JSON array, one object per company: "
        "[{\"i\": <number>, \"ai\": true|false}]"
    )
    data = _parse_json(_call_llm([{"role": "user", "content": prompt}], temperature=0.0) or "")
    out = {}
    if isinstance(data, list):
        for o in data:
            if isinstance(o, dict) and "i" in o and "ai" in o:
                j = int(o["i"]) - 1
                if 0 <= j < len(batch):
                    out[batch[j][0]] = bool(o["ai"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--workers", type=int, default=10)
    a = ap.parse_args()

    lim = f"LIMIT {a.limit}" if a.limit else ""
    with _conn() as c:
        df = pd.read_sql(f"SELECT id, name, description FROM companies WHERE {SEL} ORDER BY id {lim}", c)
    print(f"re-verifying {len(df):,} ai_mentioned-only companies...")

    rows = list(df.itertuples(index=False, name=None))  # (id, name, description)
    batches = [rows[i:i + a.batch] for i in range(0, len(rows), a.batch)]
    verdict = {}; done = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(classify_batch, b) for b in batches]
        for f in as_completed(futs):
            verdict.update(f.result()); done += 1
            if done % 20 == 0:
                print(f"  {done}/{len(batches)} batches, {len(verdict):,} classified", flush=True)

    ai = sum(1 for v in verdict.values() if v)
    non = sum(1 for v in verdict.values() if not v)
    parsed = len(verdict)
    print(f"\nclassified {parsed:,}/{len(df):,} ({100*parsed/max(len(df),1):.0f}% parsed): "
          f"AI {ai:,} ({100*ai/max(parsed,1):.0f}%) | non-AI {non:,} ({100*non/max(parsed,1):.0f}%)")

    # show a few of each for eyeball
    name_by = {r[0]: r[1] for r in rows}
    print("  sample AI:    ", ", ".join(name_by[i] for i, v in list(verdict.items()) if v)[:0] or
          ", ".join([name_by[i] for i, v in verdict.items() if v][:6]))
    print("  sample non-AI:", ", ".join([name_by[i] for i, v in verdict.items() if not v][:6]))

    if not a.write:
        print("\n(pilot — pass --write to persist llm_ai_verified / llm_ai_rejected)")
        return

    conn = _conn(); cur = conn.cursor()
    cur.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS llm_ai_rejected BOOLEAN")
    conn.commit()
    ai_ids = [(i,) for i, v in verdict.items() if v]
    non_ids = [(i,) for i, v in verdict.items() if not v]
    for label, ids, sql in [
        ("llm_ai_verified", ai_ids, "UPDATE companies SET llm_ai_verified=TRUE FROM (VALUES %s) v(id) WHERE companies.id=v.id"),
        ("llm_ai_rejected", non_ids, "UPDATE companies SET llm_ai_rejected=TRUE FROM (VALUES %s) v(id) WHERE companies.id=v.id")]:
        for k in range(0, len(ids), 2000):
            for attempt in range(6):
                try:
                    psycopg2.extras.execute_values(cur, sql, ids[k:k+2000]); conn.commit(); break
                except psycopg2.OperationalError:
                    try: conn.close()
                    except Exception: pass
                    time.sleep(3); conn = _conn(); cur = conn.cursor()
        print(f"  wrote {label} for {len(ids):,}")
    conn.close()
    print("done")


if __name__ == "__main__":
    main()
