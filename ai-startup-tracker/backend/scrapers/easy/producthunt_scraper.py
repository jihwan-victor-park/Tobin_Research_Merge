"""
Product Hunt scraper (RSS-feed mode).

Why RSS only:
  - Product Hunt's public site is behind a Cloudflare managed-challenge that
    blocks plain HTTP fetches of /topics/, /products/, and even the sitemap
    (all return 403 with a JS challenge page).
  - The Atom feed at /feed is served *without* a challenge. It returns the
    latest ~50 posts. Pagination params (?per_page, ?days, ?max) are silently
    ignored, so each fetch is a single ~50-item snapshot of today's launches.
  - There is also a "redirect" URL at /r/p/{post_id} that resolves to the
    actual external product website, but it is Cloudflare-gated too. So we
    store the PH profile URL as `website_url` for now — downstream enrichment
    can resolve the real external URL later (e.g. when the agentic engine
    re-visits these).

  This gives us a cheap, high-quality firehose of new launches: every day
  we pick up the most recent ~50 (mostly novel between runs). Over months
  this accumulates into a meaningful AI-product index. A token-based v2
  GraphQL pull would give the full archive — we can add a second mode once
  a PH developer token is provisioned.

Atom entry shape:
    <entry>
      <id>tag:www.producthunt.com,2005:Post/1147419</id>
      <published>2026-05-14T22:16:54-07:00</published>
      <link rel="alternate" type="text/html"
            href="https://www.producthunt.com/products/kimi-ai-assistant"/>
      <title>Kimi WebBridge</title>
      <content type="html">… &lt;p&gt;A bridge connecting AI agents to the live web&lt;/p&gt; …</content>
      <author><name>Zac Zuo</name></author>
    </entry>

We pull:
    name        ← <title>
    description ← stripped <content> (first paragraph)
    profile_url ← <link rel="alternate" href="...">
    website_url ← same as profile_url (PH page; external URL behind CF)
    is_ai_startup ← keyword scan on name+description (PH covers all product
                    categories, not just AI — so we filter heuristically and
                    let the bulk LLM classifier do the deeper pass later).
"""
from __future__ import annotations

import html as html_module
import logging
import re
from typing import List, Optional
from xml.etree import ElementTree as ET

import requests

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

FEED_URL = "https://www.producthunt.com/feed"
TIMEOUT_S = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "application/atom+xml, application/xml;q=0.9",
}

ATOM_NS = "{http://www.w3.org/2005/Atom}"

# AI keyword filter — see hn_launch_scraper for the same rationale (cheap
# regex pass, the bulk LLM classifier does the deeper work later).
_AI_KEYWORDS = re.compile(
    r"\b(?:"
    r"ai|llm|llms|gpt|claude|gemini|mistral|anthropic|openai|huggingface|"
    r"ml|machine[\s-]?learning|neural|deep[\s-]?learning|transformer|"
    r"agent|agents|agentic|rag|embedding|vector|inference|prompt|"
    r"chatbot|copilot|nlp|computer[\s-]?vision|speech[\s-]?to[\s-]?text|"
    r"text[\s-]?to[\s-]?speech|tts|stt|generative|diffusion|stable[\s-]?diffusion"
    r")\b",
    re.IGNORECASE,
)


def _looks_ai(text: str) -> bool:
    if not text:
        return False
    return bool(_AI_KEYWORDS.search(text))


def _strip_html(s: str) -> str:
    """Strip tags and the trailing 'Discussion | Link' boilerplate PH appends."""
    s = html_module.unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # PH content ends with "Discussion | Link" — drop it.
    s = re.sub(r"\s*Discussion\s*\|\s*Link\s*$", "", s)
    return s


def _parse_feed(xml_text: str) -> List[dict]:
    """Return list of {name, description, profile_url, post_id} dicts."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning(f"[ph] feed XML parse error: {e}")
        return []

    out: List[dict] = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        title_el = entry.find(f"{ATOM_NS}title")
        content_el = entry.find(f"{ATOM_NS}content")
        id_el = entry.find(f"{ATOM_NS}id")

        # Prefer <link rel="alternate" type="text/html">; fall back to first link.
        profile_url: Optional[str] = None
        for link in entry.findall(f"{ATOM_NS}link"):
            if link.get("rel") == "alternate" and link.get("type") == "text/html":
                profile_url = link.get("href")
                break
        if not profile_url:
            for link in entry.findall(f"{ATOM_NS}link"):
                profile_url = link.get("href")
                if profile_url:
                    break

        name = (title_el.text or "").strip() if title_el is not None else ""
        description = _strip_html(content_el.text or "") if content_el is not None else ""
        post_id = None
        if id_el is not None and id_el.text:
            # "tag:www.producthunt.com,2005:Post/1147419" → "1147419"
            m = re.search(r"Post/(\d+)", id_el.text)
            if m:
                post_id = m.group(1)

        if not name or not profile_url:
            continue
        out.append(
            {
                "name": name,
                "description": description or None,
                "profile_url": profile_url,
                "post_id": post_id,
            }
        )
    return out


class ProductHuntScraper(BaseScraper):
    """Pull recent posts from the Product Hunt Atom feed."""

    name = "producthunt"
    domain = "producthunt.com"
    difficulty = "easy"
    source_url = FEED_URL

    def __init__(self, ai_only: bool = False):
        """ai_only=True drops non-AI-keyword entries entirely (smaller, cleaner
        result set). Default False — keep everything and let the downstream
        is_ai_startup flag + bulk LLM classifier do the filtering, so we don't
        miss a launch whose AI nature isn't obvious from the title."""
        self.ai_only = ai_only

    def scrape(self) -> List[ScrapedCompany]:
        try:
            r = requests.get(FEED_URL, headers=HEADERS, timeout=TIMEOUT_S)
            r.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"[ph] feed fetch failed: {e}")
            return []

        entries = _parse_feed(r.text)
        logger.info(f"[ph] parsed {len(entries)} feed entries")

        results: List[ScrapedCompany] = []
        ai_count = 0
        for e in entries:
            combined = " ".join(filter(None, [e["name"], e.get("description") or ""]))
            is_ai = _looks_ai(combined)
            if is_ai:
                ai_count += 1
            elif self.ai_only:
                continue

            results.append(
                ScrapedCompany(
                    name=e["name"],
                    description=e.get("description"),
                    # Leave website_url unset — the external URL is behind
                    # Cloudflare's /r/p/{id} redirect, so we only have the PH
                    # profile URL. Storing the PH profile URL as website_url
                    # would collapse all 50 entries onto domain="producthunt.com"
                    # during dedup. Downstream enrichment can resolve the real
                    # external URL later.
                    website_url=None,
                    profile_url=e["profile_url"],
                    industry=None,
                    is_ai_startup=is_ai,
                    confidence=0.7 if is_ai else 0.5,
                    program="Product Hunt",
                    batch=None,
                    source_url=self.source_url,
                )
            )

        logger.info(f"[ph] {len(results)} returned ({ai_count} keyword-AI matches)")
        return results
