"""
News discovery pipeline: global startup-media RSS → Claude Haiku extraction.

Regional startup press covers tiny, non-English companies years before they
reach Crunchbase — often the only public record besides a company register.
Each article costs ~$0.002 to process (Haiku), and funding amounts come out
as a bonus (reduces our PitchBook-only funding dependency).

Flow per article:
  RSS entry → fetch page → strip to text → Haiku extracts startups as JSON
  → dedup (domain, then normalized name) → upsert Company (+FundingSignal)
  → record URL in news_articles so reruns skip it (idempotent).

Usage:
    python scripts/discover_from_news.py --max-articles 5 --dry-run   # test
    python scripts/discover_from_news.py                              # full run
    python scripts/discover_from_news.py --feed platum.kr             # one feed
"""
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from sqlalchemy import text as sql_text  # noqa: E402
from backend.db.connection import session_scope, get_engine, init_db  # noqa: E402
from backend.db.models import Company, FundingSignal, VerificationStatus  # noqa: E402
from backend.utils.domain import canonicalize_domain  # noqa: E402
from backend.utils.normalize import normalize_company_name  # noqa: E402
from backend.utils.denylist import BIG_TECH_DENYLIST  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("news_discover")

MODEL = os.getenv("NEWS_LLM_MODEL", "claude-haiku-4-5-20251001")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 TobinResearch/1.0"

# Global coverage on purpose: regional feeds surface companies CB never sees.
FEEDS = [
    ("techcrunch.com",    "https://techcrunch.com/category/startups/feed/"),
    ("eu-startups.com",   "https://www.eu-startups.com/feed/"),
    ("tech.eu",           "https://tech.eu/feed"),
    ("sifted.eu",         "https://sifted.eu/feed"),
    ("arcticstartup.com", "https://arcticstartup.com/feed/"),
    ("platum.kr",         "https://platum.kr/feed"),
    ("venturesquare.net", "https://www.venturesquare.net/feed"),
    ("thebridge.jp",      "https://thebridge.jp/feed"),
    ("e27.co",            "https://e27.co/feed/"),
    ("techinasia.com",    "https://www.techinasia.com/rss"),
    ("inc42.com",         "https://inc42.com/feed/"),
    ("yourstory.com",     "https://yourstory.com/feed"),
    ("contxto.com",       "https://contxto.com/feed/"),
    ("disruptafrica.com", "https://disruptafrica.com/feed/"),
    ("techcabal.com",     "https://techcabal.com/feed/"),
    ("betakit.com",       "https://betakit.com/feed/"),
    ("startupdaily.net",  "https://www.startupdaily.net/feed/"),
    ("siliconrepublic.com", "https://www.siliconrepublic.com/feed"),
]

EXTRACT_PROMPT = """You are extracting startup companies from a news article for an economics research database.

Article (may be in any language):
---
{article}
---

Return a JSON array. One object per STARTUP COMPANY that is a subject of this article (funded, launched, profiled, acquired). Exclude: investors/VC firms, big established companies, accelerators, government bodies.

Each object:
{{"name": str,                    // official company name
  "website": str|null,            // domain like "example.com" ONLY if stated in article
  "country": str|null,            // English country name, e.g. "South Korea"
  "city": str|null,
  "description": str,             // one English sentence: what the company does
  "is_ai": bool,                  // does the company build/heavily use AI?
  "round_type": str|null,         // e.g. "Seed", "Series A", null if no funding news
  "amount_usd": number|null,      // funding amount converted to USD, null if unknown
  "investors": [str]|null}}

Return [] if no startups. JSON only, no commentary."""


def _ensure_state_table():
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(sql_text("""
            CREATE TABLE IF NOT EXISTS news_articles (
                url VARCHAR(1024) PRIMARY KEY,
                feed VARCHAR(128),
                processed_at TIMESTAMP NOT NULL,
                companies_found INTEGER DEFAULT 0
            )
        """))
        conn.commit()


def _processed_urls() -> set:
    engine = get_engine()
    with engine.connect() as conn:
        return {r[0] for r in conn.execute(sql_text("SELECT url FROM news_articles"))}


def _fetch_feed_entries(feed_url: str) -> List[Dict]:
    """Minimal RSS/Atom parse — title, link, published — via feedparser."""
    import feedparser
    parsed = feedparser.parse(feed_url, agent=UA)
    out = []
    for e in parsed.entries:
        link = getattr(e, "link", None)
        if not link:
            continue
        published = None
        for attr in ("published_parsed", "updated_parsed"):
            t = getattr(e, attr, None)
            if t:
                published = datetime(*t[:6])
                break
        out.append({"url": link, "title": getattr(e, "title", ""), "published": published})
    return out


