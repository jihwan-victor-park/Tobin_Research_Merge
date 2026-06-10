"""
Scout agent — find candidate accelerator/incubator/VC portfolio URLs we don't
already cover, in a chosen country.

Pipeline:
  1. Search Tavily with rotated queries (one round-trip per query).
     Queries span 5 source types per country: VC portfolios, accelerators,
     government programs, university incubators, and local startup directories.
  2. Drop URLs whose canonical domain is already in site_health.
  3. Fetch a snippet of each candidate page (visible text, first ~800 chars)
     to give the LLM real signal rather than just URL + title.
  4. Validate each candidate with one LLM call to confirm it's a portfolio
     page, classify category, and tag country.
  5. Register surviving sites via HealthMonitor.register_site() so they
     show up as Pending in the dashboard and get picked up by the agentic
     hard-tier engine.

Returns the list of newly registered ScoutCandidate objects.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from backend.db.connection import session_scope
from backend.db.models import SiteHealth
from backend.orchestrator.health import HealthMonitor
from backend.utils.domain import canonicalize_domain, is_product_domain

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
_PAGE_FETCH_TIMEOUT = 8   # seconds
_PAGE_SNIPPET_CHARS = 800  # visible text chars to send to the LLM

# ---------------------------------------------------------------------------
# Queries — 5 source types × ~12 queries per country
#
# Types:
#   vc       — VC firm portfolio pages
#   accel    — accelerator / incubator portfolio pages
#   gov      — government-backed programs
#   uni      — university incubator / tech-transfer programs
#   dir      — country-specific startup directories / aggregators
#
# Rule: queries must target pages that LIST companies, not news articles.
# They're designed to surface portfolio/companies/startups pages directly.
# ---------------------------------------------------------------------------

_QUERIES_BY_COUNTRY: dict[str, list[str]] = {

    # ── South Korea ────────────────────────────────────────────────────────
    # Focus: dense VC ecosystem, major government programs (TIPS, Born2Global),
    # university tech-transfer (KAIST, POSTECH, SNU), AI hardware & software
    "KR": [
        # Tier-1 VCs
        "Bon Angels Ventures portfolio companies Korea AI startups site:bonangels.net OR site:bonangels.com",
        "SoftBank Ventures Korea portfolio companies AI startups",
        "Kakao Ventures portfolio companies Korea AI",
        "Altos Ventures Korea portfolio companies AI",
        "Strong Ventures portfolio companies Seoul AI",
        "Korea Investment Partners KIP portfolio companies AI",
        "Naver D2 Startup Factory portfolio companies Korea AI",
        "Samsung Catalyst Fund portfolio companies Korea AI",
        # Accelerators / incubators
        "SparkLabs Seoul portfolio companies Korea AI startups",
        "Primer Sazze Partners portfolio companies Korea AI",
        "FastTrack Asia portfolio companies Korea AI",
        "Sprint Accelerator portfolio companies Korea AI",
        "Korea Startup Forum accelerator portfolio companies AI",
        "Starta Ventures Korea portfolio companies AI startups",
        # Government programs
        "TIPS Korea tech incubator startup portfolio companies AI 2025",
        "Born2Global Center Korea portfolio companies AI startup",
        "K-Startup Grand Challenge portfolio companies Korea 2025",
        "KISED Korea Institute startup development portfolio companies",
        "Korea Creative Economy Innovation Center CCEI portfolio AI",
        "KOICA startup program portfolio companies Korea AI",
        # University incubators
        "KAIST startup incubator portfolio companies Korea AI deep tech",
        "POSTECH startup incubator portfolio companies Korea AI",
        "Seoul National University SNU startup venture companies AI",
        "Yonsei University startup incubator portfolio companies Korea AI",
        "KAIST ICC startup companies Korea AI technology",
        # Native-language queries — surfaces Korean-only portfolio pages
        "본엔젤스 포트폴리오 스타트업 인공지능",
        "카카오벤처스 투자기업 인공지능 스타트업",
        "알토스벤처스 포트폴리오 AI 스타트업",
        "스파크랩 포트폴리오 스타트업 인공지능",
        "팁스 프로그램 선정기업 인공지능 스타트업",
        "본투글로벌 참여기업 AI 스타트업",
        "KAIST 창업 인큐베이터 포트폴리오 기업 AI",
        "포스텍 창업 스타트업 인공지능 기업",
        "서울대 창업 벤처 기업 인공지능",
    ],

    # ── Israel ─────────────────────────────────────────────────────────────
    # Focus: cybersecurity, AI infra, deep tech; strong government innovation
    # system; Unit 8200 alumni network; university spinout ecosystem
    "IL": [
        # Tier-1 VCs
        "JVP Jerusalem Venture Partners portfolio companies Israel AI",
        "Pitango Venture Capital portfolio companies Israel AI startups",
        "Team8 portfolio companies Israel AI cybersecurity",
        "OurCrowd portfolio companies Israel AI",
        "Grove Ventures portfolio companies Israel AI deep tech",
        "Viola Ventures portfolio companies Israel AI",
        "iAngels portfolio companies Israel AI startups",
        "Vertex Ventures Israel portfolio companies AI",
        "Entrée Capital portfolio companies Israel AI",
        "lool ventures portfolio companies Israel AI",
        # Accelerators
        "8200 EISP alumni startup companies Israel AI",
        "MassChallenge Israel portfolio companies AI",
        "Microsoft for Startups Israel portfolio companies AI",
        "Google for Startups Israel portfolio companies AI",
        "Nielsen portfolio companies Israel AI incubator",
        "Techstars Israel portfolio companies AI",
        # Government programs
        "Israel Innovation Authority incubator portfolio companies AI",
        "Israel Tech Challenge ITC portfolio companies AI",
        "Start-Up Nation Central portfolio companies Israel AI",
        "BIRD Foundation Israel USA portfolio companies AI",
        "Yozma Group portfolio companies Israel AI startups",
        # University spinouts
        "Technion TTO startup spinout companies Israel AI portfolio",
        "Hebrew University Yissum spinout companies Israel AI",
        "Weizmann Institute Yeda startup companies Israel AI",
        "Tel Aviv University Ramot spinout companies Israel AI",
        "Ben Gurion University BGN tech startup companies AI Israel",
    ],

    # ── China ──────────────────────────────────────────────────────────────
    # Focus: AI hardware, LLMs, robotics, autonomous vehicles; major national
    # parks; top VCs with English-accessible portfolio pages
    "CN": [
        # Tier-1 VCs
        "Sinovation Ventures Innovation Works portfolio companies China AI",
        "ZhenFund portfolio companies China AI startups English",
        "IDG Capital portfolio companies China AI",
        "HongShan Sequoia China portfolio companies AI",
        "Matrix Partners China portfolio companies AI startups",
        "Linear Capital portfolio companies China AI",
        "GGV Capital portfolio companies China AI startups",
        "Qiming Venture Partners portfolio companies China AI",
        "Northern Light Venture Capital portfolio companies China AI",
        "Zhangmen Fund portfolio companies China AI",
        # Accelerators / cross-border
        "MiraclePlus portfolio companies China AI startups English",
        "Innospring accelerator portfolio companies China AI",
        "Microsoft Accelerator Beijing portfolio companies AI",
        "Alibaba Entrepreneurs Fund portfolio companies China AI",
        "Tencent AI Accelerator portfolio companies China AI",
        # Government / national parks
        "Zhongguancun ZGC Science Park startup portfolio companies China AI",
        "Beijing AI Park Artificial Intelligence Industrial Park companies",
        "Shenzhen High-Tech Zone startup portfolio companies China AI",
        "Shanghai Zhangjiang Hi-Tech Park startup companies AI",
        "National High-Tech Incubation Center China startup companies AI",
        # University tech-transfer
        "Tsinghua University x-lab startup incubator portfolio companies AI",
        "Peking University startup incubator portfolio companies AI",
        "Shanghai Jiao Tong SJTU startup incubator companies AI",
        "Fudan University startup incubator portfolio companies AI",
        "Zhejiang University startup incubator portfolio companies AI",
        # Native-language queries — surfaces Chinese-only portfolio pages
        "红杉中国 被投企业 人工智能 创业公司",
        "真格基金 投资组合 人工智能 创业公司",
        "经纬创投 投资组合 人工智能 AI",
        "源码资本 投资组合 人工智能 创业",
        "高榕资本 投资组合 AI 企业",
        "奇绩创坛 孵化企业 人工智能 创业公司",
        "中关村科技园 人工智能企业 创业公司 名录",
        "清华大学 x-lab 创业企业 人工智能",
        "北京大学 创业孵化器 企业名录 AI",
        "浙江大学 创业孵化 人工智能 企业",
    ],

    # ── Singapore ──────────────────────────────────────────────────────────
    # Hub for SE Asia; strong government ecosystem; regional HQ for global VCs
    "SG": [
        "SGInnovate portfolio companies Singapore AI deep tech",
        "NUS Enterprise BLOCK71 portfolio companies Singapore AI",
        "Jungle Ventures portfolio companies Singapore AI",
        "Vertex Ventures SEA portfolio companies Singapore AI",
        "Golden Gate Ventures portfolio companies Singapore AI",
        "Wavemaker Partners portfolio companies Singapore AI",
        "Antler Singapore portfolio companies AI",
        "Entrepreneur First Singapore portfolio companies AI",
        "Monk's Hill Ventures portfolio companies Singapore AI",
        "Enterprise Singapore startup supported companies AI",
        "MAS Fintech Festival startup companies Singapore AI",
        "NTU startup incubator portfolio companies Singapore AI",
        "SMU Institute Innovation portfolio companies Singapore AI",
        "Startup SG accelerator portfolio companies AI 2025",
        "Singapore AI startup ecosystem directory companies 2025",
    ],

    # ── Japan ──────────────────────────────────────────────────────────────
    "JP": [
        "JAFCO portfolio companies Japan AI startups",
        "Global Brain portfolio companies Japan AI",
        "Incubate Fund portfolio companies Japan AI startups",
        "SoftBank Vision Fund Japan portfolio companies AI",
        "Coral Capital portfolio companies Japan AI",
        "500 Startups Japan portfolio companies AI",
        "Plug and Play Japan portfolio companies AI",
        "KDDI Open Innovation program portfolio companies Japan AI",
        "J-Startup government program portfolio companies Japan AI",
        "IPA Japan startup portfolio companies AI technology",
        "University of Tokyo IPC portfolio companies Japan AI",
        "Kyoto University startup incubator portfolio companies AI",
        "Japan Science Technology Agency JST startup portfolio AI",
        "Tokyo AI startup accelerator cohort companies 2025 2026",
        "Japan AI startup ecosystem companies directory 2025",
        # Native-language queries — surfaces Japanese-only portfolio pages
        "ジャフコ ポートフォリオ企業 AI スタートアップ",
        "グローバル・ブレイン 投資先企業 人工知能 スタートアップ",
        "インキュベイトファンド ポートフォリオ AI 企業",
        "Plug and Play Japan 採択企業 人工知能 スタートアップ",
        "J-Startup 選定企業 人工知能 AI",
        "東京大学IPC ポートフォリオ企業 AI スタートアップ",
        "京都大学 スタートアップ インキュベーター 企業 AI",
        "KDDI ∞ Labo 採択企業 スタートアップ AI",
    ],

    # ── India ──────────────────────────────────────────────────────────────
    "IN": [
        "Blume Ventures portfolio companies India AI startups",
        "Peak XV Partners Sequoia India portfolio companies AI",
        "Kalaari Capital portfolio companies India AI",
        "Nexus Venture Partners portfolio companies India AI",
        "Surge portfolio companies India Southeast Asia AI",
        "CIIE IIM Ahmedabad portfolio companies India AI",
        "iCreate India portfolio companies AI startups",
        "T-Hub Hyderabad portfolio companies India AI",
        "Startup India DPIIT scheme companies AI portfolio",
        "NASSCOM DeepTech Club portfolio companies India AI",
        "IIT Bombay SINE incubator portfolio companies AI",
        "IIT Delhi Foundation portfolio companies AI startups",
        "IISc Bangalore startup portfolio companies India AI",
        "AIC Atal Incubation Centre portfolio companies India AI",
        "India AI startup ecosystem directory companies 2025",
    ],

    # ── US ─────────────────────────────────────────────────────────────────
    "US": [
        "Pioneer Fund portfolio companies AI startups",
        "Neo accelerator portfolio companies AI",
        "Z Fellows portfolio companies AI startups",
        "American university startup incubator portfolio companies AI 2026",
        "US deep tech seed fund portfolio companies AI startups",
    ],
}

# Fallback for countries not in the map
_GENERIC_QUERY_TEMPLATES = [
    "top AI accelerator portfolio companies in {country} 2025",
    "startup incubator portfolio companies {country} AI 2025",
    "venture capital portfolio companies AI {country}",
    "government startup program portfolio companies {country} AI",
    "university incubator startup companies {country} AI",
    "{country} AI startup ecosystem directory companies",
]


@dataclass
class ScoutCandidate:
    url: str
    domain: str
    category: str   # university_incubator | accelerator | vc_portfolio | discovery_aggregator | government_program | other
    country: str
    confidence: float
    title: Optional[str] = None


def scout(country: str = "US", limit: int = 20) -> List[ScoutCandidate]:
    """Find new portfolio URLs and register them. Returns the registered set."""
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        logger.warning("TAVILY_API_KEY not set — scout cannot run")
        return []

    country_upper = country.upper()
    queries = _QUERIES_BY_COUNTRY.get(country_upper)
    if not queries:
        logger.info(f"scout: no specific queries for {country_upper}, using generic templates")
        queries = [t.format(country=country) for t in _GENERIC_QUERY_TEMPLATES]

    raw_hits: list[dict] = []
    for q in queries:
        hits = _tavily_search(api_key, q, max_results=10)
        raw_hits.extend(hits)
        logger.debug(f"scout: query '{q[:60]}' → {len(hits)} hits")
        if len(raw_hits) >= limit * 12:
            break

    # Dedup by canonical domain + drop sites already tracked
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
        candidates.append({
            "url": url,
            "domain": domain,
            "title": h.get("title"),
            "snippet": h.get("content", "")[:400],  # Tavily search snippet
        })
        if len(candidates) >= limit * 4:
            break

    logger.info(f"scout: {len(candidates)} unique novel domains pre-validation (country={country_upper})")

    # Validate with LLM (with live page snippet for accuracy) and register keepers
    monitor = HealthMonitor()
    accepted: list[ScoutCandidate] = []
    for c in candidates:
        if len(accepted) >= limit:
            break

        # Fetch a real page snippet to give the LLM actual content signal
        page_text = _fetch_page_snippet(c["url"])

        verdict = _validate_with_llm(
            url=c["url"],
            title=c.get("title"),
            search_snippet=c.get("snippet", ""),
            page_text=page_text,
            country=country_upper,
        )
        if verdict is None or not verdict.get("is_portfolio"):
            continue

        confidence = float(verdict.get("confidence") or 0.6)
        _JS_HEAVY_COUNTRIES = {"CN", "KR", "JP", "TW", "VN", "TH", "ID"}
        min_conf = 0.4 if country_upper in _JS_HEAVY_COUNTRIES else 0.5
        if confidence < min_conf:
            logger.debug(f"scout: low confidence ({confidence:.2f}) for {c['domain']}, skipping")
            continue

        cand = ScoutCandidate(
            url=c["url"],
            domain=c["domain"],
            category=str(verdict.get("category") or "other"),
            country=str(verdict.get("country") or country_upper),
            confidence=confidence,
            title=c.get("title"),
        )
        monitor.register_site(
            domain=cand.domain,
            url=cand.url,
            difficulty="hard",
            scraper_name=f"scout:{country_upper.lower()}",
            category=cand.category,
        )
        accepted.append(cand)
        logger.info(
            f"scout: accepted {cand.domain} "
            f"({cand.category}, conf={cand.confidence:.2f})"
        )

    logger.info(f"scout: registered {len(accepted)} new site(s) for {country_upper}")
    return accepted


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
            logger.warning(f"tavily {resp.status_code}: {resp.text[:200]}")
            return []
        return resp.json().get("results", []) or []
    except Exception as e:
        logger.warning(f"tavily search failed: {e}")
        return []


def _fetch_page_snippet(url: str) -> str:
    """Fetch the page and return visible text (first _PAGE_SNIPPET_CHARS chars).

    Falls back to headless Playwright when requests returns empty content (JS-rendered
    SPAs common on Chinese/Korean VC sites). Returns empty string on total failure.
    """
    text = ""
    try:
        resp = requests.get(
            url,
            timeout=_PAGE_FETCH_TIMEOUT,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "en,en-US;q=0.9",
            },
            allow_redirects=True,
        )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                tag.decompose()
            text = " ".join(soup.get_text(" ", strip=True).split())
    except Exception:
        pass

    if len(text) >= 100:
        return text[:_PAGE_SNIPPET_CHARS]

    # Fallback: Playwright for JS-rendered pages (React/Vue/Angular SPAs)
    try:
        from backend.agentic.engine import _playwright_extract_urls
        results = _playwright_extract_urls([url], max_urls=1)
        if results and results[0].get("raw_content"):
            pw_text = str(results[0]["raw_content"])
            if len(pw_text) > len(text):
                logger.debug(f"scout: playwright fallback got {len(pw_text)} chars for {url}")
                return pw_text[:_PAGE_SNIPPET_CHARS]
    except Exception:
        pass

    return text[:_PAGE_SNIPPET_CHARS]


_VALIDATE_SYSTEM = """\
You judge whether a URL is the OFFICIAL portfolio or companies page of a startup
investor, accelerator, incubator, government program, or university program.

