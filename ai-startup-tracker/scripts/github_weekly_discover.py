#!/usr/bin/env python3
"""
GitHub Weekly Discovery Script
===============================
Discover emerging AI startup candidates from GitHub, create time-series
snapshots, classify repos, compute trend scores, and generate reports.

Usage:
    python scripts/github_weekly_discover.py [--since-days 7] [--init-db]
"""
import argparse
import base64
import json
import logging
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.db.connection import session_scope, init_db
from backend.db.models import (
    Company, GithubSignal, GithubRepoSnapshot,
    VerificationStatus, LocationSource,
)
from backend.utils.domain import canonicalize_domain, extract_homepage_domain
from backend.utils.normalize import normalize_company_name
from backend.utils.scoring import (
    compute_ai_score, compute_startup_score,
    compute_startup_likelihood, extract_ai_tags,
)
from backend.utils.classify import classify_repo
from backend.utils.trends import compute_batch_trends
from backend.utils.llm_filter import filter_startups_with_llm

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("github_discover")


# ── Configuration ──────────────────────────────────────────────────────

GITHUB_API = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# AI topics to search for
AI_TOPICS = [
    "ai", "machine-learning", "llm", "rag", "computer-vision",
    "generative-ai", "agents", "deep-learning", "nlp",
    "transformer", "diffusion", "multimodal",
    "artificial-intelligence", "neural-network", "gpt",
    "chatbot", "text-generation", "image-generation",
    "vector-database", "mlops", "language-model",
    "stable-diffusion", "openai", "huggingface",
    "ai-assistant", "prompt-engineering",
]

# AI keywords in name/description
AI_KEYWORDS = [
    "LLM", "RAG", "agent", "inference", "fine-tuning",
    "vision", "diffusion", "speech", "multimodal",
    "embedding", "transformer", "GPT", "chatbot",
    "vector database", "neural", "deep learning",
    "generative AI", "AI platform", "AI API",
    "machine learning", "MLOps", "prompt",
    "text-to-image", "text-to-speech", "AI copilot",
    "retrieval augmented", "autonomous agent",
]

# Exclusion keywords (non-startup repos)
EXCLUDE_KEYWORDS = [
    "awesome", "papers", "course", "tutorial", "homework",
    "notes", "leetcode", "cookbook", "roadmap", "cheatsheet",
    "interview", "study", "learning-path",
]

MAX_RESULTS_PER_QUERY = 500  # fetch more results per query (5 pages of 100)
REQUEST_DELAY = 2.0  # seconds between API calls


# ── GitHub API helpers ─────────────────────────────────────────────────

def github_headers() -> Dict[str, str]:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers


def check_rate_limit(resource: str = "search"):
    """Check remaining rate limit and sleep if needed.
    resource: 'search' for search API, 'core' for REST API.
    """
    try:
        resp = requests.get(f"{GITHUB_API}/rate_limit", headers=github_headers(), timeout=10)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        logger.warning("Could not check rate limit (connection error), sleeping 60s...")
        time.sleep(60)
        return None
    if resp.status_code == 200:
        data = resp.json()
        remaining = data["resources"][resource]["remaining"]
        reset_ts = data["resources"][resource]["reset"]
        if remaining < 10:
            wait = max(reset_ts - time.time(), 1) + 5
            logger.warning(f"{resource} rate limit low ({remaining}). Sleeping {wait:.0f}s...")
            time.sleep(wait)
        return remaining
    return None


