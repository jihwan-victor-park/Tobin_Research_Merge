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
from backend.utils.country import GLOBE_COUNTRIES, normalize_country
# reuse the LLM + Tavily helpers already built for company resolution
from scripts.enrich_companies_with_ai import (
    BAD_RESOLVED_HOSTS, _call_llm, _parse_json, tavily_search,
)

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
        # Fields the advisor didn't ask for but that fall out of pages we are
        # already fetching, so they cost almost nothing:
        #   ai_stack        who they depend on in the AI stack ("wrapper vs builder")
        #   commercialization  pricing page / enterprise motion => revenue attempt,
        #                   a partial stand-in for the funding data we can't get
        #   regulatory      HIPAA/FDA/GDPR exposure — matters for the health/science cut
        #   linkedin_url    present on ~53% of sites; the precise handle that makes a
        #                   later founder lookup tractable
        #   domain_created  WHOIS creation date -> founding-year proxy + discovery lag
        for col, typ in (("ai_stack", "VARCHAR(32)"),
                         ("commercialization", "VARCHAR(24)"),
                         ("regulatory", "VARCHAR(64)"),
                         ("open_source", "BOOLEAN"),
                         ("linkedin_url", "VARCHAR(200)"),
                         ("domain_created_year", "INTEGER"),
                         ("whois_attempted_at", "TIMESTAMPTZ")):
            c.execute(text(
                f"ALTER TABLE company_enrichment ADD COLUMN IF NOT EXISTS {col} {typ}"
            ))
        # Attempt bookkeeping: an unattended multi-hour run must not retry the
        # same dead site / no-result search on every pass. Each stage stamps its
        # column whether or not it extracted anything, and skips rows already
        # stamped.
        for col in ("web_attempted_at", "deep_attempted_at"):
            c.execute(text(
                f"ALTER TABLE company_enrichment ADD COLUMN IF NOT EXISTS {col} TIMESTAMPTZ"
            ))


def mark_attempt(engine, company_id: int, column: str) -> None:
    """Record that a stage ran for this company, even when it found nothing."""
    with engine.begin() as c:
        c.execute(text(f"""
            INSERT INTO company_enrichment (company_id, {column})
            VALUES (:cid, now())
            ON CONFLICT (company_id) DO UPDATE SET {column} = now()
        """), {"cid": company_id})


_COLS = ["sector", "ai_application", "ai_subfield", "business_model",
         "target_customer", "problem_solved", "location_city", "location_country",
         "team_size_bucket", "product_status", "accelerator", "founding_year",
         "founders", "recent_funding",
         "ai_stack", "commercialization", "regulatory", "open_source",
         "linkedin_url", "domain_created_year"]

AI_STACK = ["uses_closed_api", "uses_open_models", "builds_own_models", "not_stated"]
COMMERCIALIZATION = ["self_serve_pricing", "enterprise_sales", "waitlist_only",
                     "free_or_research", "not_stated"]


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
    return (fetch_site(domain, max_chars) or (None, None))[0]


def fetch_site(domain: str, max_chars: int = 6000):
    """Return (visible_text, linkedin_company_url). The LinkedIn handle is read
    from the raw HTML (present on ~53% of sites) — it costs nothing here and is
    the precise identifier that makes a later founder lookup tractable."""
    import re as _re

    import httpx
    from bs4 import BeautifulSoup
    if not domain:
        return None, None
    url = domain if domain.startswith("http") else f"https://{domain}"
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (research-crawler)"})
        if r.status_code >= 400 or "text/html" not in r.headers.get("content-type", ""):
            return None, None
        html = r.text
        m = _re.search(r"https?://[\w.]*linkedin\.com/company/[\w\-%.]+", html, _re.I)
        li = m.group(0)[:200] if m else None
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "svg"]):
            tag.decompose()
        text_out = " ".join(soup.get_text(" ").split())
        return (text_out[:max_chars] or None), li
    except Exception:
        return None, None


# ── WHOIS: domain creation year (free founding-year proxy) ───────────
def whois_year(domain: str) -> Optional[int]:
    """Year the domain was registered. Startups usually register at founding, so
    this is a usable proxy where no founding year exists — label it as a proxy,
    never as the true founding date. Skips the registry's own boilerplate
    'created: 1985-01-01' line that appears in every .com record."""
    import re as _re
    import subprocess
    try:
        out = subprocess.run(["whois", domain], capture_output=True,
                             text=True, timeout=25).stdout
    except Exception:
        return None
    for pat in (r"Creation Date:\s*(\d{4})",
                r"Domain Registration Date:\s*\w*\s*(\d{4})",
                r"created:\s*(\d{4})-\d\d-\d\d",
                r"Registered on:\s*\d\d-\w+-(\d{4})"):
        for m in _re.finditer(pat, out, _re.IGNORECASE):
            y = int(m.group(1))
            if 1990 <= y <= 2026:
                return y
    return None