Reply with JSON only:
{
  "is_portfolio": true | false,
  "category": one of "university_incubator" | "accelerator" | "vc_portfolio" |
               "discovery_aggregator" | "government_program" | "other",
  "country": ISO-3166 alpha-2 country code (best guess),
  "confidence": 0.0–1.0
}

Set is_portfolio=true ONLY if ALL hold:
1. The domain is the PRIMARY owner of the portfolio (e.g. ycombinator.com) —
   NOT a third-party listing (crunchbase.com, dealroom.co, tracxn.com,
   cbinsights.com, pitchbook.com, vcbeast.com, privateequitylist.com).
2. The page or its owner clearly lists multiple portfolio / investee companies.
3. The domain is not a large incumbent (Fortune 500, public company) unless it
   is an explicitly dedicated standalone venture / accelerator subdomain.

Set confidence < 0.5 if:
- You cannot tell from the URL + title + text whether it lists companies.
- The page text is empty or generic (JS-rendered, auth-gated).

Set is_portfolio=false for: blog posts, news articles, generic homepages,
third-party aggregators, or any site listing someone else's portfolio.
"""


def _validate_with_llm(
    url: str,
    title: Optional[str],
    search_snippet: str,
    page_text: str,
    country: str,
) -> Optional[dict]:
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

    # Build context — use page text if we got it, otherwise fall back to the
    # Tavily search snippet. Either way the LLM gets real content signal.
    content_block = page_text if page_text else search_snippet
    user = (
        f"URL: {url}\n"
        f"Title: {title or '(none)'}\n"
        f"Country hint: {country}\n"
        f"Page content preview:\n{content_block or '(unavailable)'}\n\n"
        "Return JSON only."
    )
    messages = [
        {"role": "system", "content": _VALIDATE_SYSTEM},
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