def _fetch_article_text(url: str) -> Optional[str]:
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=30, follow_redirects=True)
        r.raise_for_status()
    except Exception as e:
        logger.debug(f"fetch failed {url}: {e}")
        return None
    soup = BeautifulSoup(r.text, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()
    paras = [p.get_text(" ", strip=True) for p in soup.find_all(["p", "h1", "h2"])]
    text = "\n".join(p for p in paras if len(p) > 40)
    return text[:7000] if len(text) > 300 else None


def _extract_companies(client, article_text: str, title: str) -> List[dict]:
    from json_repair import repair_json
    msg = client.messages.create(
        model=MODEL, max_tokens=1500, temperature=0,
        messages=[{"role": "user",
                   "content": EXTRACT_PROMPT.format(article=f"{title}\n\n{article_text}")}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()
    try:
        data = json.loads(repair_json(raw))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _upsert(db, existing_domains, existing_norm, rec: dict, feed_domain: str,
            article_url: str, published, now, stats):
    name = (rec.get("name") or "").strip()
    if not name or len(name) > 200:
        return
    norm = normalize_company_name(name)
    if not norm or norm.lower() in BIG_TECH_DENYLIST:
        return
    domain = canonicalize_domain(rec.get("website") or "") or None

    existing_id = None
    if domain and domain.lower() in existing_domains:
        existing_id = existing_domains[domain.lower()]
    elif norm.lower() in existing_norm:
        existing_id = existing_norm[norm.lower()]

    if existing_id and existing_id > 0:
        company = db.query(Company).get(existing_id)
        changed = False
        if company:
            if not company.description and rec.get("description"):
                company.description = rec["description"][:1000]
                changed = True
            if not company.country and rec.get("country"):
                company.country = rec["country"]
                changed = True
            if rec.get("is_ai") and not company.ai_mentioned:
                company.ai_mentioned = True
                changed = True
            if changed:
                company.updated_at = now
                stats["enriched"] += 1
        company_id = existing_id
    else:
        company = Company(
            name=name, domain=domain, normalized_name=norm,
            country=rec.get("country"), city=rec.get("city"),
            description=(rec.get("description") or "")[:1000] or None,
            ai_mentioned=bool(rec.get("is_ai")),
            verification_status=VerificationStatus.emerging_github,
            source_domain=feed_domain,
            first_seen_at=now, last_seen_at=now, created_at=now, updated_at=now,
        )
        db.add(company)
        db.flush()
        company_id = company.id
        if domain:
            existing_domains[domain.lower()] = company_id
        existing_norm[norm.lower()] = company_id
        stats["new_companies"] += 1

    if rec.get("amount_usd") or rec.get("round_type"):
        db.add(FundingSignal(
            company_id=company_id, source="news",
            deal_date=published, round_type=rec.get("round_type"),
            deal_size=float(rec["amount_usd"]) if rec.get("amount_usd") else None,
            investors=rec.get("investors") or None,
            raw_metadata={"article": article_url, "feed": feed_domain},
            collected_at=now,
        ))
        stats["funding_signals"] += 1


def main():
    ap = argparse.ArgumentParser(description="Discover startups from global news RSS")
    ap.add_argument("--max-articles", type=int, default=400, help="cost guard per run")
    ap.add_argument("--feed", help="only this feed domain")
    ap.add_argument("--dry-run", action="store_true", help="extract but don't write DB")
    args = ap.parse_args()

    import anthropic
    client = anthropic.Anthropic()

    init_db()
    _ensure_state_table()
    seen = _processed_urls()
    logger.info(f"{len(seen):,} articles already processed")

    feeds = [(d, u) for d, u in FEEDS if not args.feed or args.feed == d]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stats = {"articles": 0, "new_companies": 0, "enriched": 0, "funding_signals": 0}
    engine = get_engine()

    with session_scope() as db:
        existing_domains: Dict[str, int] = {}
        existing_norm: Dict[str, int] = {}
        for c in db.query(Company.id, Company.domain, Company.normalized_name).all():
            if c.domain:
                existing_domains[c.domain.lower()] = c.id
            if c.normalized_name:
                existing_norm[c.normalized_name.lower()] = c.id

        for feed_domain, feed_url in feeds:
            try:
                entries = _fetch_feed_entries(feed_url)
            except Exception as e:
                logger.warning(f"feed failed {feed_domain}: {e}")
                continue
            fresh = [e for e in entries if e["url"] not in seen]
            logger.info(f"{feed_domain}: {len(entries)} entries, {len(fresh)} new")

            for entry in fresh:
                if stats["articles"] >= args.max_articles:
                    break
                text = _fetch_article_text(entry["url"])
                found = 0
                if text:
                    try:
                        recs = _extract_companies(client, text, entry["title"])
                    except Exception as e:
                        logger.warning(f"LLM failed on {entry['url']}: {e}")
                        recs = []
                    for rec in recs:
                        if not args.dry_run:
                            _upsert(db, existing_domains, existing_norm, rec,
                                    feed_domain, entry["url"], entry["published"], now, stats)
                        found += 1
                stats["articles"] += 1
                if not args.dry_run:
                    with engine.connect() as conn:
                        conn.execute(sql_text(
                            "INSERT INTO news_articles (url, feed, processed_at, companies_found) "
                            "VALUES (:u, :f, :t, :n) ON CONFLICT (url) DO NOTHING"),
                            {"u": entry["url"][:1024], "f": feed_domain, "t": now, "n": found})
                        conn.commit()
                if args.dry_run and found:
                    logger.info(f"  [{entry['title'][:60]}] → {found} companies")
                time.sleep(0.3)
            if stats["articles"] >= args.max_articles:
                logger.info("Hit --max-articles cap")
                break

    logger.info(f"Done: {stats}")


if __name__ == "__main__":
    main()