# ── Tier 1: classify from description ────────────────────────────────
#
# Cost here is dominated by output tokens, which bill at five times input, so
# the JSON the model writes back uses two-letter keys and the batch prompt
# carries the instruction block once for many companies instead of once each.
# Long key names, repeated per company across twenty thousand companies, were
# most of the bill.
_SHORT = {
    "ap": "ai_application", "sf": "ai_subfield", "bm": "business_model",
    "se": "sector", "tc": "target_customer", "ps": "problem_solved",
    "ci": "location_city", "co": "location_country", "fy": "founding_year",
    "st": "product_status", "ts": "team_size_bucket", "ai": "ai_stack",
    "cm": "commercialization", "rg": "regulatory", "os": "open_source",
    "cf": "confidence", "bs": "basis",
}


def _expand(d: dict) -> dict:
    """Map the compact keys the model returns back to real field names."""
    out = {}
    for k, v in (d or {}).items():
        out[_SHORT.get(k, k)] = v
    basis = out.get("basis")
    if isinstance(basis, dict):
        out["basis"] = {_SHORT.get(k, k): v for k, v in basis.items()}
    return out


def _instructions() -> str:
    """The shared instruction block — sent once per batch, not once per company."""
    return (
        "Label AI startups for a research dataset.\n"
        "Reply with ONLY a JSON array, one object per company, same order as given.\n"
        "Use these exact short keys to keep the reply small:\n"
        f"  ap: one of {AI_APPLICATION}\n"
        f"  sf: one of {AI_SUBFIELD}\n"
        f"  bm: one of {BUSINESS_MODEL}\n"
        "  se: 2-4 word industry, e.g. 'healthcare diagnostics'\n"
        "  tc: who they sell to, <=5 words\n"
        "  ps: what problem they solve, <=12 words\n"
        "  cf: 0.0-1.0 how sure you are\n"
        # Asked to estimate these, the model returns the same modal startup for
        # almost every company - a third of them in San Francisco, 71% at 11-50
        # people, founded 2020 - which is its prior, not a reading of the text.
        # A distribution built from that describes the model, not the companies,
        # so these are extraction only: quote the description or return null.
        "\nAlso report these, but ONLY when the description states them.\n"
        "Return null when it does not say. Do NOT guess, estimate, or infer -\n"
        "a null here is correct and useful, a plausible-looking guess is not:\n"
        "  ci: city named in the text\n"
        "  co: country named in the text (a real country, not a region)\n"
        "  fy: 4-digit founding year given in the text\n"
        f"  st: one of {[s for s in PRODUCT_STATUS if s != 'unknown']} if the text says so\n"
        f"  ts: one of {[s for s in TEAM_BUCKET if s != 'unknown']} if the text says so\n"
        f"  ai: one of {[s for s in AI_STACK if s != 'not_stated']} if the text says so\n"
        f"  cm: one of {[s for s in COMMERCIALIZATION if s != 'not_stated']} if the text says so\n"
        "  rg: regulated regime the text mentions (HIPAA/FDA/GDPR/finance), else null\n"
        "  os: true or false only if the text says whether it is open source\n"
    )


def classify_batch(items: list[tuple[str, str]]) -> list[Optional[dict]]:
    """Classify several companies in one call. Returns one result per input,
    None where the model did not return a usable object for that position."""
    if not items:
        return []
    body = "\n\n".join(
        f"[{i}] {name!r}\n{(blurb or '')[:600]}" for i, (name, blurb) in enumerate(items)
    )
    raw = _call_llm([{"role": "user", "content": _instructions() + "\n\n" + body}],
                    temperature=0.0)
    data = _parse_json(raw or "")
    # _parse_json hands back whatever shape the model produced; a single object
    # is a valid reply when the batch is one company.
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return [None] * len(items)
    out: list[Optional[dict]] = []
    for i in range(len(items)):
        rec = data[i] if i < len(data) and isinstance(data[i], dict) else None
        out.append(_normalize(_expand(rec)) if rec else None)
    return out


