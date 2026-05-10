"""
HuggingFace Organizations scraper.

Why HF is a goldmine for AI startup discovery:
  Every organization on huggingface.co is in the ML/AI domain by definition —
  the platform exclusively hosts model/dataset/space artifacts. Filtering the
  org directory to type="company" gives a near-100% AI hit rate, an order of
  magnitude better than generic VC portfolio scrapes.

Two scrape modes (the API path is the default and recommended):

  mode="api" — uses HuggingFace's public JSON API (rate budget: 500 req per
    5 min, well-documented in response headers).
      1. Paginate /api/models?sort=downloads&limit=1000 via the cursor link
         header. ~10 pages = ~10k top-traction models.
      2. Extract unique author slugs (typically 1k-2k unique).
      3. For each slug, GET /api/organizations/{slug}/overview. 200 means it
         is an org (returns fullname, plan, numModels, numFollowers, ...);
         404 means a user — skipped.
      4. Optionally enrich with the profile HTML page (website + socials).
    This avoids the HTML /organizations directory which gets aggressively
    rate-limited (~1h IP cooldowns).

  mode="listing" — paginated GET on https://huggingface.co/organizations?p=N.
    Each page is server-rendered HTML containing ~50 "overview-card-wrapper"
    <article> blocks. Faster per-org but trips a strict per-IP rate cap after
    ~30-100 pages.

Profile-page enrichment (both modes):
    For the kept orgs we optionally fetch the org's profile page and extract:
      - website (the first <a class="leading-snug ..." rel="nofollow" ...>)
      - github / twitter / linkedin URLs (sidebar social links)
    This is the single signal that distinguishes a real business from a
    placeholder/unverified org account.

AI classification:
  HF orgs are AI by construction, so we mark them is_ai_startup=True with
  confidence 0.9 — saves a downstream LLM call per row.
"""
from __future__ import annotations

import html as html_module
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

import requests

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


# ── Config ────────────────────────────────────────────────────────────────

LISTING_URL = "https://huggingface.co/organizations"
PROFILE_URL_TEMPLATE = "https://huggingface.co/{slug}"
MODELS_API_URL = "https://huggingface.co/api/models"
ORG_OVERVIEW_TEMPLATE = "https://huggingface.co/api/organizations/{slug}/overview"

# Listing pages are public; HF rate-limits aggressively at ~5 req/s, so we
# pace deliberately. Empirically 1.5s between listing pages keeps us under
# the limit, and 4 enrichment workers with 0.5s per-thread spacing sustains
# without 429s.
LISTING_DELAY_S = 1.5
PROFILE_DELAY_S = 0.5
TIMEOUT_S = 20
# Max wait inside a single 429 backoff loop (exponential capped here).
MAX_BACKOFF_S = 60

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}


# ── Regex parsers ─────────────────────────────────────────────────────────

# Each org is wrapped in <article class="overview-card-wrapper ..."> ... </article>.
_ARTICLE_RE = re.compile(
    r'<article[^>]*class="overview-card-wrapper[^"]*"[^>]*>(.*?)</article>',
    re.DOTALL,
)
# Slug from the inner anchor href="/{slug}".
_SLUG_RE = re.compile(r'<a[^>]*href="/([^"/?#]+)"')
# Fullname is the first <h4 ... title="...">{name}</h4>.
_NAME_RE = re.compile(r'<h4[^>]*title="([^"]+)"')
# Org type — capitalized span ("company", "university", ...). The badge is
# rendered as <span class="capitalize">{type}</span>; sometimes preceded by a
# verification flag like "Enterprise".
_TYPE_RE = re.compile(r'<span class="capitalize"[^>]*>([^<]+)</span>')
# "Enterprise" verification flag (rendered separately on the same card).
_ENTERPRISE_RE = re.compile(r"Enterprise", re.IGNORECASE)
# Models count — visible text "{N} models". Followers same: "{N} followers".
_MODELS_RE = re.compile(r"([\d.,]+)\s*(k|m|b)?\s*models?", re.IGNORECASE)
_FOLLOWERS_RE = re.compile(r"([\d.,]+)\s*(k|m|b)?\s*followers?", re.IGNORECASE)

