#!/usr/bin/env python3
"""
AI Company Resolver — quantitative sourcing / enrichment with Tavily + Claude.
===============================================================================
The single biggest data-quality hole in `companies` is that ~30% of rows are
"non-registered": a name was scraped off a portfolio/listing page that never
linked the company's own website, so the row has no `domain` (and usually no
country/description either). Those rows can't dedup cleanly, can't be verified,
and don't show up on the globe.

This tool *resolves* those rows. For each under-registered company it:

  1. Tavily web search  — "{name} startup official website" (+ industry/country
     hints when we have them). One Basic search ≈ $0.005.
  2. Claude extraction  — hands the search hits to Claude (Haiku by default via
     ANTHROPIC_MODEL) which picks the company's OWN homepage domain (never a
     directory / social / news host) and pulls country, city, description,
     founded_year, and an is-AI judgement as strict JSON.
  3. DB write           — fills the missing columns. The unique `domain`
     constraint is respected: if another company already owns the resolved
     domain we keep this row's domain NULL and still backfill the other
     fields, logging the collision for a later merge pass.

One Tavily + one Claude call backfills every missing field at once, so the same
run that "registers" a company also enriches its location and description.

Usage:
    # Preview what the first 20 unregistered AI companies would resolve to:
    python scripts/enrich_companies_with_ai.py --dry-run --limit 20

    # Actually register the 200 highest-value unregistered companies:
    python scripts/enrich_companies_with_ai.py --limit 200

    # Resolve everything missing a domain (slow + costs $$ — Tavily per row):
    python scripts/enrich_companies_with_ai.py --target domain --limit 0

Flags:
    --target {domain,location,description,any}  which gap selects a company
    --order  {ai_first,recent,id}               processing priority
    --limit N      max companies (0 = all; default 100)
    --workers N    parallel Tavily+Claude workers (network-bound; default 8)
    --min-confidence F   skip writes below this Claude confidence (default 0.55)
    --dry-run      resolve + print, write nothing
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.db.connection import session_scope  # noqa: E402
from backend.db.models import Company, LocationSource  # noqa: E402
from backend.utils.domain import canonicalize_domain, is_product_domain  # noqa: E402

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("enrich_companies")

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

# Hosts that are never a company's own homepage. If Claude returns one of these
# we reject it — they're directories, social, code hosts, or news.
BAD_RESOLVED_HOSTS = frozenset({
    "linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com",
    "youtube.com", "crunchbase.com", "pitchbook.com", "wikipedia.org",
    "github.com", "medium.com", "substack.com", "techcrunch.com",
    "bloomberg.com", "forbes.com", "producthunt.com", "g2.com",
    "glassdoor.com", "indeed.com", "tracxn.com", "owler.com",
})


# ── Tavily ────────────────────────────────────────────────────────────────

def tavily_search(query: str, max_results: int = 5) -> List[dict]:
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
        "include_answer": False,
    }
    try:
        r = requests.post(TAVILY_SEARCH_URL, json=payload, timeout=30)
        r.raise_for_status()
    except requests.RequestException as exc:
        logger.debug(f"tavily err on '{query[:50]}': {exc}")
        return []
    return r.json().get("results", []) or []


# ── Claude extraction ──────────────────────────────────────────────────────

_SYSTEM = (
    "You resolve a startup's canonical identity from web search results. "
    "You are given the company name, any hints we already have, and a list of "
    "search results (title, url, snippet). Return STRICT JSON only, no prose:\n"
    '{"official_domain": str|null, "country": str|null, "city": str|null, '
    '"description": str|null, "founded_year": int|null, '
    '"is_ai": bool, "confidence": 0.0-1.0}\n'
    "Rules:\n"
    "- official_domain = the company's OWN homepage registrable domain "
    "(e.g. 'acme.ai'), lowercased, no scheme/path. NEVER a directory, social "
    "network, news site, app store, or code host. If none of the results is "
    "clearly THIS company's own site, set official_domain to null.\n"
    "- country = ISO 3166-1 alpha-2 (e.g. 'US', 'GB', 'KR'). null if unknown.\n"
    "- description = one neutral sentence on what the company does. null if unknown.\n"
    "- is_ai = true only if the core product applies ML/LLMs/computer vision/"
    "robotics/etc. Merely 'using AI' internally is false.\n"
    "- confidence = how sure you are that official_domain belongs to THIS "
    "company. Be conservative when the name is generic or results are ambiguous."
)


# LLM is optional. If every configured backend is out of credits / unkeyed we
# flip this flag once and never retry — the run continues on the Tavily-only
# heuristic resolver below instead of burning time on dead endpoints.
_LLM_DISABLED = False
_LLM_WARNED = False


def _llm_available() -> bool:
    return not _LLM_DISABLED and bool(
        ANTHROPIC_API_KEY or os.getenv("TOGETHER_API_KEY") or os.getenv("GROQ_API_KEY")
    )


def _call_llm(messages: List[Dict], temperature: float = 0.0) -> Optional[str]:
    """Try the configured LLM backend, then any other keyed one. Returns the
    text response, or None (and disables LLM for the rest of the run) when no
    backend is usable — e.g. credit-exhausted keys."""
    global _LLM_DISABLED, _LLM_WARNED
    if _LLM_DISABLED:
        return None
    try:
        from backend.utils.llm_filter import (
            _call_anthropic, _call_groq, _call_together,
            ANTHROPIC_API_KEY as AK, GROQ_API_KEY as GK,
            TOGETHER_API_KEY as TK, LLM_BACKEND,
        )
    except Exception:
        _LLM_DISABLED = True
        return None

    order = [LLM_BACKEND.lower(), "anthropic", "together", "groq"]
    seen = set()
    transports = {"anthropic": (_call_anthropic, AK), "together": (_call_together, TK),
                  "groq": (_call_groq, GK)}
    auth_failures = 0
    tried = 0
    for backend in order:
        if backend in seen or backend not in transports:
            continue
        seen.add(backend)
        fn, key = transports[backend]
        if not key:
            continue
        tried += 1
        try:
            return fn(messages, temperature=temperature)
        except Exception as e:
            err = str(e).lower()
            if any(s in err for s in ("402", "credit", "balance", "401", "invalid", "quota")):
                auth_failures += 1
            logger.debug(f"{backend} llm call failed: {str(e)[:120]}")
            continue
    # Every keyed backend failed on auth/credits → stop trying for this run.
    if tried and auth_failures >= tried:
        _LLM_DISABLED = True
        if not _LLM_WARNED:
            _LLM_WARNED = True
            logger.warning("All LLM backends are unusable (credits/keys). "
                           "Falling back to Tavily-only heuristic domain resolution.")
    return None


def _parse_json(raw: str) -> Optional[dict]:
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None


# ── Heuristic fallback (no LLM) ──────────────────────────────────────────────

def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def heuristic_resolve(name: str, results: List[dict]) -> Optional[dict]:
    """Pick the company's own domain from Tavily hits by fuzzy-matching the
    name against each result's registrable domain. Used when no LLM is
    available. Precision-first: only returns a domain on a strong match."""
    try:
        from rapidfuzz import fuzz
    except Exception:
        fuzz = None

    norm = _alnum(name)
    # AI companies frequently drop an 'ai'/'hq'/'app' suffix in their domain.
    variants = {norm}
    for suf in ("ai", "hq", "app", "io", "labs", "inc"):
        if norm.endswith(suf) and len(norm) > len(suf) + 2:
            variants.add(norm[: -len(suf)])
    if not norm:
        return None

    best = None  # (confidence, domain)
    for rank, r in enumerate(results[:5]):
        url = (r.get("url") or "").strip()
        dom = canonicalize_domain(url)
        if not dom:
            continue
        host = dom.lower()
        if host in BAD_RESOLVED_HOSTS or any(host.endswith("." + b) for b in BAD_RESOLVED_HOSTS):
            continue
        if not is_product_domain(dom):
            continue
        dom_name = _alnum(dom.rsplit(".", 1)[0])  # registrable name, no TLD
        if not dom_name:
            continue

        conf = 0.0
        for v in variants:
            if v == dom_name:
                conf = max(conf, 0.92)
            elif dom_name.startswith(v) or v.startswith(dom_name):
                # strong containment (e.g. 'scale' vs 'scaleai')
                ratio = min(len(v), len(dom_name)) / max(len(v), len(dom_name))
                if ratio >= 0.6:
                    conf = max(conf, 0.78)
            elif fuzz is not None:
                f = fuzz.ratio(v, dom_name) / 100.0
                if f >= 0.88:
                    conf = max(conf, 0.7 * f)
        # Slightly favor higher-ranked Tavily results on ties.
        conf -= rank * 0.01
        if conf > 0 and (best is None or conf > best[0]):
            best = (conf, dom)

    if best is None or best[0] < 0.55:
        return None
    return {
        "domain": best[1],
        "country": None,
        "city": None,
        "description": None,
        "founded_year": None,
        "is_ai": False,  # keyword pass happens elsewhere; stay conservative here
        "confidence": round(best[0], 2),
        "method": "heuristic",
    }


def resolve_company(company: dict) -> Optional[dict]:
    """Tavily + LLM (or heuristic) -> normalized resolution dict (no DB).

    Returns None if the company could not be resolved at all.
    """
    name = (company.get("name") or "").strip()
    if not name:
        return None

    # Build a search query enriched with whatever we already know.
    hint_bits = [name, "startup official website"]
    if company.get("industry"):
        hint_bits.insert(1, company["industry"])
    if company.get("country"):
        hint_bits.append(company["country"])
    query = " ".join(hint_bits)

    results = tavily_search(query, max_results=5)
    if not results:
        return None

    # No LLM budget? Resolve the domain heuristically from the same hits.
    if not _llm_available():
        return heuristic_resolve(name, results)

    # Compact the hits for the prompt.
    blocks = []
    for r in results[:5]:
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        snippet = (r.get("content") or "").strip()[:300]
        blocks.append(f"- title: {title}\n  url: {url}\n  snippet: {snippet}")
    hints = []
    if company.get("description"):
        hints.append(f"known_description: {company['description'][:200]}")
    if company.get("industry"):
        hints.append(f"known_industry: {company['industry']}")
    if company.get("country"):
        hints.append(f"known_country: {company['country']}")

    user = (
        f"Company name: {name}\n"
        + (("Hints:\n" + "\n".join(hints) + "\n") if hints else "")
        + "Search results:\n"
        + "\n".join(blocks)
        + "\n\nReturn the JSON now."
    )
    raw = _call_llm([
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ])
    data = _parse_json(raw or "")
    if data is None:
        # LLM became unavailable mid-run (or returned junk) — heuristic fallback.
        return heuristic_resolve(name, results)

    # Normalize + validate the resolved domain.
    dom = data.get("official_domain")
    if dom:
        dom = canonicalize_domain(str(dom))
    if dom:
        host = dom.lower()
        if host in BAD_RESOLVED_HOSTS or any(host.endswith("." + b) for b in BAD_RESOLVED_HOSTS):
            dom = None
        elif not is_product_domain(dom):
            dom = None

    country = data.get("country")
    if isinstance(country, str):
        country = country.strip().upper()[:2] or None

    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    founded = data.get("founded_year")
    try:
        founded = int(founded) if founded else None
        if founded and (founded < 1900 or founded > 2100):
            founded = None
    except (TypeError, ValueError):
        founded = None

    return {
        "domain": dom,
        "country": country,
        "city": (data.get("city") or None),
        "description": (data.get("description") or None),
        "founded_year": founded,
        "is_ai": bool(data.get("is_ai")),
        "confidence": max(0.0, min(1.0, confidence)),
    }


# ── Selection ───────────────────────────────────────────────────────────────

def select_companies(target: str, order: str, limit: int) -> List[dict]:
    """Load the under-registered companies to work on (as plain dicts)."""
    with session_scope() as s:
        q = s.query(Company)
        if target == "domain":
            q = q.filter((Company.domain.is_(None)) | (Company.domain == ""))
        elif target == "location":
            q = q.filter(Company.country.is_(None))
        elif target == "description":
            q = q.filter((Company.description.is_(None)) | (Company.description == ""))
        else:  # any
            q = q.filter(
                (Company.domain.is_(None)) | (Company.domain == "")
                | (Company.country.is_(None))
                | (Company.description.is_(None)) | (Company.description == "")
            )

        if order == "ai_first":
            q = q.order_by(Company.ai_score.desc().nullslast(), Company.last_seen_at.desc().nullslast())
        elif order == "recent":
            q = q.order_by(Company.last_seen_at.desc().nullslast())
        else:
            q = q.order_by(Company.id.asc())

        if limit and limit > 0:
            q = q.limit(limit)

        return [
            {
                "id": c.id,
                "name": c.name,
                "domain": c.domain,
                "country": c.country,
                "city": c.city,
                "description": c.description,
                "industry": None,  # companies table has no industry col; left for hints parity
                "ai_score": c.ai_score,
            }
            for c in q.all()
        ]


# ── Write-back ──────────────────────────────────────────────────────────────

def apply_resolution(session, company: Company, res: dict, min_conf: float) -> str:
    """Mutate `company` in place. Returns a short outcome tag for stats."""
    changed = []

    dom = res.get("domain")
    if dom and not company.domain and res["confidence"] >= min_conf:
        # Respect the unique-domain constraint.
        owner = (
            session.query(Company.id)
            .filter(Company.domain == dom, Company.id != company.id)
            .first()
        )
        if owner is None:
            company.domain = dom
            changed.append("domain")
        else:
            changed.append("domain_conflict")

    if res.get("country") and not company.country:
        company.country = res["country"]
        company.city = res.get("city") or company.city
        company.location_source = LocationSource.unknown
        changed.append("country")

    if res.get("description") and not company.description:
        company.description = res["description"]
        changed.append("description")

    if res.get("founded_year") and not company.founded_year:
        company.founded_year = res["founded_year"]
        changed.append("founded_year")

    if res.get("is_ai") and (company.ai_score is None or company.ai_score < 0.6):
        company.ai_score = max(company.ai_score or 0.0, 0.7)
        changed.append("ai_score")

    if not changed:
        return "no_change"
    if "domain" in changed:
        return "registered"
    if "domain_conflict" in changed:
        return "enriched_conflict"
    return "enriched"


# ── Main ────────────────────────────────────────────────────────────────────

def run(target: str, order: str, limit: int, workers: int, min_conf: float, dry_run: bool):
    companies = select_companies(target, order, limit)
    if not companies:
        logger.info("Nothing to do — no companies match the selection.")
        return

    est_cost = len(companies) * 0.005
    mode = f"LLM extraction ({ANTHROPIC_MODEL})" if _llm_available() else "Tavily-only heuristic (no LLM credits)"
    logger.info(
        f"Selected {len(companies)} companies (target={target}, order={order}). "
        f"~${est_cost:.2f} Tavily ceiling. Resolution mode: {mode}."
    )

    stats = {"resolved": 0, "registered": 0, "enriched": 0,
             "enriched_conflict": 0, "no_change": 0, "unresolved": 0}

    # Phase 1: resolve in parallel (network only, thread-safe — no DB sessions).
    resolutions: Dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(resolve_company, c): c for c in companies}
        for i, fut in enumerate(as_completed(futs), start=1):
            c = futs[fut]
            try:
                res = fut.result()
            except Exception as e:
                logger.debug(f"resolve failed for {c['name']}: {e}")
                res = None
            if res is None:
                stats["unresolved"] += 1
            else:
                stats["resolved"] += 1
                resolutions[c["id"]] = res
                if dry_run:
                    logger.info(
                        f"  {c['name'][:40]:40s} -> domain={res['domain']} "
                        f"country={res['country']} ai={res['is_ai']} conf={res['confidence']:.2f}"
                    )
            if i % 50 == 0:
                logger.info(f"  resolved {i}/{len(companies)}...")

    if dry_run:
        logger.info("=" * 60)
        logger.info(f"DRY RUN — resolved {stats['resolved']}, unresolved {stats['unresolved']}. No writes.")
        return

    # Phase 2: write serially in one session.
    with session_scope() as session:
        for cid, res in resolutions.items():
            company = session.get(Company, cid)
            if company is None:
                continue
            outcome = apply_resolution(session, company, res, min_conf)
            if outcome == "registered":
                stats["registered"] += 1
            elif outcome == "enriched":
                stats["enriched"] += 1
            elif outcome == "enriched_conflict":
                stats["enriched_conflict"] += 1
            else:
                stats["no_change"] += 1

    logger.info("=" * 60)
    logger.info("Enrichment complete!")
    logger.info(f"  selected        : {len(companies)}")
    logger.info(f"  resolved (LLM)  : {stats['resolved']}")
    logger.info(f"  unresolved      : {stats['unresolved']}")
    logger.info(f"  newly registered: {stats['registered']}  (domain set)")
    logger.info(f"  enriched only   : {stats['enriched']}  (country/desc, no domain)")
    logger.info(f"  domain conflicts: {stats['enriched_conflict']}  (domain owned by another row)")
    logger.info(f"  no change       : {stats['no_change']}")
    logger.info("=" * 60)


def main():
    p = argparse.ArgumentParser(description="Resolve/enrich under-registered companies with Tavily + Claude")
    p.add_argument("--target", choices=["domain", "location", "description", "any"], default="domain")
    p.add_argument("--order", choices=["ai_first", "recent", "id"], default="ai_first")
    p.add_argument("--limit", type=int, default=100, help="Max companies (0 = all)")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--min-confidence", type=float, default=0.55)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if not TAVILY_API_KEY:
        sys.exit("TAVILY_API_KEY not set")
    if not ANTHROPIC_API_KEY:
        sys.exit("ANTHROPIC_API_KEY not set")

    run(
        target=args.target,
        order=args.order,
        limit=args.limit,
        workers=args.workers,
        min_conf=args.min_confidence,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