def classify_from_text(name: str, blurb: str) -> Optional[dict]:
    return classify_batch([(name, blurb)])[0]


def _normalize(data: dict) -> Optional[dict]:
    """Validate whatever the model returned. Inference is allowed;
    nonsense is not."""
    if not data:
        return None
    # normalize to allowed sets
    if data.get("ai_application") not in AI_APPLICATION:
        data["ai_application"] = "other"
    if data.get("ai_subfield") not in AI_SUBFIELD:
        data["ai_subfield"] = "other"
    if data.get("business_model") not in BUSINESS_MODEL:
        data["business_model"] = "other"
    # Storing a catch-all is worse than storing nothing: it looks like coverage
    # in every count while telling us nothing, and it blocks the row from being
    # revisited later by a method that could actually answer.
    for key, allowed, empty in (("product_status", PRODUCT_STATUS, "unknown"),
                                ("team_size_bucket", TEAM_BUCKET, "unknown"),
                                ("ai_stack", AI_STACK, "not_stated"),
                                ("commercialization", COMMERCIALIZATION, "not_stated")):
        if data.get(key) not in allowed or data.get(key) == empty:
            data[key] = None
    reg = str(data.get("regulatory") or "").strip()[:40]
    data["regulatory"] = None if reg.lower() in ("none", "n/a", "unknown", "") else reg
    data["open_source"] = data["open_source"] if isinstance(data.get("open_source"), bool) else None
    # Inference is allowed; nonsense is not. A country still has to be a real
    # country, so "EU" and "Global" are rejected however confident the model is.
    cc = normalize_country(str(data.get("location_country") or "").strip())
    data["location_country"] = cc if cc in GLOBE_COUNTRIES else None
    year = data.get("founding_year")
    try:
        year = int(str(year)[:4])
    except (TypeError, ValueError):
        year = None
    data["founding_year"] = year if year and 1970 <= year <= 2026 else None
    if not isinstance(data.get("basis"), dict):
        data["basis"] = {}
    return data


def stage_classify(engine, limit: int, workers: int, dry_run: bool,
                   all_hidden: bool = False) -> None:
    # Restricting this to companies already flagged as AI is circular: a hidden
    # company with a description that has never been flagged can never be
    # classified, so it can never be found to be AI. --all-hidden lets the
    # classifier decide instead of requiring the answer up front.
    ai_clause = "" if all_hidden else f"AND {ai_filter_sql('c')}"
    with engine.connect() as c:
        rows = c.execute(text(f"""
            SELECT c.id, c.name, c.description
            FROM companies c
            LEFT JOIN company_enrichment e ON e.company_id = c.id
            WHERE {HIDDEN} {ai_clause}
              AND c.description IS NOT NULL AND c.description <> ''
              AND (e.ai_application IS NULL)
            LIMIT :lim
        """), {"lim": limit}).mappings().all()
    print(f"classify: {len(rows)} hidden companies with a description{'' if all_hidden else ' (AI-flagged only)'}", flush=True)

    BATCH = 8      # one instruction block covers eight companies

    def work(chunk):
        results = classify_batch([(r["name"], r["description"]) for r in chunk])
        out = []
        for row, data in zip(chunk, results):
            if not data:
                out.append((row["id"], None))
                continue
            conf = float(data.get("confidence", 0.5) or 0.5)
            fields = {
                "sector": (data.get("sector") or "")[:64] or None,
                "ai_application": data.get("ai_application"),
                "ai_subfield": data.get("ai_subfield"),
                "business_model": data.get("business_model"),
                "target_customer": (data.get("target_customer") or "")[:200] or None,
                "problem_solved": (data.get("problem_solved") or "")[:300] or None,
                "location_city": (data.get("location_city") or "")[:128] or None,
                "location_country": data.get("location_country"),
                "founding_year": data.get("founding_year"),
                "product_status": data.get("product_status"),
                "team_size_bucket": data.get("team_size_bucket"),
                "ai_stack": data.get("ai_stack"),
                "commercialization": data.get("commercialization"),
                "regulatory": data.get("regulatory"),
                "open_source": data.get("open_source"),
            }
            # Two kinds of value, kept apart by source: the taxonomy fields are
            # the model's reading of the description, the rest are quoted out of
            # it. Nothing here is estimated, so nothing is labelled inferred.
            judged = {"sector", "ai_application", "ai_subfield", "business_model",
                      "target_customer", "problem_solved"}
            src = {}
            for k, v in fields.items():
                if v is None:
                    continue
                src[k] = {"source": "llm_from_description" if k in judged
                                    else "llm_quoted_from_description",
                          "confidence": conf}
            out.append((row["id"], (fields, src)))
        return out

    chunks = [rows[i:i + BATCH] for i in range(0, len(rows), BATCH)]
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(work, ch) for ch in chunks]):
            for cid, res in f.result():
                if res and not dry_run:
                    upsert(engine, cid, res[0], res[1])
                done += 1
            if done % 200 < BATCH:
                print(f"  {done}/{len(rows)}", flush=True)
    print(f"✓ classify done ({'dry-run' if dry_run else 'written'})", flush=True)


