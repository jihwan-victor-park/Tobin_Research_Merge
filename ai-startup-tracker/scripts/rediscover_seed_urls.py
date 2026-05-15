"""Re-discover seed URLs for D_WRONG_URL + I_OFFTOPIC sites.

For each target domain:
  1. Search Tavily for "{domain} portfolio companies cohort startups".
  2. Filter to URLs on the same registered domain.
  3. Ask Haiku to pick the single best portfolio/companies listing URL
     from candidates (title + snippet + URL).
  4. Persist the pick:
       - data/scrape_instructions/<domain>.yaml -> seed_urls[0]
       - site_health.url -> new URL
  5. Print a summary line per domain.

Usage:
  python3 scripts/rediscover_seed_urls.py --dry-run --limit 5
  python3 scripts/rediscover_seed_urls.py --apply --buckets D_WRONG_URL,I_OFFTOPIC
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from backend.db.connection import session_scope  # noqa: E402
from backend.db.models import SiteHealth  # noqa: E402

import anthropic  # noqa: E402

INSTRUCTION_DIR = ROOT / "data" / "scrape_instructions"
TSV_PATH = ROOT / "reports" / "failure_buckets.tsv"
MD_PATH = ROOT / "reports" / "failure_buckets.md"

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
HAIKU_MODEL = "claude-haiku-4-5-20251001"


def _registered_domain(host: str) -> str:
    """Strip 'www.' and any subdomain — eg 'foo.example.co.uk' -> 'example.co.uk'.
    Naive 2-label fallback is fine for our use; perfect PSL parsing is overkill."""
    host = host.lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host


def load_target_domains(buckets: list[str]) -> list[tuple[str, str]]:
    """Return [(domain, bucket_reason)] for the requested buckets."""
    rows: list[tuple[str, str]] = []
    if TSV_PATH.exists():
        for line in TSV_PATH.read_text().splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0] in buckets:
                rows.append((parts[1], parts[2] if len(parts) > 2 else ""))
        return rows
    if not MD_PATH.exists():
        sys.exit("Run scripts/classify_failures.py first to produce the report.")
    m = re.search(r"## Full domain → bucket mapping\s*\n\s*```\n(.*?)```", MD_PATH.read_text(), re.S)
    if not m:
        sys.exit("Could not parse domain→bucket mapping out of report markdown.")
    for line in m.group(1).strip().splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[0] in buckets:
            rows.append((parts[1], ""))
    return rows


def tavily_search(query: str, max_results: int = 8) -> list[dict]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        sys.exit("TAVILY_API_KEY not set")
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
        "include_answer": False,
    }
    try:
        resp = requests.post(TAVILY_SEARCH_URL, json=payload, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  [tavily err] {exc}", flush=True)
        return []
    return resp.json().get("results", []) or []


POSITIVE_PATTERNS = {
    r"/portfolio(?:/|$|\?)": 10,
    r"/companies(?:/|$|\?)": 10,
    r"/our[-_]?(?:companies|portfolio|investments|ventures)(?:/|$|\?)": 10,
    r"/(?:startups|ventures)(?:/|$|\?)": 8,
    r"/(?:cohort|batch|class(?:es)?)(?:/|$|\?)": 8,
    r"/alumni(?:/|$|\?)": 8,
    r"/founders(?:/|$|\?)": 5,
    r"/investments(?:/|$|\?)": 7,
    r"/grantees(?:/|$|\?)": 7,
    r"/teams?(?:/|$|\?)": 4,
    # Title / snippet keywords (matched against title+content)
}

POSITIVE_TEXT_KEYWORDS = re.compile(
    r"\b(portfolio|companies|cohort|batch|alumni|grantees|startups|invest(?:ed|ments)|founders)\b",
    re.IGNORECASE,
)

NEGATIVE_PATTERNS = {
    r"/(?:blog|news|press|events?|stories|insights|podcasts?|videos?)(?:/|$)": -8,
    r"/(?:contact|about|team|careers|jobs)(?:/|$)": -6,
    r"\.pdf$": -10,
    r"/(?:tag|category|author)/": -5,
    r"/\d{4}/\d{2}/": -5,  # date-stamped paths => articles
}


def score_url(url: str, title: str, snippet: str) -> int:
    """Rule-based score for "this is a company-listing page". Higher = better."""
    score = 0
    path = urlparse(url).path or "/"

    for pat, pts in POSITIVE_PATTERNS.items():
        if re.search(pat, path, re.IGNORECASE):
            score += pts
    for pat, pts in NEGATIVE_PATTERNS.items():
        if re.search(pat, path, re.IGNORECASE):
            score += pts

    # Title / snippet keyword bonus (cheap text signal)
    text = f"{title} {snippet}"
    kw_hits = len(POSITIVE_TEXT_KEYWORDS.findall(text))
    score += min(kw_hits, 4)

    # Penalize root or near-root pages (we already tried those and they failed)
    depth = len([p for p in path.split("/") if p])
    if depth == 0:
        score -= 10  # bare root
    elif depth == 1:
        score += 1
    else:
        score += 2

    return score


def pick_best_url_rules(candidates: list[dict]) -> tuple[Optional[str], str]:
    """Rule-based fallback: score each candidate by URL/title/snippet, pick best positive."""
    if not candidates:
        return None, "no_candidates"
    scored = []
    for c in candidates:
        url = c.get("url") or ""
        title = c.get("title") or ""
        snippet = (c.get("content") or "")[:300]
        scored.append((score_url(url, title, snippet), url, title))
    scored.sort(key=lambda x: -x[0])
    best_score, best_url, best_title = scored[0]
    if best_score <= 0:
        return None, f"rules:no_positive (best={best_score})"
    return best_url, f"rules:score={best_score}"


def pick_best_url_llm(domain: str, candidates: list[dict], client: anthropic.Anthropic) -> tuple[Optional[str], str]:
    """Haiku-picked best candidate. Returns (chosen_url, reason) or (None, error_reason)."""
    if not candidates:
        return None, "no_candidates"

    listing = "\n".join(
        f"[{i}] {c.get('url')}\n  title: {(c.get('title') or '')[:120]!r}\n  snippet: {(c.get('content') or '')[:200]!r}"
        for i, c in enumerate(candidates)
    )
    prompt = (
        f"I am scraping {domain} for a list of companies / startups in their portfolio "
        "(if VC), cohort (if accelerator/incubator), or alumni (if university program).\n\n"
        "Below are candidate URLs. Pick the SINGLE one most likely to be a LISTING page "
        "showing many companies by name. Reject blog posts, news articles, individual "
        "company profiles, generic about/contact pages, or homepages.\n\n"
        "Prefer paths containing: portfolio, companies, startups, cohort, batch, alumni, "
        "ventures, founders, our-investments, our-companies, grantees.\n\n"
        f"Candidates:\n{listing}\n\n"
        'Respond ONLY with JSON: {"index": <int or null>, "reason": "<short>"}. '
        "index=null if NO candidate is a real listing page."
    )

    try:
        msg = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as exc:
        return None, f"anthropic_err:{type(exc).__name__}:{str(exc)[:100]}"

    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None, f"no_json:{text[:80]}"
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None, f"bad_json:{text[:80]}"

    idx = data.get("index")
    reason = (data.get("reason") or "")[:120]
    if idx is None or not isinstance(idx, int) or idx < 0 or idx >= len(candidates):
        return None, f"llm_rejected:{reason}"
    return candidates[idx].get("url"), f"llm:{reason}"


def pick_best_url(domain: str, candidates: list[dict], client: Optional[anthropic.Anthropic]) -> tuple[Optional[str], str]:
    """Try LLM first; fall back to rule-based scoring if LLM unavailable / errors."""
    if client is not None:
        chosen, reason = pick_best_url_llm(domain, candidates, client)
        if chosen:
            return chosen, reason
        # Only fall through on transient errors; respect a clean llm_rejected.
        if not reason.startswith(("anthropic_err", "no_json", "bad_json")):
            return chosen, reason
    return pick_best_url_rules(candidates)


def update_yaml(domain: str, new_url: str) -> None:
    INSTRUCTION_DIR.mkdir(parents=True, exist_ok=True)
    path = INSTRUCTION_DIR / f"{domain}.yaml"
    if path.exists():
        data = yaml.safe_load(path.read_text()) or {}
    else:
        data = {"version": 1, "domain": domain}
    seeds = [new_url] + [u for u in (data.get("seed_urls") or []) if u != new_url]
    data["seed_urls"] = seeds[:20]
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def update_db_url(domain: str, new_url: str) -> None:
    with session_scope() as s:
        h = s.query(SiteHealth).filter(SiteHealth.domain == domain).one_or_none()
        if h:
            h.url = new_url
        s.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Persist results (otherwise dry-run)")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N sites (0 = all)")
    parser.add_argument("--buckets", default="D_WRONG_URL,I_OFFTOPIC")
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.4,
        help="Sleep between sites to be polite to Tavily/Anthropic",
    )
    args = parser.parse_args()

    buckets = [b.strip() for b in args.buckets.split(",") if b.strip()]
    targets = load_target_domains(buckets)
    if args.limit:
        targets = targets[: args.limit]
    print(f"Targets: {len(targets)} (buckets={buckets}) — mode={'APPLY' if args.apply else 'DRY-RUN'}")
    print()

    client: Optional[anthropic.Anthropic] = None
    if os.getenv("ANTHROPIC_API_KEY"):
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    stats: dict[str, int] = defaultdict(int)
    for i, (domain, bucket_reason) in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {domain}", flush=True)

        # Search
        query = f'"{domain}" portfolio companies startups cohort'
        results = tavily_search(query, max_results=10)
        same_domain = [
            r for r in results
            if (host := urlparse(r.get("url", "")).hostname) and _registered_domain(host).endswith(_registered_domain(domain))
        ]
        if not same_domain:
            print(f"  -> no same-domain candidates")
            stats["no_candidates"] += 1
            time.sleep(args.sleep)
            continue

        # LLM-first pick with rule-based fallback
        chosen, reason = pick_best_url(domain, same_domain[:8], client)
        if not chosen:
            print(f"  -> rejected ({reason})")
            stats["llm_rejected"] += 1
            time.sleep(args.sleep)
            continue

        print(f"  -> {chosen}  [{reason}]")
        stats["picked"] += 1

        if args.apply:
            update_yaml(domain, chosen)
            update_db_url(domain, chosen)
            stats["applied"] += 1

        time.sleep(args.sleep)

    print()
    print("=== Summary ===")
    for k, v in stats.items():
        print(f"  {k:20s} {v}")


if __name__ == "__main__":
    main()
