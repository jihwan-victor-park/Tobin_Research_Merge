"""
Scout agent — find candidate accelerator/incubator/VC portfolio URLs we don't
already cover, in a chosen country.

Pipeline:
  1. Search Tavily with rotated queries (one round-trip per query).
  2. Drop URLs whose canonical domain is already in site_health.
  3. Validate each candidate with one Anthropic call to confirm it's a
     portfolio page, classify category, and tag country.
  4. Register surviving sites via HealthMonitor.register_site() so they
     show up as Pending in the dashboard.

Returns the list of newly registered ScoutCandidate objects so callers can
report counts.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import List, Optional

import requests

from backend.db.connection import session_scope
from backend.db.models import SiteHealth
from backend.orchestrator.health import HealthMonitor
from backend.utils.domain import canonicalize_domain, is_product_domain

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"

# Queries are tuned to surface portfolio pages, not blog posts. The country
# token is interpolated; if the user asks for a country we don't have queries
# for we just append "in {country}" to a generic query set.
_QUERIES_BY_COUNTRY = {
    "US": [
        "AI accelerator portfolio United States",
        "top startup incubators United States 2026",
        "university entrepreneurship program portfolio US",
        "venture capital portfolio companies AI United States",
        "best startup accelerators in the US 2026",
    ],
    "UK": [
        "AI accelerator portfolio United Kingdom",
        "London startup incubators 2026",
        "UK university entrepreneurship program portfolio",
        "British venture capital portfolio companies AI",
        "UK deep tech accelerator portfolio 2026",
    ],
    "KR": [
        "South Korea startup accelerator portfolio",
        "Seoul AI startup incubator companies",
        "Korean venture capital portfolio AI startups",
        "TIPS program Korea portfolio companies",
    ],
    "IN": [
        "India AI startup accelerator portfolio 2026",
        "NASSCOM startup ecosystem portfolio companies",
        "IIT incubator portfolio AI companies India",
        "Indian venture capital portfolio AI startups",
        "Startup India DPIIT recognized accelerator portfolio",
        "iCreate CIIE SIDBI startup fund portfolio India",
    ],
    "IL": [
        "Israel tech accelerator portfolio AI startups 2026",
        "Tel Aviv startup accelerator portfolio companies",
        "Israel Innovation Authority funded startups",
        "Israeli venture capital AI portfolio companies",
        "8200 EISP alumni companies Israel",
    ],
    "DE": [
        "Germany AI startup accelerator portfolio 2026",
        "High-Tech Gründerfonds portfolio companies",
        "EXIST Gründerstipendium startup portfolio Germany",
        "Berlin startup incubator portfolio AI",
        "German deep tech venture capital portfolio",
    ],
    "FR": [
        "France AI startup accelerator portfolio 2026",
        "Station F companies portfolio AI startups",
        "BPIFrance startup portfolio companies",
        "French Tech accelerator portfolio 2026",
        "Paris startup incubator portfolio AI companies",
    ],
    "SG": [
        "Singapore AI startup accelerator portfolio 2026",
        "SGInnovate portfolio companies AI",
        "Enterprise Singapore startup portfolio",
        "NUS BLOCK71 startups Singapore portfolio",
        "Singapore venture capital AI portfolio companies",
    ],
    "SE": [
        "Sweden startup accelerator portfolio 2026",
        "Stockholm AI startup incubator companies",
        "EQT Ventures portfolio companies Sweden",
        "Swedish deep tech venture capital portfolio AI",
        "Nordic startup accelerator portfolio companies",
    ],
    "CA": [
        "Canada AI startup accelerator portfolio 2026",
        "MaRS Discovery District portfolio companies",
        "Creative Destruction Lab CDL companies AI",
        "Canadian venture capital AI portfolio startups",
        "Communitech Waterloo startup portfolio",
    ],
    "AU": [
        "Australia AI startup accelerator portfolio 2026",
        "Startmate portfolio companies Australia",
        "Blackbird Ventures portfolio AI startups",
        "CSIRO ON accelerator portfolio companies",
        "Australian deep tech startup accelerator portfolio",
    ],
    "BR": [
        "Brazil startup accelerator portfolio 2026",
        "500 Startups LatAm portfolio companies Brazil",
        "Softbank LatAm portfolio AI startups Brazil",
        "Brazilian venture capital portfolio AI companies",
        "Cubo Itaú startup portfolio Brazil",
    ],
    "AE": [
        "UAE startup accelerator portfolio 2026",
        "Hub71 Abu Dhabi portfolio companies AI",
        "In5 Dubai startup portfolio companies",
        "DIFC FinTech Hive portfolio UAE",
        "Middle East venture capital AI portfolio startups",
    ],
}


@dataclass
class ScoutCandidate:
    url: str
    domain: str
    category: str          # university_incubator | accelerator | vc_portfolio | discovery_aggregator | government_program | other
    country: str
    confidence: float
    title: Optional[str] = None


def scout(country: str = "US", limit: int = 20) -> List[ScoutCandidate]:
    """Find new portfolio URLs and register them. Returns the registered set."""
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        logger.warning("TAVILY_API_KEY not set — scout cannot run")
        return []

    queries = _QUERIES_BY_COUNTRY.get(country.upper()) or [
        f"AI accelerator portfolio in {country}",
        f"top startup incubators in {country} 2026",
        f"venture capital portfolio companies AI in {country}",
    ]

    raw_hits: list[dict] = []
    for q in queries:
        raw_hits.extend(_tavily_search(api_key, q, max_results=10))
        if len(raw_hits) >= limit * 5:
            break

    # Dedup by canonical domain + drop sites we already track.
    existing = _existing_domains()
    seen: set[str] = set()
    candidates: list[dict] = []
    for h in raw_hits:
        url = (h.get("url") or "").strip()
        if not url:
            continue
        domain = canonicalize_domain(url)
        if not domain or not is_product_domain(domain):
            continue
        if domain in existing or domain in seen:
            continue
        seen.add(domain)
        candidates.append({"url": url, "domain": domain, "title": h.get("title")})
        if len(candidates) >= limit * 3:  # over-collect, validation will trim
            break

    logger.info(f"scout: {len(candidates)} unique novel domains pre-validation (country={country})")

    # Validate with the LLM and register the keepers.
    monitor = HealthMonitor()
    accepted: list[ScoutCandidate] = []
    for c in candidates:
        if len(accepted) >= limit:
            break
        verdict = _validate_with_llm(url=c["url"], title=c.get("title"), country=country)
        if verdict is None or not verdict.get("is_portfolio"):
            continue
        cand = ScoutCandidate(
            url=c["url"],
            domain=c["domain"],
            category=str(verdict.get("category") or "other"),
            country=str(verdict.get("country") or country.upper()),
            confidence=float(verdict.get("confidence") or 0.6),
            title=c.get("title"),
        )
        monitor.register_site(
            domain=cand.domain,
            url=cand.url,
            difficulty="hard",  # unknown sites default to the agentic engine
            scraper_name=f"scout:{country.lower()}",
        )
        # register_site doesn't take category — patch it in directly so the
        # row carries the inventory bucket from the start.
        with session_scope() as session:
            row = session.query(SiteHealth).filter(SiteHealth.domain == cand.domain).first()
            if row is not None:
                row.category = cand.category
        accepted.append(cand)
        logger.info(f"scout: accepted {cand.domain} ({cand.category}, conf={cand.confidence:.2f})")

    logger.info(f"scout: registered {len(accepted)} new site(s)")
    return accepted


def _existing_domains() -> set[str]:
    with session_scope() as session:
        return {d for (d,) in session.query(SiteHealth.domain).all()}


def _tavily_search(api_key: str, query: str, max_results: int = 10) -> list[dict]:
    try:
        resp = requests.post(
            TAVILY_SEARCH_URL,
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results,
                "include_answer": False,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            logger.warning(f"tavily search {resp.status_code}: {resp.text[:200]}")
            return []
        return resp.json().get("results", []) or []
    except Exception as e:
        logger.warning(f"tavily search failed: {e}")
        return []


_VALIDATE_PROMPT = (
    "You judge whether a URL is the portfolio/companies page of a startup "
    "investor or accelerator program. Reply with JSON only:\n"
    '{"is_portfolio": true|false, "category": one of '
    '"university_incubator","accelerator","vc_portfolio",'
    '"discovery_aggregator","government_program","other", '
    '"country": ISO-3166 alpha-2 country code (best guess), '
    '"confidence": 0.0-1.0}.\n'
    "Only true if the URL clearly lists multiple portfolio companies "
    "(not a blog post, news article, or generic homepage)."
)


def _validate_with_llm(url: str, title: Optional[str], country: str) -> Optional[dict]:
    try:
        from backend.utils.llm_filter import (
            _call_anthropic, _call_groq, _call_ollama, _call_together,
            ANTHROPIC_API_KEY, GROQ_API_KEY, TOGETHER_API_KEY, LLM_BACKEND,
        )
    except Exception as e:
        logger.debug(f"scout: LLM transport unavailable: {e}")
        return None

    backend = (LLM_BACKEND or "together").lower()
    call_fn = {
        "together": _call_together,
        "groq": _call_groq,
        "ollama": _call_ollama,
        "anthropic": _call_anthropic,
    }.get(backend)
    if call_fn is None:
        return None
    if backend == "together" and not TOGETHER_API_KEY:
        return None
    if backend == "anthropic" and not ANTHROPIC_API_KEY:
        return None

    user = (
        f"URL: {url}\nTitle: {title or '(none)'}\n"
        f"Hint: scouted for country={country.upper()}.\nReturn JSON only."
    )
    messages = [
        {"role": "system", "content": _VALIDATE_PROMPT},
        {"role": "user", "content": user},
    ]
    try:
        raw = call_fn(messages, temperature=0.0)
    except Exception as e:
        logger.debug(f"scout: LLM call failed for {url}: {e}")
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
