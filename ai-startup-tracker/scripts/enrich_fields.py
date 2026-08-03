"""
Field enrichment for the "invisible" (hidden) AI companies.

Fills the advisor's requested fields — description, sector, AI application/tech,
business model, location, team/product/accelerator signals, and the hard trio
(founding year, founders, recent funding) — plus a per-field source+confidence
record so we can answer "how good is this number?".

Reuses the existing infra rather than adding a new LLM/scraper stack:
  - LLM        : _call_llm  (Together Llama-3.3-70B primary -> Claude Haiku 4.5
                 failover, via backend/utils/llm_filter) from enrich_companies_with_ai
  - Web search : tavily_search  (same module)
  - Site fetch : httpx + BeautifulSoup (already in requirements)

Stages (run in order; each is independent and resumable):
  classify   Tier 1, cheapest — LLM reads the existing description and tags
             sector / ai_application / ai_subfield / business_model /
             target_customer / problem_solved.  (~$0.001/company)
  web        Tier 1-2 — for rows missing domain/description/location, Tavily +
             the company site fill them, then re-run classify inline.
  deep       Tier 3 (hard) — Tavily search for founders / founding year /
             recent funding, kept only above a confidence floor.

    python scripts/enrich_fields.py classify --limit 200 --dry-run
    python scripts/enrich_fields.py classify
    python scripts/enrich_fields.py web  --workers 6
    python scripts/enrich_fields.py deep --min-confidence 0.5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text

from backend.db.connection import get_engine
from backend.utils.ai_filter import ai_filter_sql
# reuse the LLM + Tavily helpers already built for company resolution
from scripts.enrich_companies_with_ai import _call_llm, _parse_json, tavily_search

HIDDEN = "verification_status = 'emerging_github'"   # the invisibles

# Fixed taxonomies — the LLM must pick from these so aggregation is clean.
AI_APPLICATION = ["ai_for_science", "healthcare", "b2b", "b2c", "consumer", "other"]
AI_SUBFIELD = ["llm_nlp", "computer_vision", "agents", "robotics", "speech_audio",
               "generative_media", "ml_infrastructure", "data_analytics", "other"]
BUSINESS_MODEL = ["saas", "api_platform", "marketplace", "consumer_app",
                  "hardware", "services", "open_source", "other"]
PRODUCT_STATUS = ["live", "beta", "waitlist", "research", "unknown"]
TEAM_BUCKET = ["1-10", "11-50", "51-200", "200+", "unknown"]


# ── enrichment table ─────────────────────────────────────────────────
def ensure_table(engine) -> None:
    with engine.begin() as c:
        c.execute(text("""
            CREATE TABLE IF NOT EXISTS company_enrichment (
                company_id      INTEGER PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
                sector          VARCHAR(64),
                ai_application  VARCHAR(32),
                ai_subfield     VARCHAR(32),
                business_model  VARCHAR(32),
                target_customer TEXT,
                problem_solved  TEXT,
                location_city   VARCHAR(128),
                location_country VARCHAR(96),
                team_size_bucket VARCHAR(16),
                product_status  VARCHAR(16),
                accelerator     VARCHAR(96),
                founding_year   INTEGER,
                founders        JSONB,
                recent_funding  TEXT,
                sources         JSONB DEFAULT '{}'::jsonb,   -- {field: {source, confidence}}
                enriched_at     TIMESTAMPTZ DEFAULT now()
            )
        """))


_COLS = ["sector", "ai_application", "ai_subfield", "business_model",
         "target_customer", "problem_solved", "location_city", "location_country",
         "team_size_bucket", "product_status", "accelerator", "founding_year",
         "founders", "recent_funding"]


def upsert(engine, company_id: int, fields: dict, sources: dict) -> None:
    """Merge fields into company_enrichment. COALESCE keeps existing values when
    a field is omitted this stage; sources JSONB is merged, not replaced."""
    params = {"cid": company_id, "sources": json.dumps(sources)}
    for col in _COLS:
        val = fields.get(col)
        params[col] = json.dumps(val) if col == "founders" and val is not None else val
    set_clause = ", ".join(
        f"{col} = COALESCE(EXCLUDED.{col}, company_enrichment.{col})" for col in _COLS
    )
    insert_cols = ", ".join(_COLS)
    insert_vals = ", ".join(
        (f"CAST(:{col} AS jsonb)" if col == "founders" else f":{col}") for col in _COLS
    )
    with engine.begin() as c:
        c.execute(text(f"""
            INSERT INTO company_enrichment (company_id, {insert_cols}, sources, enriched_at)
            VALUES (:cid, {insert_vals}, CAST(:sources AS jsonb), now())
            ON CONFLICT (company_id) DO UPDATE SET
                {set_clause},
                sources = company_enrichment.sources || EXCLUDED.sources,
                enriched_at = now()
        """), params)


# ── website fetch (static) ───────────────────────────────────────────
def fetch_site_text(domain: str, max_chars: int = 6000) -> Optional[str]:
    import httpx
    from bs4 import BeautifulSoup
    if not domain:
        return None
    url = domain if domain.startswith("http") else f"https://{domain}"
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (research-crawler)"})
        if r.status_code >= 400 or "text/html" not in r.headers.get("content-type", ""):
            return None
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "svg"]):
            tag.decompose()
        text_out = " ".join(soup.get_text(" ").split())
        return text_out[:max_chars] or None
    except Exception:
        return None


# ── Tier 1: classify from description ────────────────────────────────
def classify_from_text(name: str, blurb: str) -> Optional[dict]:
    prompt = (
        f"You are labeling an AI startup for a research dataset. Company: {name!r}.\n"
        f"Description:\n{blurb[:1500]}\n\n"
        "Return ONLY compact JSON with these keys, choosing values from the allowed sets:\n"
        f"  ai_application: one of {AI_APPLICATION}\n"
        f"  ai_subfield: one of {AI_SUBFIELD}\n"
        f"  business_model: one of {BUSINESS_MODEL}\n"
        "  sector: 2-4 word industry (free text, e.g. 'healthcare diagnostics')\n"
        "  target_customer: who they sell to, <=8 words\n"
        "  problem_solved: one sentence, <=20 words\n"
        "  confidence: 0.0-1.0 how sure you are given the description\n"
        "If the description is too thin to tell, use 'other'/'unknown' and low confidence."
    )
    raw = _call_llm([{"role": "user", "content": prompt}], temperature=0.0)
    data = _parse_json(raw or "")
    if not data:
        return None
    # normalize to allowed sets
    if data.get("ai_application") not in AI_APPLICATION:
        data["ai_application"] = "other"
    if data.get("ai_subfield") not in AI_SUBFIELD:
        data["ai_subfield"] = "other"
    if data.get("business_model") not in BUSINESS_MODEL:
        data["business_model"] = "other"
    return data


def stage_classify(engine, limit: int, workers: int, dry_run: bool) -> None:
    with engine.connect() as c:
        rows = c.execute(text(f"""
            SELECT c.id, c.name, c.description
            FROM companies c
            LEFT JOIN company_enrichment e ON e.company_id = c.id
            WHERE {HIDDEN} AND {ai_filter_sql('c')}
              AND c.description IS NOT NULL AND c.description <> ''
              AND (e.ai_application IS NULL)
            LIMIT :lim
        """), {"lim": limit}).mappings().all()
    print(f"classify: {len(rows)} hidden AI companies with a description")

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

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, r) for r in rows]
        for f in as_completed(futs):
            cid, res = f.result()
            if res and not dry_run:
                upsert(engine, cid, res[0], res[1])
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(rows)}")
    print(f"✓ classify done ({'dry-run' if dry_run else 'written'})")


# ── Tier 1-2: web fill (domain / description / location / signals) ───
def stage_web(engine, limit: int, workers: int, dry_run: bool) -> None:
    with engine.connect() as c:
        rows = c.execute(text(f"""
            SELECT c.id, c.name, c.domain, c.description, c.country, c.city
            FROM companies c
            LEFT JOIN company_enrichment e ON e.company_id = c.id
            WHERE {HIDDEN} AND {ai_filter_sql('c')}
              AND (c.domain IS NULL OR c.description IS NULL OR c.country IS NULL
                   OR e.product_status IS NULL)
            LIMIT :lim
        """), {"lim": limit}).mappings().all()
    print(f"web: {len(rows)} hidden AI companies to web-enrich")

    def work(row):
        name = row["name"]
        domain = row["domain"]
        src = {}
        fields = {}
        # 1) find domain if missing
        if not domain:
            hits = tavily_search(f"{name} AI startup official website", max_results=3)
            for h in hits:
                u = (h.get("url") or "").split("/")[2:3]
                if u:
                    domain = u[0].replace("www.", "")
                    fields["domain_found"] = domain  # informational; companies.domain updated below
                    src["domain"] = {"source": "tavily", "confidence": 0.5}
                    break
        # 2) fetch site text, feed the LLM for description + Tier-2 signals
        site = fetch_site_text(domain) if domain else None
        blurb = row["description"] or ""
        if site:
            prompt = (
                f"From this company website text for {name!r}, extract JSON:\n{site[:4000]}\n\n"
                "Keys (use null when not stated):\n"
                "  description: one-sentence summary of what they do\n"
                "  location_city, location_country\n"
                f"  team_size_bucket: one of {TEAM_BUCKET}\n"
                f"  product_status: one of {PRODUCT_STATUS}\n"
                "  accelerator: incubator/accelerator name if mentioned (e.g. Y Combinator)\n"
                "  confidence: 0.0-1.0"
            )
            data = _parse_json(_call_llm([{"role": "user", "content": prompt}]) or "") or {}
            conf = float(data.get("confidence", 0.5) or 0.5)
            for col in ["location_city", "location_country", "team_size_bucket",
                        "product_status", "accelerator"]:
                v = data.get(col)
                if v and str(v).lower() not in ("null", "unknown", ""):
                    fields[col] = str(v)[:128]
                    src[col] = {"source": "website", "confidence": conf}
            if not blurb and data.get("description"):
                blurb = str(data["description"])
                fields["_new_description"] = blurb
                src["description"] = {"source": "website", "confidence": conf}
        return row["id"], domain, blurb, fields, src

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, r) for r in rows]
        for f in as_completed(futs):
            cid, domain, blurb, fields, src = f.result()
            if not dry_run:
                # write back domain/description onto companies (canonical), signals onto enrichment
                with engine.begin() as c:
                    if domain:
                        c.execute(text("UPDATE companies SET domain = COALESCE(domain, :d) "
                                       "WHERE id = :cid"), {"d": domain, "cid": cid})
                    if fields.get("_new_description"):
                        c.execute(text("UPDATE companies SET description = COALESCE(description, :x) "
                                       "WHERE id = :cid"), {"x": fields["_new_description"], "cid": cid})
                clean = {k: v for k, v in fields.items() if k in _COLS}
                if clean or src:
                    upsert(engine, cid, clean, src)
            done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(rows)}")
    print(f"✓ web done ({'dry-run' if dry_run else 'written'})")


# ── Tier 3: founders / founding year / recent funding (hard) ─────────
def stage_deep(engine, limit: int, workers: int, min_conf: float, dry_run: bool) -> None:
    with engine.connect() as c:
        rows = c.execute(text(f"""
            SELECT c.id, c.name, c.domain
            FROM companies c
            LEFT JOIN company_enrichment e ON e.company_id = c.id
            WHERE {HIDDEN} AND {ai_filter_sql('c')}
              AND (e.founders IS NULL OR e.founding_year IS NULL OR e.recent_funding IS NULL)
            LIMIT :lim
        """), {"lim": limit}).mappings().all()
    print(f"deep: {len(rows)} hidden AI companies for founder/funding/year search")

    def work(row):
        name = row["name"]
        ctx = "\n".join(
            f"- {h.get('title','')}: {h.get('content','')[:200]}"
            for h in tavily_search(f"{name} startup founder funding founded", max_results=5)
        )
        if not ctx.strip():
            return row["id"], None
        prompt = (
            f"Search snippets about the startup {name!r}:\n{ctx[:3500]}\n\n"
            "Extract JSON (null when the snippets don't clearly say):\n"
            "  founders: list of {name, title} (only if clearly this company's founders)\n"
            "  founding_year: integer year\n"
            "  recent_funding: short string e.g. 'Seed $2M (2024)'\n"
            "  confidence: 0.0-1.0 — be strict; many startups share names\n"
            "Only include a field if the snippets are actually about THIS company."
        )
        data = _parse_json(_call_llm([{"role": "user", "content": prompt}]) or "") or {}
        conf = float(data.get("confidence", 0.0) or 0.0)
        if conf < min_conf:
            return row["id"], None
        fields, src = {}, {}
        if isinstance(data.get("founders"), list) and data["founders"]:
            fields["founders"] = data["founders"][:6]
            src["founders"] = {"source": "tavily_search", "confidence": conf}
        yr = data.get("founding_year")
        if isinstance(yr, int) and 1990 <= yr <= 2026:
            fields["founding_year"] = yr
            src["founding_year"] = {"source": "tavily_search", "confidence": conf}
        if data.get("recent_funding"):
            fields["recent_funding"] = str(data["recent_funding"])[:120]
            src["recent_funding"] = {"source": "tavily_search", "confidence": conf}
        return row["id"], ((fields, src) if fields else None)

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, r) for r in rows]
        for f in as_completed(futs):
            cid, res = f.result()
            if res and not dry_run:
                upsert(engine, cid, res[0], res[1])
            done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(rows)}")
    print(f"✓ deep done ({'dry-run' if dry_run else 'written'})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["classify", "web", "deep"])
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--min-confidence", type=float, default=0.5)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    engine = get_engine()
    ensure_table(engine)
    if a.stage == "classify":
        stage_classify(engine, a.limit, a.workers, a.dry_run)
    elif a.stage == "web":
        stage_web(engine, a.limit, a.workers, a.dry_run)
    elif a.stage == "deep":
        stage_deep(engine, a.limit, a.workers, a.min_confidence, a.dry_run)


if __name__ == "__main__":
    main()