# Website link on org profile page — explicitly the sidebar entry.
_WEBSITE_RE = re.compile(
    r'<a[^>]*class="[^"]*leading-snug[^"]*"[^>]*href="(https?://[^"]+)"',
)
# Anything href="https?://..." outside HF/asset CDNs counts as a candidate
# external link; we filter to socials below.
_EXTERNAL_HREF_RE = re.compile(r'href="(https?://[^"]+)"')


def _suffix_to_int(value: str, suffix: Optional[str]) -> int:
    """Convert "1.29k" → 1290, "82.9k" → 82900, "5.85k" → 5850, "3.6m" → 3600000."""
    try:
        n = float(value.replace(",", ""))
    except ValueError:
        return 0
    mult = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(
        (suffix or "").lower(), 1
    )
    return int(n * mult)


def _parse_card(article_html: str) -> Optional[dict]:
    """Pull (slug, fullname, type, models, followers, enterprise) from one card."""
    slug_m = _SLUG_RE.search(article_html)
    name_m = _NAME_RE.search(article_html)
    if not slug_m or not name_m:
        return None
    slug = slug_m.group(1)
    fullname = html_module.unescape(name_m.group(1)).strip()

    type_m = _TYPE_RE.search(article_html)
    org_type = type_m.group(1).strip().lower() if type_m else "unknown"
    is_enterprise = bool(_ENTERPRISE_RE.search(article_html))

    models = 0
    if (m := _MODELS_RE.search(article_html)):
        models = _suffix_to_int(m.group(1), m.group(2))

    followers = 0
    if (m := _FOLLOWERS_RE.search(article_html)):
        followers = _suffix_to_int(m.group(1), m.group(2))

    return {
        "slug": slug,
        "fullname": fullname,
        "org_type": org_type,
        "is_enterprise": is_enterprise,
        "models": models,
        "followers": followers,
    }


def _parse_profile(html_text: str) -> dict:
    """Extract website + social links from an org's profile page."""
    out = {"website": None, "github": None, "twitter": None, "linkedin": None}

    if (m := _WEBSITE_RE.search(html_text)):
        out["website"] = m.group(1)

    seen = set()
    for href in _EXTERNAL_HREF_RE.findall(html_text):
        if href in seen:
            continue
        seen.add(href)
        low = href.lower()
        if "huggingface.co" in low or "cdn-avatars" in low:
            continue
        if "github.com/" in low and "github" not in out:
            out["github"] = href
        if ("twitter.com/" in low or "x.com/" in low) and out["twitter"] is None:
            out["twitter"] = href
        if "linkedin.com/" in low and out["linkedin"] is None:
            out["linkedin"] = href
        if out["website"] is None and not any(
            s in low for s in (
                "github.com", "twitter.com", "x.com", "linkedin.com",
                "fonts.googleapis", "fonts.gstatic", "cdnjs.cloudflare",
                "discord.gg", "discord.com", "workable.com",
            )
        ):
            out["website"] = href

    return out


# ── Scraper class ─────────────────────────────────────────────────────────