# ── Tier 1-2: web fill (domain / description / location / signals) ───
def stage_web(engine, limit: int, workers: int, dry_run: bool,
              all_hidden: bool = False, have_domain: bool = False) -> None:
    # Rows that already have a domain are fetched directly; rows without one
    # have to be searched for first, and that search is the only part of this
    # stage that costs Tavily credit. --have-domain keeps the run on the free
    # half, which is also the half with the better hit rate.
    ai_clause = "" if all_hidden else f"AND {ai_filter_sql('c')}"
    dom_clause = "AND c.domain IS NOT NULL" if have_domain else ""
    with engine.connect() as c:
        rows = c.execute(text(f"""
            SELECT c.id, c.name, c.domain, c.description, c.country, c.city
            FROM companies c
            LEFT JOIN company_enrichment e ON e.company_id = c.id
            WHERE {HIDDEN} {ai_clause} {dom_clause}
              AND e.web_attempted_at IS NULL
              AND (c.domain IS NULL OR c.description IS NULL OR c.country IS NULL
                   OR e.product_status IS NULL)
            ORDER BY (c.domain IS NULL)     -- companies we already have a site for first
            LIMIT :lim
        """), {"lim": limit}).mappings().all()
    print(f"web: {len(rows)} hidden AI companies to web-enrich")

    def work(row):
        name = row["name"]
        domain = row["domain"]
        src = {}
        fields = {}
        # 1) find domain if missing — skip directories/social/news, which are
        #    never the company's own site (BAD_RESOLVED_HOSTS is the same
        #    denylist the company-resolution script uses).
        if not domain:
            hits = tavily_search(f"{name} AI startup official website", max_results=3)
            for h in hits:
                u = (h.get("url") or "").split("/")[2:3]
                if not u:
                    continue
                host = u[0].replace("www.", "").lower()
                if any(host == bad or host.endswith("." + bad) for bad in BAD_RESOLVED_HOSTS):
                    continue
                domain = host
                src["domain"] = {"source": "tavily", "confidence": 0.5}
                break
        # 2) fetch site text, feed the LLM for description + Tier-2 signals
        site, linkedin = fetch_site(domain) if domain else (None, None)
        if linkedin:
            fields["linkedin_url"] = linkedin
            src["linkedin_url"] = {"source": "website", "confidence": 0.9}
        blurb = row["description"] or ""
        # llm_ok distinguishes "the model looked and found nothing" from "the
        # model never ran" (credits out / transport error). Only the former is a
        # real attempt — stamping the latter would skip the row forever.
        llm_ok = True
        if site:
            prompt = (
                f"From this company website text for {name!r}, extract JSON:\n{site[:4000]}\n\n"
                "Keys (use null when not stated):\n"
                "  description: one-sentence summary of what they do\n"
                "  location_city, location_country\n"
                f"  team_size_bucket: one of {TEAM_BUCKET}\n"
                f"  product_status: one of {PRODUCT_STATUS}\n"
                "  accelerator: incubator/accelerator name if mentioned (e.g. Y Combinator)\n"
                f"  ai_stack: one of {AI_STACK} — do they call third-party model APIs "
                "(OpenAI/Anthropic), run open models (Llama/Mistral/HF), or train their own?\n"
                f"  commercialization: one of {COMMERCIALIZATION} — published prices, "
                "'contact sales' only, waitlist, or free/research\n"
                "  regulatory: comma-separated compliance regimes named (HIPAA, SOC2, "
                "GDPR, FDA, CE) or null\n"
                "  open_source: true/false — do they publish their own code/models?\n"
                "  confidence: 0.0-1.0"
            )
            raw = _call_llm([{"role": "user", "content": prompt}])
            if raw is None:
                llm_ok = False
            data = _parse_json(raw or "") or {}
            conf = float(data.get("confidence", 0.5) or 0.5)
            for col in ["location_city", "location_country", "team_size_bucket",
                        "product_status", "accelerator", "regulatory"]:
                v = data.get(col)
                if v and str(v).lower() not in ("null", "unknown", "none", ""):
                    fields[col] = str(v)[:128]
                    src[col] = {"source": "website", "confidence": conf}
            # constrained vocabularies — drop anything off-list so the aggregate stays clean
            if data.get("ai_stack") in AI_STACK and data["ai_stack"] != "not_stated":
                fields["ai_stack"] = data["ai_stack"]
                src["ai_stack"] = {"source": "website", "confidence": conf}
            if (data.get("commercialization") in COMMERCIALIZATION
                    and data["commercialization"] != "not_stated"):
                fields["commercialization"] = data["commercialization"]
                src["commercialization"] = {"source": "website", "confidence": conf}
            if isinstance(data.get("open_source"), bool):
                fields["open_source"] = data["open_source"]
                src["open_source"] = {"source": "website", "confidence": conf}
            if not blurb and data.get("description"):
                blurb = str(data["description"])
                fields["_new_description"] = blurb
                src["description"] = {"source": "website", "confidence": conf}
        # 3) if we just learned what they do, classify it now — otherwise this
        #    company would sit unclassified until the next tier-1 pass.
        if blurb and not row["description"]:
            tags = classify_from_text(name, blurb)
            if tags:
                tconf = float(tags.get("confidence", 0.5) or 0.5)
                for col in ("sector", "ai_application", "ai_subfield", "business_model",
                            "target_customer", "problem_solved"):
                    v = tags.get(col)
                    if v:
                        fields[col] = str(v)[:300]
                        src[col] = {"source": "llm_from_website", "confidence": tconf}
        return row["id"], domain, blurb, fields, src, llm_ok

    done = stalled = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, r) for r in rows]
        for f in as_completed(futs):
            cid, domain, blurb, fields, src, llm_ok = f.result()
            if not llm_ok:
                stalled += 1
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
                # stamp the attempt only when the model actually ran: a dead
                # site is a real attempt, a credit-out is not.
                if llm_ok:
                    mark_attempt(engine, cid, "web_attempted_at")
            done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(rows)}", flush=True)
    if stalled:
        print(f"  ! {stalled}/{len(rows)} rows had no LLM response (credits/keys?) "
              f"— left unstamped for a later pass", flush=True)
    print(f"✓ web done ({'dry-run' if dry_run else 'written'})", flush=True)


