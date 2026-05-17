"""
There's An AI For That (theresanaiforthat.com) scraper.

TAAFT is one of the largest AI-tool directories on the open web (~25k tools
indexed). Every listing is an AI product by construction, so the AI hit-rate
is effectively 100% — comparable to HuggingFace organizations, but skewed
toward end-user products rather than ML infrastructure.

Why only the homepage:
  Listing pages like /just-released/, /trending/, /featured/, and the sitemap
  are gated behind a Cloudflare managed challenge (JS + cookies). The bare
  homepage (https://theresanaiforthat.com/) is served without challenge and
  contains ~150-200 tool cards — a rotating mix of "just released", "trending
  today", and editor picks. Each run captures one snapshot; over many runs
  the union accumulates broad coverage of the catalog.

  Query params (?page=2, ?sort=new, …) are silently ignored by the cache layer
  — every variant returns the same homepage HTML — so there is no pagination
  to walk.

Tool card structure (a `<li>` per tool):
    <li class="li ..." data-id="285508" data-name="GoAI"
        data-task="Stocks" data-task_id="..." data-url="https://goai.digital/?ref=taaft..."
        data-task_slug="stocks" data-release="v4.0 released 5h ago">
      ...
      <a class="ai_link" href="https://theresanaiforthat.com/ai/goai/">GoAI</a>
      <div class="short_desc">Your Personal AI Investment Analyst — …</div>
      <a class="task_label" href="/task/stocks/">Stocks</a>
    </li>

We pull:
  name        ← data-name
  website_url ← data-url, stripped of TAAFT ref/utm params
  profile_url ← /ai/{slug}/ (slug from `<span class="share_ai" data-slug="...">`,
                falling back to a sanitised name)
  description ← <div class="short_desc">...</div>
  industry    ← data-task (the human-readable task label)

is_ai_startup is set True with no LLM call — every listing on TAAFT is an AI
product by construction.
"""
from __future__ import annotations

import html as html_module
import logging
import re
from typing import List, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

HOMEPAGE_URL = "https://theresanaiforthat.com/"
PROFILE_URL_BASE = "https://theresanaiforthat.com/ai/"
TIMEOUT_S = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
}

# Each tool is a <li ... data-id=... data-name=... data-url=... ...>.
# We anchor on data-id (always present, numeric) so we don't catch other <li>s.
_CARD_RE = re.compile(
    r'<li\b[^>]*\bdata-id="\d+"[^>]*>(?P<body>.*?)</li>',
    re.DOTALL,
)
_ATTR_RES = {
    "name": re.compile(r'\bdata-name="([^"]*)"'),
    "url": re.compile(r'\bdata-url="([^"]*)"'),
    "task": re.compile(r'\bdata-task="([^"]*)"'),
    "task_slug": re.compile(r'\bdata-task_slug="([^"]*)"'),
    "release": re.compile(r'\bdata-release="([^"]*)"'),
}
# The slug for the TAAFT profile URL lives on an inner <span class="share_ai">.
# It can differ from a naive slug(name) (e.g. "leania.ai Chrome Extension"
# → "leania-ai-chrome-extension"), so always prefer the explicit one.
_SLUG_RE = re.compile(r'<span[^>]*class="share_ai"[^>]*data-slug="([^"]+)"')
_DESC_RE = re.compile(r'<div class="short_desc"[^>]*>(.*?)</div>', re.DOTALL)

# Outbound links carry TAAFT tracking params; strip them so dedup against
# other sources lines up.
_STRIP_QUERY_KEYS = {"ref", "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"}


def _clean_text(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    # Decode HTML entities, collapse whitespace.
    s = html_module.unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _strip_tracking(url: str) -> str:
    """Drop TAAFT/UTM tracking params from an outbound URL.

    We keep all non-tracking params (some tools genuinely encode state in the
    query string), so this is a conservative filter."""
    try:
        p = urlparse(url)
    except ValueError:
        return url
    if not p.query:
        return url
    kept = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in _STRIP_QUERY_KEYS]
    new_query = urlencode(kept, doseq=True)
    return urlunparse(p._replace(query=new_query))


def _parse_homepage(html: str) -> List[dict]:
    """Return list of {name, url, description, task, slug, release} dicts."""
    out: List[dict] = []
    seen_names: set[str] = set()

    for m in _CARD_RE.finditer(html):
        block = m.group(0)  # full <li>...</li> including attrs
        body = m.group("body")

        attrs = {}
        for key, pat in _ATTR_RES.items():
            am = pat.search(block)
            if am:
                attrs[key] = html_module.unescape(am.group(1))

        name = (attrs.get("name") or "").strip()
        url = (attrs.get("url") or "").strip()
        if not name or not url:
            continue
        if name in seen_names:
            continue
        seen_names.add(name)

        slug_m = _SLUG_RE.search(body)
        slug = slug_m.group(1) if slug_m else None

        desc_m = _DESC_RE.search(body)
        description = _clean_text(desc_m.group(1)) if desc_m else None

        out.append(
            {
                "name": name,
                "url": _strip_tracking(url),
                "description": description,
                "task": attrs.get("task") or None,
                "slug": slug,
                "release": attrs.get("release") or None,
            }
        )

    return out


class TaaftScraper(BaseScraper):
    """Scrapes the TAAFT homepage for a rotating snapshot of AI tools."""

    name = "taaft"
    domain = "theresanaiforthat.com"
    difficulty = "easy"
    source_url = HOMEPAGE_URL

    def scrape(self) -> List[ScrapedCompany]:
        try:
            r = requests.get(HOMEPAGE_URL, headers=HEADERS, timeout=TIMEOUT_S)
            r.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"[taaft] homepage fetch failed: {e}")
            return []

        cards = _parse_homepage(r.text)
        logger.info(f"[taaft] parsed {len(cards)} tool cards from homepage")

        results: List[ScrapedCompany] = []
        for c in cards:
            profile_url = f"{PROFILE_URL_BASE}{c['slug']}/" if c.get("slug") else None
            results.append(
                ScrapedCompany(
                    name=c["name"],
                    description=c.get("description"),
                    website_url=c["url"],
                    profile_url=profile_url,
                    industry=c.get("task"),
                    is_ai_startup=True,
                    confidence=0.9,
                    program=None,
                    batch=None,
                    source_url=self.source_url,
                )
            )

        return results
