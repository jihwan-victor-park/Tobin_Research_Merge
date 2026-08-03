"""
Classify a SAMPLE of commercial (Crunchbase/PitchBook) AI companies with the
SAME taxonomy Victor's enrich_fields.py applies to hidden companies, so the
hidden-vs-commercial "what are they doing" comparison (research_analysis.py
section 20) is apples-to-apples.

Reuses enrich_fields.py's classify_from_text / upsert / ensure_table verbatim
(no duplicated prompt or LLM logic) — only the candidate query differs:
commercial AI companies with a description, not already enriched. Different
rows than Victor's hidden run (his is scoped to emerging_github), so the two
runs write disjoint rows of company_enrichment — no conflict.

    python scripts/classify_commercial_sample.py --limit 50 --dry-run
    python scripts/classify_commercial_sample.py --limit 1500 --workers 6
"""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text

from backend.db.connection import get_engine
from backend.utils.ai_filter import ai_filter_sql
from scripts.enrich_fields import classify_from_text, upsert, ensure_table

COMMERCIAL = "verification_status IN ('verified_cb', 'verified_pb', 'verified_cb_pb')"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=1500)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    engine = get_engine()
    ensure_table(engine)
    with engine.connect() as c:
        rows = c.execute(text(f"""
            SELECT c.id, c.name, c.description
            FROM companies c
            LEFT JOIN company_enrichment e ON e.company_id = c.id
            WHERE {COMMERCIAL} AND {ai_filter_sql('c')}
              AND c.description IS NOT NULL AND c.description <> ''
              AND e.ai_application IS NULL
            ORDER BY random()
            LIMIT :lim
        """), {"lim": a.limit}).mappings().all()
    print(f"commercial classify: {len(rows)} CB/PB AI companies (sample)")

    def work(row):
        data = classify_from_text(row["name"], row["description"])
        if not data:
            return row["id"], None
        conf = float(data.get("confidence", 0.5) or 0.5)
        fields = {
            "sector": (data.get("sector") or "")[:64] or None,
            "ai_application": data.get("ai_application"),
            "ai_subfield": data.get("ai_subfield"),
            "business_model": data.get("business_model"),
            "target_customer": (data.get("target_customer") or "")[:200] or None,
            "problem_solved": (data.get("problem_solved") or "")[:300] or None,
        }
        src = {k: {"source": "llm_from_description", "confidence": conf}
               for k, v in fields.items() if v}
        return row["id"], (fields, src)

    done = written = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(work, r) for r in rows]
        for f in as_completed(futs):
            cid, res = f.result()
            if res and not a.dry_run:
                upsert(engine, cid, res[0], res[1])
                written += 1
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(rows)} (written={written})")
    print(f"✓ done ({'dry-run' if a.dry_run else f'{written} written'})")


if __name__ == "__main__":
    main()