# ── Tier 3: founders / founding year / recent funding (hard) ─────────
def stage_deep(engine, limit: int, workers: int, min_conf: float, dry_run: bool) -> None:
    with engine.connect() as c:
        rows = c.execute(text(f"""
            SELECT c.id, c.name, c.domain
            FROM companies c
            LEFT JOIN company_enrichment e ON e.company_id = c.id
            WHERE {HIDDEN} AND {ai_filter_sql('c')}
              AND e.deep_attempted_at IS NULL
              AND (e.founders IS NULL OR e.founding_year IS NULL OR e.recent_funding IS NULL)
            ORDER BY (c.domain IS NULL)   -- a known domain disambiguates same-name startups
            LIMIT :lim
        """), {"lim": limit}).mappings().all()
    print(f"deep: {len(rows)} hidden AI companies for founder/funding/year search")

    def work(row):
        name = row["name"]
        # Include the domain in the query when we have one — startup names
        # collide constantly, and the site is the cheapest disambiguator.
        query = f"{name} startup founder funding founded"
        if row["domain"]:
            query = f'{name} {row["domain"]} founder funding founded'
        ctx = "\n".join(
            f"- {h.get('title','')}: {h.get('content','')[:200]}"
            for h in tavily_search(query, max_results=5)
        )
        if not ctx.strip():
            return row["id"], None, True       # search genuinely returned nothing
        prompt = (
            f"Search snippets about the startup {name!r}:\n{ctx[:3500]}\n\n"
            "Extract JSON (null when the snippets don't clearly say):\n"
            "  founders: list of {name, title} (only if clearly this company's founders)\n"
            "  founding_year: integer year\n"
            "  recent_funding: short string e.g. 'Seed $2M (2024)'\n"
            "  confidence: 0.0-1.0 — be strict; many startups share names\n"
            "Only include a field if the snippets are actually about THIS company."
        )
        raw = _call_llm([{"role": "user", "content": prompt}])
        if raw is None:
            return row["id"], None, False      # model never ran — don't stamp
        data = _parse_json(raw) or {}
        conf = float(data.get("confidence", 0.0) or 0.0)
        if conf < min_conf:
            return row["id"], None, True
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
        return row["id"], ((fields, src) if fields else None), True

    done = stalled = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, r) for r in rows]
        for f in as_completed(futs):
            cid, res, llm_ok = f.result()
            if not llm_ok:
                stalled += 1
            if not dry_run:
                if res:
                    upsert(engine, cid, res[0], res[1])
                if llm_ok:
                    mark_attempt(engine, cid, "deep_attempted_at")
            done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(rows)}", flush=True)
    if stalled:
        print(f"  ! {stalled}/{len(rows)} rows had no LLM response (credits/keys?) "
              f"— left unstamped for a later pass", flush=True)
    print(f"✓ deep done ({'dry-run' if dry_run else 'written'})", flush=True)