def search_repos(query: str, sort: str = "updated", per_page: int = 30) -> List[Dict]:
    """Search GitHub repos. Returns list of repo dicts."""
    all_items = []
    page = 1
    max_pages = MAX_RESULTS_PER_QUERY // per_page

    while page <= max_pages:
        check_rate_limit()
        params = {
            "q": query,
            "sort": sort,
            "order": "desc",
            "per_page": per_page,
            "page": page,
        }
        try:
            resp = requests.get(
                f"{GITHUB_API}/search/repositories",
                headers=github_headers(),
                params=params,
                timeout=30,
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            logger.warning(f"Search connection error, waiting 60s and retrying: {e}")
            time.sleep(60)
            try:
                resp = requests.get(
                    f"{GITHUB_API}/search/repositories",
                    headers=github_headers(),
                    params=params,
                    timeout=30,
                )
            except Exception:
                logger.error(f"Search retry also failed, skipping remaining pages for: {query}")
                break

        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            all_items.extend(items)
            if len(items) < per_page:
                break
            page += 1
            time.sleep(REQUEST_DELAY)
        elif resp.status_code == 403:
            logger.warning("Rate limited. Waiting 60s...")
            time.sleep(60)
        elif resp.status_code == 422:
            logger.warning(f"Invalid query: {query}")
            break
        else:
            logger.error(f"Search failed ({resp.status_code}): {resp.text[:200]}")
            break

    return all_items


def fetch_readme(full_name: str, max_chars: int = 5000) -> Optional[str]:
    """Fetch the README for a repo (first max_chars characters)."""
    resp = requests.get(
        f"{GITHUB_API}/repos/{full_name}/readme",
        headers=github_headers(),
        timeout=15,
    )
    if resp.status_code == 200:
        data = resp.json()
        content = data.get("content", "")
        encoding = data.get("encoding", "")
        if encoding == "base64" and content:
            try:
                decoded = base64.b64decode(content).decode("utf-8", errors="replace")
                return decoded[:max_chars]
            except Exception:
                pass
    return None


def fetch_org_info(login: str) -> Dict[str, Optional[str]]:
    """Fetch organization profile: website URL and location."""
    result = {"blog": None, "location": None}
    resp = requests.get(
        f"{GITHUB_API}/orgs/{login}",
        headers=github_headers(),
        timeout=15,
    )
    if resp.status_code == 200:
        data = resp.json()
        blog = data.get("blog", "") or ""
        if blog and not blog.startswith("http"):
            blog = "https://" + blog
        result["blog"] = blog if blog else None
        result["location"] = data.get("location") or None
    return result


def fetch_user_location(login: str) -> Optional[str]:
    """Fetch location from a user profile."""
    resp = requests.get(
        f"{GITHUB_API}/users/{login}",
        headers=github_headers(),
        timeout=15,
    )
    if resp.status_code == 200:
        data = resp.json()
        return data.get("location") or None
    return None


def parse_location(location_str: Optional[str]) -> Dict[str, Optional[str]]:
    """
    Parse a free-form location string into country and city.
    Handles patterns like:
      'San Francisco, CA'
      'London, United Kingdom'
      'Berlin, Germany'
      'Singapore'
    """
    if not location_str:
        return {"country": None, "city": None}

    location_str = location_str.strip()

    COUNTRY_ALIASES = {
        "usa": "US", "us": "US", "united states": "US", "united states of america": "US",
        "uk": "GB", "united kingdom": "GB", "england": "GB", "scotland": "GB", "wales": "GB",
        "germany": "DE", "deutschland": "DE",
        "france": "FR", "india": "IN", "china": "CN",
        "canada": "CA", "japan": "JP", "south korea": "KR", "korea": "KR",
        "australia": "AU", "brazil": "BR", "israel": "IL",
        "singapore": "SG", "netherlands": "NL", "holland": "NL",
        "sweden": "SE", "switzerland": "CH", "spain": "ES",
        "italy": "IT", "ireland": "IE", "portugal": "PT",
        "poland": "PL", "austria": "AT", "belgium": "BE",
        "norway": "NO", "finland": "FI", "denmark": "DK",
        "czech republic": "CZ", "czechia": "CZ",
        "new zealand": "NZ", "mexico": "MX",
        "indonesia": "ID", "thailand": "TH", "vietnam": "VN",
        "taiwan": "TW", "hong kong": "HK", "uae": "AE",
        "united arab emirates": "AE", "russia": "RU",
        "turkey": "TR", "ukraine": "UA", "romania": "RO",
        "argentina": "AR", "colombia": "CO", "chile": "CL",
        "nigeria": "NG", "south africa": "ZA", "kenya": "KE",
        "egypt": "EG", "pakistan": "PK", "bangladesh": "BD",
        "philippines": "PH", "malaysia": "MY", "estonia": "EE",
    }

    US_STATES = {
        "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
        "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
        "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
        "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
        "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy",
    }

    parts = [p.strip() for p in location_str.split(",")]

    if len(parts) >= 2:
        city = parts[0]
        last_part = parts[-1].strip().lower()

        if last_part in US_STATES or last_part.replace(".", "") in US_STATES:
            return {"country": "US", "city": city}
        if last_part in COUNTRY_ALIASES:
            return {"country": COUNTRY_ALIASES[last_part], "city": city}
        return {"country": last_part.upper() if len(last_part) == 2 else parts[-1].strip(), "city": city}

    single = location_str.lower().strip()
    if single in COUNTRY_ALIASES:
        return {"country": COUNTRY_ALIASES[single], "city": None}

    return {"country": None, "city": location_str.strip()}


# ── Filtering ──────────────────────────────────────────────────────────

def should_exclude(repo: Dict) -> bool:
    """Check if repo should be excluded (tutorial, awesome-list, etc.)."""
    name = (repo.get("name") or "").lower()
    desc = (repo.get("description") or "").lower()
    full = name + " " + desc

    for kw in EXCLUDE_KEYWORDS:
        if kw.lower() in full:
            return True

    if repo.get("fork", False):
        return True

    return False


# ── Main discovery logic ───────────────────────────────────────────────

def discover_repos(since_days: int = 7) -> List[Dict]:
    """Run GitHub search queries and return filtered candidate repos."""
    since_date = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%d")
    all_repos = {}

    # Strategy 1: Topic-based searches (sorted by stars to get quality repos)
    for topic in AI_TOPICS:
        query = f"topic:{topic} pushed:>{since_date}"
        logger.info(f"Searching: {query}")
        results = search_repos(query, sort="stars", per_page=100)
        for r in results:
            rid = r.get("id")
            if rid and rid not in all_repos:
                all_repos[rid] = r

    # Strategy 2: Keyword-based searches (all keywords, not just first 6)
    for kw in AI_KEYWORDS:
        query = f"{kw} in:name,description pushed:>{since_date}"
        logger.info(f"Searching: {query}")
        results = search_repos(query, sort="stars", per_page=100)
        for r in results:
            rid = r.get("id")
            if rid and rid not in all_repos:
                all_repos[rid] = r

    # Strategy 3: Recently created AI repos (catch brand-new startups)
    for topic in ["ai", "llm", "generative-ai", "agents", "rag"]:
        query = f"topic:{topic} created:>{since_date}"
        logger.info(f"Searching new repos: {query}")
        results = search_repos(query, sort="stars", per_page=100)
        for r in results:
            rid = r.get("id")
            if rid and rid not in all_repos:
                all_repos[rid] = r

    # Strategy 4: High-star AI repos updated recently (catch established startups)
    for topic in ["ai", "machine-learning", "llm", "generative-ai", "deep-learning"]:
        for star_threshold in [50, 10]:
            query = f"topic:{topic} stars:>{star_threshold} pushed:>{since_date}"
            logger.info(f"Searching popular: {query}")
            results = search_repos(query, sort="stars", per_page=100)
            for r in results:
                rid = r.get("id")
                if rid and rid not in all_repos:
                    all_repos[rid] = r

    # Strategy 5: Organization-owned AI repos (more likely to be startups)
    for topic in ["ai", "llm", "generative-ai", "machine-learning"]:
        query = f"topic:{topic} user:type:org pushed:>{since_date}"
        logger.info(f"Searching org repos: {query}")
        results = search_repos(query, sort="stars", per_page=100)
        for r in results:
            rid = r.get("id")
            if rid and rid not in all_repos:
                all_repos[rid] = r

    # Strategy 6: AI repos sorted by recently updated (catch active development)
    for topic in ["ai", "llm", "rag", "agents", "generative-ai"]:
        query = f"topic:{topic} pushed:>{since_date}"
        logger.info(f"Searching recently updated: {query}")
        results = search_repos(query, sort="updated", per_page=100)
        for r in results:
            rid = r.get("id")
            if rid and rid not in all_repos:
                all_repos[rid] = r

    logger.info(f"Total unique repos found: {len(all_repos)}")

    candidates = [repo for repo in all_repos.values() if not should_exclude(repo)]
    logger.info(f"After exclusion filter: {len(candidates)} candidates")
    return candidates


def sanitize_text(text: Optional[str]) -> Optional[str]:
    """Remove null bytes from text to prevent Postgres errors."""
    if text is None:
        return None
    return text.replace("\x00", "")


def _safe_request(func, *args, max_retries=3, **kwargs):
    """Wrapper that retries on connection errors with backoff."""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt < max_retries - 1:
                wait = 30 * (2 ** attempt)  # 30s, 60s, 120s
                logger.warning(f"Connection error (attempt {attempt+1}/{max_retries}), waiting {wait}s: {e}")
                time.sleep(wait)
            else:
                logger.error(f"Connection failed after {max_retries} retries: {e}")
                return None
    return None


def process_candidates(candidates: List[Dict]) -> List[Dict]:
    """
    For each candidate repo, extract domain, fetch README, classify,
    score, and prepare structured records.
    """
    processed = []
    readme_fetch_count = 0
    max_readme_fetches = 500
    owner_cache = {}  # cache org/user lookups to avoid duplicate API calls
    total = len(candidates)

    skipped = 0
    for idx, repo in enumerate(candidates):
        if idx % 200 == 0:
            logger.info(f"Processing candidate {idx+1}/{total} ({len(processed)} done, {skipped} skipped)...")

        try:
            full_name = repo.get("full_name", "")
            owner = repo.get("owner", {})
            owner_login = owner.get("login", "")
            owner_type = owner.get("type", "User")

            homepage = sanitize_text(repo.get("homepage") or "")
            topics = [sanitize_text(t) for t in repo.get("topics", [])]
            description = sanitize_text(repo.get("description") or "")

            # Fetch org/user profile for website + location (with caching)
            org_blog = None
            gh_location = None
            if owner_login in owner_cache:
                cached = owner_cache[owner_login]
                org_blog = cached.get("blog")
                gh_location = cached.get("location")
            else:
                if owner_type == "Organization":
                    org_info = _safe_request(fetch_org_info, owner_login)
                    if org_info:
                        org_blog = org_info["blog"]
                        gh_location = org_info["location"]
                        owner_cache[owner_login] = {"blog": org_blog, "location": gh_location}
                    time.sleep(0.5)
                else:
                    gh_location = _safe_request(fetch_user_location, owner_login)
                    owner_cache[owner_login] = {"blog": None, "location": gh_location}
                    time.sleep(0.5)

                # Check core rate limit every 100 repos
                if idx % 100 == 99:
                    check_rate_limit(resource="core")

            parsed_loc = parse_location(gh_location)

            # Fetch README for promising candidates
            readme_snippet = None
            if readme_fetch_count < max_readme_fetches:
                readme_snippet = _safe_request(fetch_readme, full_name)
                readme_fetch_count += 1
                time.sleep(0.5)
            readme_snippet = sanitize_text(readme_snippet)

            # Extract domain
            domain = extract_homepage_domain(homepage, readme_snippet, org_blog)

            # Compute scores
            ai_score = compute_ai_score(
                topics=topics, description=description, readme_snippet=readme_snippet,
            )
            startup_score = compute_startup_score(
                domain=domain, owner_type=owner_type,
                description=description, readme_snippet=readme_snippet,
            )
            ai_tags = extract_ai_tags(
                topics=topics, description=description, readme_snippet=readme_snippet,
            )

            # Classify into subdomain + layer
            subdomain, layer = classify_repo(
                topics=topics, description=description, readme_snippet=readme_snippet,
            )

            # Startup likelihood (snapshot-level score)
            pushed_at_dt = _parse_dt(repo.get("pushed_at"))

            # Ensure UTC-aware datetime arithmetic
            now_utc = datetime.now(timezone.utc)
            if pushed_at_dt is not None and pushed_at_dt.tzinfo is None:
                pushed_at_dt = pushed_at_dt.replace(tzinfo=timezone.utc)

            pushed_recent = (
                pushed_at_dt is not None
                and (now_utc - pushed_at_dt).days <= 14
                )

            startup_lk = compute_startup_likelihood(
                domain=domain,
                owner_type=owner_type,
                has_org_blog=bool(org_blog),
                description=description,
                readme_snippet=readme_snippet,
                pushed_at_recent=pushed_recent,
            )

            # Extract license info from repo
            license_info = repo.get("license") or {}
            license_name = license_info.get("spdx_id") or license_info.get("name") or None

            company_name = owner_login

            processed.append({
                "company_name": company_name,
                "domain": domain,
                "repo_full_name": full_name,
                "repo_url": repo.get("html_url", ""),
                "owner_login": owner_login,
                "owner_type": owner_type,
                "description": description,
                "topics": topics,
                "homepage_url": homepage,
                "created_at": repo.get("created_at"),
                "pushed_at": repo.get("pushed_at"),
                "stars": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0),
                "open_issues": repo.get("open_issues_count", 0),
                "watchers": repo.get("watchers_count", 0),
                "size_kb": repo.get("size", 0),
                "language": repo.get("language"),
                "license": license_name,
                "default_branch": repo.get("default_branch", "main"),
                "readme_snippet": readme_snippet,
                "ai_score": ai_score,
                "startup_score": startup_score,
                "ai_tags": ai_tags,
                "ai_subdomain": subdomain,
                "stack_layer": layer,
                "startup_likelihood": startup_lk,
                "country": parsed_loc["country"],
                "city": parsed_loc["city"],
            })
        except Exception as e:
            skipped += 1
            logger.error(f"Failed to process repo {repo.get('full_name', '?')}: {e}")
            continue

    if skipped:
        logger.warning(f"Skipped {skipped}/{total} repos due to errors")
    return processed