class HuggingFaceScraper(BaseScraper):
    """Discover real-business AI orgs from the HuggingFace organization directory.

    Knobs (set on the instance before calling .run()):
      max_pages         — listing pages to crawl (default 500 ≈ 25k orgs)
      enrich_companies  — fetch profile page for company-typed orgs (default True)
      keep_only_company — restrict output to org_type == "company" (default True)
      min_followers     — drop orgs below this follower count (default 0)
      require_website   — drop orgs whose profile has no external website (default True)
    """

    name = "huggingface"
    domain = "huggingface.co"
    difficulty = "easy"
    source_url = "https://huggingface.co/organizations"

    def __init__(
        self,
        max_pages: int = 500,
        enrich_companies: bool = True,
        keep_only_company: bool = True,
        min_followers: int = 0,
        require_website: bool = True,
        page_offset: int = 0,
        enrich_workers: int = 8,
        mode: str = "api",
        api_model_pages: int = 10,
        api_sort: str = "downloads",
    ):
        self.max_pages = max_pages
        self.enrich_companies = enrich_companies
        self.keep_only_company = keep_only_company
        self.min_followers = min_followers
        self.require_website = require_website
        self.page_offset = page_offset
        self.enrich_workers = max(1, enrich_workers)
        self.mode = mode
        self.api_model_pages = api_model_pages
        self.api_sort = api_sort
        self._session = requests.Session()
        self._session.headers.update(HEADERS)
        # Cheap shared session per thread — created lazily.
        self._tls = threading.local()

    # ── BaseScraper hook ──────────────────────────────────────────────────

    def scrape(self) -> List[ScrapedCompany]:
        if self.mode == "api":
            orgs = self._collect_via_api()
            logger.info(f"[hf] api pass: collected {len(orgs)} orgs")
        else:
            orgs = self._collect_listing()
            logger.info(f"[hf] listing pass: collected {len(orgs)} orgs")
            if self.keep_only_company:
                before = len(orgs)
                orgs = [o for o in orgs if o["org_type"] == "company"]
                logger.info(f"[hf] filtered company-only: {before} -> {len(orgs)}")

        if self.min_followers > 0:
            before = len(orgs)
            orgs = [o for o in orgs if (o.get("followers") or 0) >= self.min_followers]
            logger.info(f"[hf] filtered followers>={self.min_followers}: {before} -> {len(orgs)}")

        if self.enrich_companies:
            orgs = self._enrich_orgs(orgs)

        if self.require_website and self.enrich_companies:
            before = len(orgs)
            orgs = [o for o in orgs if o.get("website")]
            logger.info(f"[hf] filtered website-required: {before} -> {len(orgs)}")

        results: List[ScrapedCompany] = []
        for o in orgs:
            description = self._build_description(o)
            results.append(ScrapedCompany(
                name=o["fullname"] or o["slug"],
                description=description,
                website_url=o.get("website"),
                profile_url=PROFILE_URL_TEMPLATE.format(slug=o["slug"]),
                industry="AI/ML",
                country=None,
                city=None,
                is_ai_startup=True,
                ai_category="ai_ml_general",
                program="Hugging Face",
                source_url=self.source_url,
                confidence=0.9,
            ))
        return results

    # ── API pass (preferred — no HTML rate-limit) ─────────────────────────

    def _collect_via_api(self) -> list[dict]:
        """Discover orgs via /api/models cursor pagination + /api/organizations.

        Step 1: enumerate top models by `api_sort` for `api_model_pages` cursor
                pages. Each page is 1000 models, ~300-500 unique authors.
        Step 2: dedupe to author slugs, filter out obvious user accounts.
        Step 3: per-slug GET /api/organizations/{slug}/overview. 200 = org;
                404 = user (skipped). Returned JSON gives us fullname, plan,
                numModels, numFollowers, numUsers, isVerified.
        """
        author_slugs = self._collect_top_authors()
        logger.info(f"[hf] api authors collected: {len(author_slugs)}")

        orgs: list[dict] = []
        skipped = 0
        completed = 0
        total = len(author_slugs)
        with ThreadPoolExecutor(max_workers=self.enrich_workers) as pool:
            futs = {
                pool.submit(self._lookup_org_overview, slug): slug
                for slug in author_slugs
            }
            for fut in as_completed(futs):
                slug = futs[fut]
                try:
                    overview = fut.result()
                except Exception as e:
                    overview = None
                    logger.debug(f"[hf] api lookup error {slug}: {e}")
                completed += 1
                if overview is None:
                    skipped += 1
                else:
                    orgs.append({
                        "slug": slug,
                        "fullname": overview.get("fullname") or slug,
                        "org_type": "company",  # API has no type — default to company
                        "is_enterprise": overview.get("plan", "").lower() == "enterprise",
                        "models": overview.get("numModels", 0) or 0,
                        "followers": overview.get("numFollowers", 0) or 0,
                        "members": overview.get("numUsers", 0) or 0,
                        "is_verified": overview.get("isVerified", False),
                        "plan": overview.get("plan"),
                    })
                if completed % 200 == 0 or completed == total:
                    logger.info(
                        f"[hf] api overview {completed}/{total} "
                        f"(orgs {len(orgs)}, users skipped {skipped})"
                    )
        return orgs

    def _collect_top_authors(self) -> list[str]:
        """Cursor-paginate /api/models?sort=...&limit=1000 to collect authors."""
        seen: set[str] = set()
        authors: list[str] = []
        url: Optional[str] = (
            f"{MODELS_API_URL}?sort={self.api_sort}&limit=1000"
        )
        for page in range(self.api_model_pages):
            if not url:
                break
            try:
                resp = self._session.get(url, timeout=TIMEOUT_S)
            except Exception as e:
                logger.warning(f"[hf] api models page {page} network error: {e}")
                time.sleep(2)
                continue
            if resp.status_code == 429:
                wait = int(resp.headers.get("retry-after", "10"))
                logger.warning(f"[hf] api models 429, sleeping {wait}s")
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                logger.warning(f"[hf] api models {resp.status_code}: stopping")
                break
            try:
                data = resp.json()
            except Exception:
                logger.warning(f"[hf] api models page {page}: bad JSON")
                break
            new_on_page = 0
            for m in data:
                mid = m.get("id", "")
                if "/" in mid:
                    slug = mid.split("/", 1)[0]
                    if slug not in seen:
                        seen.add(slug)
                        authors.append(slug)
                        new_on_page += 1
            logger.info(
                f"[hf] api models page {page+1}/{self.api_model_pages}: "
                f"{len(data)} models, {new_on_page} new authors "
                f"(total {len(authors)})"
            )
            url = self._next_link(resp.headers.get("link"))
            time.sleep(0.6)
        return authors

    @staticmethod
    def _next_link(link_header: Optional[str]) -> Optional[str]:
        """Parse the rel="next" URL from an RFC 5988 Link header."""
        if not link_header:
            return None
        m = re.search(r"<([^>]+)>;\s*rel=\"next\"", link_header)
        return m.group(1) if m else None

    def _lookup_org_overview(self, slug: str) -> Optional[dict]:
        """Hit /api/organizations/{slug}/overview. 200 = org; 404 = user."""
        url = ORG_OVERVIEW_TEMPLATE.format(slug=slug)
        sess = self._thread_session()
        backoff = 1
        for _ in range(4):
            try:
                resp = sess.get(url, timeout=TIMEOUT_S)
            except Exception as e:
                logger.debug(f"[hf] org overview network err {slug}: {e}")
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_S)
                continue
            if resp.status_code == 404:
                return None
            if resp.status_code in (429, 503):
                wait = int(resp.headers.get("retry-after", str(backoff)))
                time.sleep(min(wait, MAX_BACKOFF_S))
                backoff = min(backoff * 2, MAX_BACKOFF_S)
                continue
            if resp.status_code >= 400:
                return None
            try:
                return resp.json()
            except Exception:
                return None
            finally:
                # Tiny pacing between successful per-thread calls keeps us under
                # the 500-req/5min API budget when many workers run.
                time.sleep(0.1)
        return None

    # ── Listing pass ──────────────────────────────────────────────────────

    def _collect_listing(self) -> list[dict]:
        orgs: list[dict] = []
        seen: set[str] = set()
        empty_pages = 0
        for page in range(self.page_offset, self.page_offset + self.max_pages):
            url = LISTING_URL if page == 0 else f"{LISTING_URL}?p={page}"
            # Listing pages are nice-to-have; if we hit a 429 wall, we'd rather
            # break out and proceed to enrichment with what we already have.
            text = self._get_with_backoff(url, label=f"listing p={page}",
                                           max_attempts=3)
            if text is None:
                empty_pages += 1
                if empty_pages >= 3:
                    logger.warning(
                        f"[hf] 3 consecutive listing failures — stopping at page "
                        f"{page} with {len(orgs)} orgs already collected"
                    )
                    break
                continue

            cards = _ARTICLE_RE.findall(text)
            if not cards:
                empty_pages += 1
                logger.info(f"[hf] page {page}: 0 cards (empty {empty_pages}/3)")
                if empty_pages >= 3:
                    logger.info("[hf] 3 consecutive empty pages — listing exhausted")
                    break
                time.sleep(LISTING_DELAY_S)
                continue
            empty_pages = 0

            new_on_page = 0
            for card in cards:
                rec = _parse_card(card)
                if not rec or rec["slug"] in seen:
                    continue
                seen.add(rec["slug"])
                orgs.append(rec)
                new_on_page += 1

            if page % 25 == 0 or page < 5:
                logger.info(
                    f"[hf] page {page}: {len(cards)} cards, "
                    f"{new_on_page} new (running total {len(orgs)})"
                )
            time.sleep(LISTING_DELAY_S)
        return orgs

    @staticmethod
    def _get_with_backoff(
        url: str, label: str, session: Optional[requests.Session] = None,
        max_attempts: int = 5,
    ) -> Optional[str]:
        """GET with exponential backoff for 429/503. Returns body text or None."""
        sess = session or requests.Session()
        if not session:
            sess.headers.update(HEADERS)
        backoff = 2
        for attempt in range(1, max_attempts + 1):
            try:
                resp = sess.get(url, timeout=TIMEOUT_S)
            except Exception as e:
                logger.debug(f"[hf] {label} network error attempt {attempt}: {e}")
                time.sleep(min(backoff, MAX_BACKOFF_S))
                backoff *= 2
                continue
            if resp.status_code in (429, 503):
                ra = resp.headers.get("retry-after")
                wait = int(ra) if (ra and ra.isdigit()) else min(backoff, MAX_BACKOFF_S)
                logger.warning(
                    f"[hf] {label} {resp.status_code}, sleeping {wait}s "
                    f"(attempt {attempt}/{max_attempts})"
                )
                time.sleep(wait)
                backoff *= 2
                continue
            if resp.status_code >= 400:
                logger.debug(f"[hf] {label} {resp.status_code}: dropping")
                return None
            return resp.text
        logger.warning(f"[hf] {label} exhausted retries")
        return None

    # ── Profile pass ──────────────────────────────────────────────────────

    def _thread_session(self) -> requests.Session:
        """Per-thread Session reuses TLS / TCP connections."""
        sess = getattr(self._tls, "session", None)
        if sess is None:
            sess = requests.Session()
            sess.headers.update(HEADERS)
            self._tls.session = sess
        return sess

    def _fetch_profile(self, slug: str) -> dict:
        url = PROFILE_URL_TEMPLATE.format(slug=slug)
        text = self._get_with_backoff(url, label=f"profile {slug}",
                                       session=self._thread_session())
        if not text:
            return {"_failed": True}
        # Polite per-thread delay — keeps bursts well under HF's per-IP limit
        # even with multiple workers.
        time.sleep(PROFILE_DELAY_S)
        return _parse_profile(text)

    def _enrich_orgs(self, orgs: list[dict]) -> list[dict]:
        total = len(orgs)
        if total == 0:
            return orgs
        logger.info(
            f"[hf] enrichment pass: {total} orgs, {self.enrich_workers} workers"
        )
        completed = 0
        failed = 0
        with ThreadPoolExecutor(max_workers=self.enrich_workers) as pool:
            futures = {pool.submit(self._fetch_profile, o["slug"]): o for o in orgs}
            for fut in as_completed(futures):
                o = futures[fut]
                try:
                    result = fut.result()
                    if result.pop("_failed", False):
                        failed += 1
                    o.update(result)
                except Exception as e:
                    failed += 1
                    logger.debug(f"[hf] enrich error for {o['slug']}: {e}")
                completed += 1
                if completed % 100 == 0 or completed == total:
                    with_site = sum(1 for x in orgs if x.get("website"))
                    logger.info(
                        f"[hf] enrich {completed}/{total} "
                        f"({with_site} with website, {failed} failed)"
                    )
        return orgs

    # ── Description ───────────────────────────────────────────────────────

    @staticmethod
    def _build_description(o: dict) -> str:
        bits = ["Hugging Face organization"]
        if o.get("is_enterprise"):
            bits.append("(Enterprise tier)")
        bits.append(f"— {o['models']} models, {o['followers']:,} followers")
        if o.get("github"):
            bits.append(f"GitHub: {o['github']}")
        if o.get("twitter"):
            bits.append(f"Twitter: {o['twitter']}")
        return " ".join(bits)