# ── WHOIS stage: founding-year proxy + discovery lag (free) ──────────
def stage_whois(engine, limit: int, workers: int, dry_run: bool,
                all_hidden: bool = False) -> None:
    """Fill domain_created_year for hidden companies that have a domain.

    This is the cheapest fix for the dataset's worst gap: founding year sits at
    ~13% coverage, which is what makes cohort/trend analysis fragile. WHOIS is
    free and hits ~70% of domained companies. It is a *proxy* — the domain
    registration date, not the incorporation date — and must be reported as one.

    By default this is limited to companies already classified as AI, which is
    only a few hundred rows once they have been attempted. --all-hidden drops
    that restriction: a hidden company that has not been classified yet may
    still be an AI company, and since WHOIS costs nothing there is no reason to
    make it wait for a classification we cannot currently pay for.
    """
    ai_clause = "" if all_hidden else f"AND {ai_filter_sql('c')}"
    with engine.connect() as c:
        rows = c.execute(text(f"""
            SELECT c.id, c.name, c.domain
            FROM companies c
            LEFT JOIN company_enrichment e ON e.company_id = c.id
            WHERE {HIDDEN} {ai_clause}
              AND c.domain IS NOT NULL
              AND e.whois_attempted_at IS NULL
            LIMIT :lim
        """), {"lim": limit}).mappings().all()
    print(f"whois: {len(rows)} domained hidden companies"
          f"{'' if all_hidden else ' (AI-classified only)'}", flush=True)

    def work(row):
        return row["id"], whois_year(row["domain"])

    done = hit = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in as_completed([ex.submit(work, r) for r in rows]):
            cid, yr = f.result()
            if yr:
                hit += 1
            if not dry_run:
                if yr:
                    upsert(engine, cid,
                           {"domain_created_year": yr},
                           {"domain_created_year": {"source": "whois",
                                                    "confidence": 0.6}})
                mark_attempt(engine, cid, "whois_attempted_at")
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(rows)}  (year found: {hit})", flush=True)
    print(f"✓ whois done — year for {hit}/{len(rows)} "
          f"({'dry-run' if dry_run else 'written'})", flush=True)


def llm_available() -> bool:
    """One cheap probe before a long stage starts.

    Three runs so far died on exhausted credits partway through and then spun
    for hours doing nothing. Failing loudly at the start is far better than
    discovering it in the logs the next morning. (whois needs no LLM, so it
    skips this check.)"""
    reply = _call_llm([{"role": "user", "content": "Reply with: ok"}])
    return bool(reply)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["classify", "web", "deep", "whois"])
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--min-confidence", type=float, default=0.5)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--have-domain", action="store_true",
                    help="web: only companies that already have a domain (no Tavily spend)")
    ap.add_argument("--all-hidden", action="store_true",
                    help="whois: do not restrict to already-AI-classified companies")
    a = ap.parse_args()

    engine = get_engine()
    ensure_table(engine)
    if a.stage != "whois" and not llm_available():
        print("! LLM backend unavailable (credits/keys) — stopping before the stage "
              "starts so nothing gets marked as attempted.", flush=True)
        sys.exit(2)
    if a.stage == "classify":
        stage_classify(engine, a.limit, a.workers, a.dry_run, a.all_hidden)
    elif a.stage == "web":
        stage_web(engine, a.limit, a.workers, a.dry_run, a.all_hidden, a.have_domain)
    elif a.stage == "deep":
        stage_deep(engine, a.limit, a.workers, a.min_confidence, a.dry_run)
    elif a.stage == "whois":
        stage_whois(engine, a.limit, a.workers, a.dry_run, a.all_hidden)


if __name__ == "__main__":
    main()
