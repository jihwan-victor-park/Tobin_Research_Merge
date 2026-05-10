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
        "Pioneer Fund portfolio companies AI startups",
        "Neo accelerator portfolio companies AI",
        "Z Fellows portfolio companies AI startups",
        "American university startup incubator portfolio companies AI 2026",
        "US deep tech seed fund portfolio companies AI startups",
    ],
    "UK": [
        "Notion Capital portfolio companies UK AI startups",
        "Atomico portfolio companies European AI startups",
        "Oxford University Innovation spinouts portfolio companies",
        "Entrepreneur First EF UK portfolio alumni companies",
        "Deepmind spinout UK AI startup accelerator portfolio",
    ],
    "KR": [
        "Kakao Ventures portfolio companies Korea AI startups",
        "Softbank Ventures Korea portfolio AI startups",
        "Korea Creative Economy Innovation Center portfolio companies",
        "POSTECH startup incubator portfolio companies Korea",
        "Altos Ventures Korea portfolio companies AI",
    ],
    "IN": [
        "CIIE IIM Ahmedabad portfolio companies India AI startups",
        "iCreate India portfolio companies AI startups",
        "IIT Bombay incubator portfolio companies startups",
        "Surge Sequoia India portfolio companies startups",
        "Blume Ventures portfolio companies India AI startups",
    ],
    "IL": [
        "JVP Jerusalem Venture Partners portfolio companies Israel AI",
        "Disruptive AI Israel portfolio companies startups",
        "8200 EISP alumni companies Israel AI startups",
        "OurCrowd portfolio companies Israel AI startups",
        "Team8 portfolio companies Israel AI cybersecurity",
    ],
    "DE": [
        "High-Tech Gründerfonds HTGF portfolio companies Germany AI",
        "Earlybird venture capital portfolio companies Germany AI",
        "Berlin startup incubator portfolio companies AI 2026",
        "UnternehmerTUM portfolio companies Munich AI startups",
        "Project A Ventures portfolio companies Germany AI",
    ],
    "FR": [
        "Station F startups portfolio companies France AI",
        "BPIFrance startup portfolio companies France AI",
        "Elaia Partners portfolio companies France AI startups",
        "Kima Ventures portfolio companies France AI startups",
        "France Paris AI accelerator portfolio companies 2026",
    ],
    "SG": [
        "SGInnovate portfolio companies Singapore AI deep tech",
        "Wavemaker Partners portfolio companies Singapore AI",
        "NUS Enterprise BLOCK71 portfolio companies Singapore",
        "Jungle Ventures portfolio companies Singapore AI startups",
        "Vertex Ventures portfolio companies Singapore AI",
    ],
    "SE": [
        "EQT Ventures portfolio companies Sweden AI startups",
        "Northzone portfolio companies Sweden AI startups",
        "STING Stockholm portfolio companies Sweden AI",
        "Industrifonden portfolio companies Sweden AI startups",
        "Creandum portfolio companies Sweden AI startups",
    ],
    "CA": [
        "Creative Destruction Lab CDL portfolio companies Canada AI",
        "MaRS Discovery District portfolio companies Canada AI",
        "Communitech portfolio companies Waterloo Canada AI",
        "Real Ventures portfolio companies Canada AI startups",
        "BDC Capital portfolio companies Canada AI startups",
    ],
    "AU": [
        "Startmate portfolio companies Australia AI startups",
        "Blackbird Ventures portfolio companies Australia AI",
        "Main Sequence Ventures portfolio companies Australia AI",
        "Reinventure portfolio companies Australia AI fintech",
        "CSIRO ON accelerator portfolio companies Australia",
    ],
    "BR": [
        "Distrito portfolio companies Brazil AI startups",
        "Canary VC portfolio companies Brazil AI startups",
        "Monashees portfolio companies Brazil AI startups",
        "Redpoint eventures portfolio companies Brazil AI",
        "Bossanova Investimentos portfolio companies Brazil AI",
    ],
    "AE": [
        "Hub71 Abu Dhabi portfolio companies UAE AI startups",
        "In5 Dubai portfolio companies UAE AI startups",
        "DIFC FinTech Hive portfolio companies UAE fintech AI",
        "Wamda Capital portfolio companies UAE AI startups",
        "Dubai Future Foundation portfolio companies AI startups",
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
            category=cand.category,
        )
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
    "You judge whether a URL is the OFFICIAL portfolio or companies page of a "
    "startup investor, accelerator, or incubator program. Reply with JSON only:\n"
    '{"is_portfolio": true|false, "category": one of '
    '"university_incubator","accelerator","vc_portfolio",'
    '"discovery_aggregator","government_program","other", '
    '"country": ISO-3166 alpha-2 country code (best guess), '
    '"confidence": 0.0-1.0}.\n'
    "Set is_portfolio=true ONLY if ALL of the following hold:\n"
    "1. The domain is the PRIMARY owner of the portfolio (e.g. sequoiacap.com, "
    "ycombinator.com) — NOT a third-party listing or aggregator site "
    "(e.g. crunchbase.com, dealroom.co, tracxn.com, vcbeast.com, "
    "privateequitylist.com, vcbacked.co, pitchbook.com, cbinsights.com).\n"
    "2. The page clearly lists multiple portfolio/investee companies.\n"
    "3. The domain is not a large incumbent corporation (Fortune 500, "
    "public company) unless the URL is an explicitly dedicated standalone "
    "venture/accelerator program subdomain.\n"
    "Set is_portfolio=false for blog posts, news articles, generic homepages, "
    "or any third-party site listing someone else's portfolio."
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