def upsert_to_db(records: List[Dict]) -> Dict[str, int]:
    """
    Upsert processed records into companies + github_signals tables.
    Also creates a GithubRepoSnapshot for each repo (every run).
    Returns counts.
    """
    stats = {
        "new_companies": 0, "updated_companies": 0,
        "new_signals": 0, "snapshots_created": 0,
    }
    all_snapshots: List[GithubRepoSnapshot] = []

    with session_scope() as session:
        now = datetime.now(timezone.utc)


        for rec in records:
            domain = rec["domain"]
            canon_domain = canonicalize_domain(domain) if domain else None
            norm_name = normalize_company_name(rec["company_name"])

            # Find existing company by domain or normalized name
            company = None
            if canon_domain:
                company = session.query(Company).filter(
                    Company.domain == canon_domain
                ).first()

            if not company and norm_name:
                company = session.query(Company).filter(
                    Company.normalized_name == norm_name
                ).first()

            if company:
                company.last_seen_at = now
                company.updated_at = now
                if rec["ai_score"] and (company.ai_score is None or rec["ai_score"] > company.ai_score):
                    company.ai_score = rec["ai_score"]
                if rec["startup_score"] and (company.startup_score is None or rec["startup_score"] > company.startup_score):
                    company.startup_score = rec["startup_score"]
                if rec["ai_tags"]:
                    existing_tags = set(company.ai_tags or [])
                    existing_tags.update(rec["ai_tags"])
                    company.ai_tags = sorted(existing_tags)
                if canon_domain and not company.domain:
                    company.domain = canon_domain
                if rec.get("country") and not company.country:
                    company.country = rec["country"]
                    company.city = rec.get("city")
                    company.location_source = LocationSource.github
                stats["updated_companies"] += 1
            else:
                company = Company(
                    name=rec["company_name"],
                    domain=canon_domain,
                    normalized_name=norm_name,
                    country=rec.get("country"),
                    city=rec.get("city"),
                    location_source=LocationSource.github if rec.get("country") else LocationSource.unknown,
                    verification_status=VerificationStatus.emerging_github,
                    ai_score=rec["ai_score"],
                    startup_score=rec["startup_score"],
                    ai_tags=rec["ai_tags"],
                    first_seen_at=now,
                    last_seen_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(company)
                session.flush()
                stats["new_companies"] += 1

            # Upsert GithubSignal (existing behavior)
            existing_signal = session.query(GithubSignal).filter(
                GithubSignal.repo_full_name == rec["repo_full_name"]
            ).first()

            if existing_signal:
                existing_signal.stars = rec["stars"]
                existing_signal.forks = rec["forks"]
                existing_signal.pushed_at = _parse_dt(rec.get("pushed_at"))
                existing_signal.collected_at = now
            else:
                signal = GithubSignal(
                    company_id=company.id,
                    repo_full_name=rec["repo_full_name"],
                    repo_url=rec["repo_url"],
                    owner_login=rec["owner_login"],
                    owner_type=rec["owner_type"],
                    description=rec["description"],
                    topics=rec["topics"],
                    homepage_url=rec["homepage_url"],
                    created_at=_parse_dt(rec.get("created_at")),
                    pushed_at=_parse_dt(rec.get("pushed_at")),
                    stars=rec["stars"],
                    forks=rec["forks"],
                    readme_snippet=rec.get("readme_snippet"),
                    collected_at=now,
                )
                session.add(signal)
                stats["new_signals"] += 1

            # Always create a snapshot (time-series record)
            snapshot = GithubRepoSnapshot(
                repo_full_name=rec["repo_full_name"],
                collected_at=now,
                stars=rec["stars"],
                forks=rec["forks"],
                open_issues=rec.get("open_issues", 0),
                watchers=rec.get("watchers", 0),
                size_kb=rec.get("size_kb", 0),
                pushed_at=_parse_dt(rec.get("pushed_at")),
                created_at=_parse_dt(rec.get("created_at")),
                language=rec.get("language"),
                license=rec.get("license"),
                owner_login=rec["owner_login"],
                owner_type=rec["owner_type"],
                default_branch=rec.get("default_branch", "main"),
                topics=rec["topics"],
                description=rec["description"],
                homepage_url=rec.get("homepage_url"),
                ai_subdomain=rec.get("ai_subdomain"),
                stack_layer=rec.get("stack_layer"),
                startup_likelihood=rec.get("startup_likelihood"),
                llm_classification=rec.get("llm_classification"),
                llm_confidence=rec.get("llm_confidence"),
                llm_reason=rec.get("llm_reason"),
            )
            session.add(snapshot)
            all_snapshots.append(snapshot)
            stats["snapshots_created"] += 1

        session.flush()

        # Compute velocity deltas and trend scores for all snapshots
        logger.info(f"Computing trend scores for {len(all_snapshots)} snapshots...")
        compute_batch_trends(session, all_snapshots, lookback_days=7)

    return stats


def _update_llm_results_in_db(records: List[Dict]):
    """Update existing snapshots with LLM classification results."""
    with session_scope() as session:
        updated = 0
        for rec in records:
            repo_name = rec.get("repo_full_name")
            llm_class = rec.get("llm_classification")
            if not repo_name or not llm_class:
                continue
            # Update the most recent snapshot for this repo
            snapshot = session.query(GithubRepoSnapshot).filter(
                GithubRepoSnapshot.repo_full_name == repo_name
            ).order_by(GithubRepoSnapshot.collected_at.desc()).first()
            if snapshot:
                snapshot.llm_classification = llm_class
                snapshot.llm_confidence = rec.get("llm_confidence")
                snapshot.llm_reason = rec.get("llm_reason")
                updated += 1
        logger.info(f"Updated {updated} snapshots with LLM classifications")


# ── Geographic aggregation ────────────────────────────────────────────

def compute_geo_trends(records: List[Dict]) -> Dict:
    """
    Compute geographic trend summaries from processed records.
    Returns a dict with country-level breakdowns.
    """
    country_counts: Counter = Counter()
    country_trend_scores: Dict[str, List[float]] = defaultdict(list)
    country_subdomain: Dict[str, Counter] = defaultdict(Counter)

    for rec in records:
        country = rec.get("country")
        if not country:
            continue
        country_counts[country] += 1
        if rec.get("startup_likelihood") is not None:
            country_trend_scores[country].append(rec["startup_likelihood"])
        subdomain = rec.get("ai_subdomain", "Other")
        country_subdomain[country][subdomain] += 1

    # Top countries by count
    top_by_count = country_counts.most_common(20)

    # Top countries by avg startup_likelihood (proxy for quality)
    country_avgs = {}
    for c, scores in country_trend_scores.items():
        country_avgs[c] = sum(scores) / len(scores)
    top_by_avg = sorted(country_avgs.items(), key=lambda x: x[1], reverse=True)[:20]

    # Country x subdomain breakdown
    breakdown = {}
    for c, counter in country_subdomain.items():
        breakdown[c] = dict(counter.most_common(10))

    return {
        "top_countries_by_count": [{"country": c, "count": n} for c, n in top_by_count],
        "top_countries_by_quality": [
            {"country": c, "avg_score": round(s, 3)} for c, s in top_by_avg
        ],
        "country_subdomain_breakdown": breakdown,
    }


# ── JSON report generation ────────────────────────────────────────────

def generate_report(
    records: List[Dict],
    stats: Dict[str, int],
    since_days: int,
) -> str:
    """
    Generate a JSON trend report and save to reports/.
    Returns the file path.
    """
    report_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
    os.makedirs(report_dir, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    report_path = os.path.join(report_dir, f"github_weekly_trends_{today}.json")

    # Sort records by startup_likelihood for top trending
    sorted_by_likelihood = sorted(
        records, key=lambda r: r.get("startup_likelihood", 0), reverse=True,
    )

    # Top 50 trending repos
    top_trending = []
    for rec in sorted_by_likelihood[:50]:
        top_trending.append({
            "repo": rec["repo_full_name"],
            "domain": rec.get("domain"),
            "country": rec.get("country"),
            "stars": rec.get("stars", 0),
            "forks": rec.get("forks", 0),
            "ai_subdomain": rec.get("ai_subdomain"),
            "stack_layer": rec.get("stack_layer"),
            "startup_likelihood": rec.get("startup_likelihood"),
            "ai_score": rec.get("ai_score"),
            "language": rec.get("language"),
            "llm_classification": rec.get("llm_classification"),
            "llm_confidence": rec.get("llm_confidence"),
            "llm_reason": rec.get("llm_reason"),
        })

    # Category summary
    subdomain_counts: Counter = Counter()
    layer_counts: Counter = Counter()
    subdomain_scores: Dict[str, List[float]] = defaultdict(list)
    for rec in records:
        sd = rec.get("ai_subdomain", "Other")
        ly = rec.get("stack_layer", "Other")
        subdomain_counts[sd] += 1
        layer_counts[ly] += 1
        if rec.get("startup_likelihood") is not None:
            subdomain_scores[sd].append(rec["startup_likelihood"])

    category_summary = {
        "by_subdomain": [
            {
                "subdomain": sd,
                "count": subdomain_counts[sd],
                "avg_startup_likelihood": round(
                    sum(subdomain_scores.get(sd, [0])) / max(len(subdomain_scores.get(sd, [1])), 1), 3
                ),
            }
            for sd in sorted(subdomain_counts, key=subdomain_counts.get, reverse=True)
        ],
        "by_layer": [
            {"layer": ly, "count": n}
            for ly, n in layer_counts.most_common()
        ],
    }

    # Geography
    geo = compute_geo_trends(records)

    # Language summary
    lang_counts = Counter(rec.get("language") or "Unknown" for rec in records)

    report = {
        "run_metadata": {
            "since_days": since_days,
            "collected_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),

            "total_repos_processed": len(records),
        },
        "totals": stats,
        "top_trending_repos": top_trending,
        "category_summary": category_summary,
        "geography_summary": geo,
        "language_summary": [
            {"language": lang, "count": n}
            for lang, n in lang_counts.most_common(20)
        ],
    }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info(f"Report saved to {report_path}")
    return report_path


def _parse_dt(val) -> Optional[datetime]:
    """Parse ISO datetime string from GitHub API."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


# ── CLI ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="GitHub Weekly AI Startup Discovery")
    parser.add_argument("--since-days", type=int, default=30, help="Look back N days (default: 30)")
    parser.add_argument("--init-db", action="store_true", help="Create DB tables before running")
    parser.add_argument("--limit", type=int, default=0, help="Max repos to process for testing (0=all)")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM startup filter (use heuristics only)")
    args = parser.parse_args()

    if not GITHUB_TOKEN:
        logger.warning("GITHUB_TOKEN not set. API rate limits will be very restrictive.")

    if args.init_db:
        init_db()

    logger.info(f"Starting GitHub discovery (last {args.since_days} days)...")

    # Step 1: Discover repos
    candidates = discover_repos(since_days=args.since_days)

    if args.limit > 0:
        logger.info(f"Limiting to {args.limit} candidates (from {len(candidates)}) for testing")
        candidates = candidates[:args.limit]

    # Step 2: Process (extract domains, classify, score, fetch READMEs)
    logger.info(f"Processing {len(candidates)} candidates...")
    records = process_candidates(candidates)

    # Step 3: Save to DB FIRST (so we don't lose processing work)
    logger.info(f"Upserting {len(records)} records to database...")
    stats = upsert_to_db(records)
    logger.info(f"DB save complete: {stats['new_companies']} new, {stats['updated_companies']} updated, {stats['snapshots_created']} snapshots")

    # Step 4: LLM startup filter — runs on saved records, updates DB in place
    if not args.no_llm:
        logger.info(f"Running LLM startup filter on {len(records)} records...")
        accepted, rejected = filter_startups_with_llm(records)
        logger.info(f"LLM filter: {len(accepted)} startups, {len(rejected)} non-startups")
        # Update snapshots in DB with LLM results
        _update_llm_results_in_db(accepted + rejected)
    else:
        logger.info("Skipping LLM filter (--no-llm). Run 'python scripts/run_llm_classify.py' later.")

    # Step 5: Generate JSON report
    report_path = generate_report(records, stats, args.since_days)

    # Step 6: Print geographic summary
    geo = compute_geo_trends(records)
    if geo["top_countries_by_count"]:
        logger.info("Top countries by new repos:")
        for item in geo["top_countries_by_count"][:10]:
            logger.info(f"  {item['country']}: {item['count']} repos")

    logger.info("=" * 60)
    logger.info("GitHub Discovery Complete!")
    logger.info(f"  New companies:     {stats['new_companies']}")
    logger.info(f"  Updated companies: {stats['updated_companies']}")
    logger.info(f"  New repo signals:  {stats['new_signals']}")
    logger.info(f"  Snapshots created: {stats['snapshots_created']}")
    logger.info(f"  Report: {report_path}")
    logger.info("=" * 60)

    return stats


if __name__ == "__main__":
    main()
