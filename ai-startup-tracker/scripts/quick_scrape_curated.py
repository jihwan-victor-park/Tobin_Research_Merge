"""
Cheap one-shot Haiku-based scraper for the curated batch.

Per site (target: 1 LLM call, ~$0.005, 5-10s):
  1. requests.get() the URL with a desktop UA, follow redirects, 25s timeout
  2. BeautifulSoup → strip script/style/nav/footer, take visible text only
  3. Truncate to ~30k chars (Haiku context budget)
  4. ONE Haiku call: "Extract every company on this portfolio page as JSON
     [{name, description, website?, country?}]"
  5. Parse JSON, dedupe, INSERT into companies (skip dupes by domain or name)
  6. Update site_health.worker_state to 'working' if records>0 else leave pending
     and write last_record_count / last_success_at

Bounded scope: only sites with scraper_name LIKE 'curated:%'.

Run:
    python scripts/quick_scrape_curated.py [--limit N] [--workers W]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / f"quick_curated_{datetime.now().strftime('%Y%m%d_%H%M')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("quick_curated")

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

EXTRACT_SYSTEM = (
    "You extract structured data from accelerator/VC/incubator portfolio pages. "
    "Return ONLY a JSON array (no prose, no code fences). Each element: "
    '{"name": str, "description": str|null, "website": str|null, "country": str|null}. '
    "Include EVERY company you can identify on the page (often 10-300+). "
    "If the page is not a portfolio (login wall, blog post, error page) return []."
)


def _fetch(url: str, timeout: int = 25) -> str | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout, allow_redirects=True)
        if r.status_code != 200 or not r.text:
            return None
        return r.text
    except Exception as e:
        logger.warning(f"  fetch failed: {e}")
        return None


def _clean_text(html: str, cap: int = 80000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "head", "footer", "nav"]):
        tag.decompose()
    # Keep links: rewrite to "text (href)" so the LLM sees company URLs.
    for a in soup.find_all("a"):
        href = a.get("href") or ""
        txt = a.get_text(strip=True)
        if href and txt and len(href) < 200:
            a.replace_with(f"{txt} <{href}>")
    text = soup.get_text("\n", strip=True)
    # Collapse runs of blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) > cap:
        text = text[:cap]
    return text


def _extract_with_llm(url: str, body: str) -> list[dict]:
    """Use Together.ai Llama 3.3 70B — far higher rate limits than tier-1 Anthropic.
    Direct call (not via llm_filter._call_together) so we can set max_tokens=12000
    for the long JSON output without touching the GitHub-classifier path."""
    import os
    import requests

    api_key = os.getenv("TOGETHER_API_KEY", "")
    if not api_key:
        raise RuntimeError("TOGETHER_API_KEY not set")

    user = (
        f"Portfolio page: {url}\n\n"
        f"Page text (truncated):\n```\n{body}\n```\n\n"
        "JSON array only:"
    )
    resp = requests.post(
        "https://api.together.xyz/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": os.getenv("LLM_MODEL", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
            "messages": [
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user", "content": user},
            ],
            "temperature": 0.0,
            "max_tokens": 12000,
        },
        timeout=180,
    )
    if resp.status_code == 429:
        # Brief sleep, single retry — Together is generous, this is rare.
        time.sleep(15)
        resp = requests.post(
            "https://api.together.xyz/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": os.getenv("LLM_MODEL", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
                "messages": [
                    {"role": "system", "content": EXTRACT_SYSTEM},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.0,
                "max_tokens": 12000,
            },
            timeout=180,
        )
    if resp.status_code != 200:
        raise RuntimeError(f"together {resp.status_code}: {resp.text[:200]}")
    raw = resp.json()["choices"][0]["message"]["content"].strip()
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip().rstrip("`").strip()
    # Try direct JSON
    try:
        data = json.loads(raw)
    except Exception:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except Exception:
            return []
    if not isinstance(data, list):
        return []
    cleaned = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name or len(name) > 200:
            continue
        cleaned.append({
            "name": name,
            "description": (item.get("description") or None),
            "website": (item.get("website") or None),
            "country": (item.get("country") or None),
        })
    return cleaned


def _insert_records(domain: str, source_url: str, records: list[dict]) -> tuple[int, int]:
    """Returns (inserted_new, total_seen). Dedup by Company.name (case-insensitive) or domain."""
    from backend.db.connection import session_scope
    from backend.db.models import Company
    from backend.utils.classify_ai import _AI_PATTERN, _BARE_AI_PATTERN, _TECH_PATTERN
    from backend.utils.domain import canonicalize_domain

    def _classify_keyword_only(name: str, desc: str | None) -> bool:
        """Skip LLM fallback during bulk insert — keyword-only is fast and
        good enough; we run a proper LLM reclassify pass afterwards."""
        text = " ".join(filter(None, [name, desc])).strip().lower()
        if not text:
            return False
        if _AI_PATTERN.search(text) or _BARE_AI_PATTERN.search(text):
            return True
        return False
    from sqlalchemy import func

    inserted = 0
    seen = 0
    now = datetime.utcnow()

    with session_scope() as session:
        for rec in records:
            seen += 1
            name = rec["name"]
            desc = rec.get("description")
            web = rec.get("website")
            web_domain = canonicalize_domain(web) if web else None

            # Dedup: by domain first (strong), then by normalized name (weak).
            existing = None
            if web_domain:
                existing = session.query(Company).filter(Company.domain == web_domain).first()
            if not existing:
                existing = (
                    session.query(Company)
                    .filter(func.lower(Company.name) == name.lower())
                    .first()
                )

            is_ai = _classify_keyword_only(name, desc)
            ai_score = 0.7 if is_ai else 0.1

            if existing:
                # Light update — don't overwrite richer fields if already set.
                if not existing.description and desc:
                    existing.description = desc
                if not existing.domain and web_domain:
                    existing.domain = web_domain
                if existing.ai_score is None:
                    existing.ai_score = ai_score
                existing.last_seen_at = now
                continue

            session.add(Company(
                name=name,
                description=desc,
                domain=web_domain,
                ai_score=ai_score,
                country=rec.get("country"),
                first_seen_at=now,
                last_seen_at=now,
                created_at=now,
                updated_at=now,
            ))
            inserted += 1

    return inserted, seen


def _update_site_health(domain: str, status: str, records_found: int, error: str | None = None) -> None:
    from backend.db.connection import session_scope
    from backend.db.models import SiteHealth

    now = datetime.now(timezone.utc)
    with session_scope() as session:
        row = session.query(SiteHealth).filter(SiteHealth.domain == domain).first()
        if not row:
            return
        row.last_scraped_at = now
        row.last_record_count = records_found
        if status == "success" and records_found > 0:
            row.worker_state = "working"
            row.status = "healthy"
            row.consecutive_failures = 0
            row.last_success_at = now
            row.last_error = None
        else:
            row.consecutive_failures = (row.consecutive_failures or 0) + 1
            row.last_error = error or f"{status}: 0 records"


def _process_one(domain: str, url: str) -> dict:
    """Returns {'domain', 'status', 'inserted', 'seen', 'err'}."""
    out = {"domain": domain, "status": "fail", "inserted": 0, "seen": 0, "err": None}
    html = _fetch(url)
    if not html:
        out["err"] = "fetch_failed"
        _update_site_health(domain, "fail", 0, error="fetch failed")
        return out
    body = _clean_text(html)
    if len(body) < 200:
        out["err"] = "page_empty"
        _update_site_health(domain, "fail", 0, error="page text too small after cleaning")
        return out
    try:
        records = _extract_with_llm(url, body)
    except Exception as e:
        out["err"] = f"llm:{e}"
        _update_site_health(domain, "fail", 0, error=f"llm: {str(e)[:160]}")
        return out
    if not records:
        out["status"] = "empty"
        _update_site_health(domain, "fail", 0, error="0 records returned")
        return out
    inserted, seen = _insert_records(domain, url, records)
    out["status"] = "ok"
    out["inserted"] = inserted
    out["seen"] = seen
    _update_site_health(domain, "success", seen)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--workers", type=int, default=4,
                   help="Parallel sites (default 4). Anthropic tier-1 allows ~5 RPM/Haiku, "
                        "but tier-2+ is much higher. Drop to 2 if you see 429s.")
    args = p.parse_args()

    from backend.db.connection import session_scope
    from backend.db.models import SiteHealth

    with session_scope() as s:
        rows = (
            s.query(SiteHealth.domain, SiteHealth.url)
            .filter(SiteHealth.scraper_name.like("curated:%"))
            .filter(SiteHealth.url.isnot(None))
            .all()
        )
        targets = [(d, u) for (d, u) in rows]

    if args.limit:
        targets = targets[: args.limit]

    logger.info(f"=== quick haiku scrape: {len(targets)} sites, workers={args.workers} ===")

    t0 = time.time()
    by_status: dict[str, int] = {}
    total_inserted = 0
    total_seen = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_to_site = {pool.submit(_process_one, d, u): (d, u) for d, u in targets}
        for i, fut in enumerate(as_completed(future_to_site), 1):
            d, u = future_to_site[fut]
            try:
                res = fut.result()
            except Exception as e:
                logger.exception(f"[{i}/{len(targets)}] {d} CRASHED: {e}")
                by_status["crash"] = by_status.get("crash", 0) + 1
                continue
            by_status[res["status"]] = by_status.get(res["status"], 0) + 1
            total_inserted += res["inserted"]
            total_seen += res["seen"]
            tag = "OK" if res["status"] == "ok" else res["status"].upper()
            extra = f" inserted={res['inserted']}/{res['seen']}" if res["status"] == "ok" else f" err={res['err']}"
            logger.info(f"[{i}/{len(targets)}] {tag} {d}{extra}")

    dt = time.time() - t0
    logger.info(f"=== done in {dt/60:.1f} min ===")
    for k, v in sorted(by_status.items(), key=lambda x: -x[1]):
        logger.info(f"  {k:8s} {v:4d}")
    logger.info(f"records seen   : {total_seen}")
    logger.info(f"records new    : {total_inserted}")


if __name__ == "__main__":
    main()
