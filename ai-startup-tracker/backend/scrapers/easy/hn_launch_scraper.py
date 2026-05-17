"""
Hacker News Launch / Show HN scraper.

Pulls "Show HN" and "Launch HN" posts via the public HN Algolia search API,
each of which is effectively a startup / product announcement. Every Show HN /
Launch HN post is an organic signal that someone shipped *something* — these
are uniquely good candidates for "AI startup launches" because the HN audience
heavily over-indexes on AI/dev tools.

Sources:
  - tags=story,launch_hn  → all (~1.1K, every one a serious launch)
  - tags=story,show_hn    → filtered by points >= MIN_SHOW_POINTS to drop
                            the noise of hobby/weekend projects.

Algolia endpoint is public and unauthenticated, ~10 req/sec is fine.

Notes on title parsing:
  HN title convention is "Show HN: <Name> – <one-liner description>"
  (separator can be en-dash, em-dash, hyphen, or colon). We strip the prefix
  and split on the first separator we find.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import requests

from backend.agentic.schemas import ScrapedCompany
from backend.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

ALGOLIA_BASE = "https://hn.algolia.com/api/v1/search_by_date"
HITS_PER_PAGE = 1000
# Algolia's public API caps `page * hitsPerPage <= 1000`, so we can only pull
# 1000 records per query. To get the full Show HN archive (~17K with our
# points filter) we slice by month and dedup by objectID.
ALGOLIA_PAGE_CAP = 2  # 1 page of 1000 is the hard limit anyway

# Show HN noise filter — only keep posts that the HN community thought were
# worth at least N upvotes. Lower => more candidates, more junk.
MIN_SHOW_POINTS = 30
MIN_LAUNCH_POINTS = 1  # Launch HN: take everything

# Time-window range for sliced Show HN fetches. Show HN as a tag started
# being used heavily around 2013-2014; pre-2014 is mostly empty.
SLICE_START_YEAR = 2013
SLICE_END_YEAR = datetime.now(timezone.utc).year + 1  # exclusive

# Title prefixes we recognise. (Case-insensitive.)
TITLE_PREFIX_RE = re.compile(r"^(?:Show HN|Launch HN)\s*[:\-–—]\s*(.+)$", re.IGNORECASE)
# Common separators between "<Name>" and "<description>" inside a title.
NAME_DESC_SEPARATORS = (" – ", " — ", " - ", ": ", " | ")

# Lightweight AI signal — keyword scan over title+description. We deliberately
# avoid base.detect_ai here because it pings the Anthropic API once per record,
# which (a) makes the scraper 50x slower and (b) racks up cost. The bulk LLM
# classifier (`scripts/reclassify_ai_with_llm.py`) does a more thorough pass
# on the whole DB later.
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


def _parse_title(title: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract (name, description) from a Show HN / Launch HN title."""
    if not title:
        return None, None
    m = TITLE_PREFIX_RE.match(title.strip())
    if not m:
        # Some titles use a comma or no separator after "Show HN".
        m2 = re.match(r"^(?:Show HN|Launch HN)\s*[,]\s*(.+)$", title.strip(), re.IGNORECASE)
        if not m2:
            return None, None
        body = m2.group(1).strip()
    else:
        body = m.group(1).strip()

    for sep in NAME_DESC_SEPARATORS:
        if sep in body:
            name, desc = body.split(sep, 1)
            return name.strip().strip("\"'"), desc.strip()
    # No separator — entire body is the name.
    return body.strip().strip("\"'"), None


class HnLaunchScraper(BaseScraper):
    """Pulls Show HN + Launch HN posts from the HN Algolia API."""

    name = "hn_launch"
    domain = "news.ycombinator.com"
    difficulty = "easy"
    source_url = "https://news.ycombinator.com/show"

    def scrape(self) -> List[ScrapedCompany]:
        # Launch HN: ~1.1K total, fits in a single 1000-row window.
        launch_hits = self._fetch_window("launch_hn", MIN_LAUNCH_POINTS, None, None)
        logger.info(f"[hn_launch] Launch HN: {len(launch_hits)} posts")

        # Show HN: ~17K with our points filter — slice by month to stay
        # under Algolia's 1000-records-per-query cap.
        show_hits = self._fetch_sliced("show_hn", MIN_SHOW_POINTS)
        logger.info(
            f"[hn_launch] Show HN (>= {MIN_SHOW_POINTS} pts): {len(show_hits)} posts"
        )

        seen_ids: set[str] = set()
        results: List[ScrapedCompany] = []
        skipped_no_name = 0
        skipped_no_url = 0

        for post in launch_hits + show_hits:
            oid = str(post.get("objectID") or "")
            if oid in seen_ids:
                continue
            seen_ids.add(oid)

            name, description = _parse_title(post.get("title") or "")
            if not name or len(name) < 2:
                skipped_no_name += 1
                continue

            url = post.get("url")
            if not url:
                # No external URL means the post body itself was the launch
                # (often a "we built X internally, here it is" without a site).
                # Skip — without a URL we have no way to dedup against
                # existing companies.
                skipped_no_url += 1
                continue

            tags = post.get("_tags") or []
            is_launch = "launch_hn" in tags
            program = "Launch HN" if is_launch else "Show HN"

            # Use story_text as fallback description if the title only gave us
            # a name.
            if not description and post.get("story_text"):
                # story_text is HTML — strip tags crudely; we mostly want the
                # first line or two for AI classification.
                story = re.sub(r"<[^>]+>", " ", post["story_text"])
                story = re.sub(r"\s+", " ", story).strip()
                description = story[:500] if story else None

            combined_text = " ".join(filter(None, [name, description]))

            results.append(
                ScrapedCompany(
                    name=name,
                    description=description,
                    website_url=url,
                    profile_url=f"https://news.ycombinator.com/item?id={oid}",
                    industry=None,
                    is_ai_startup=_looks_ai(combined_text),
                    batch=None,
                    program=program,
                    source_url=self.source_url,
                )
            )

        logger.info(
            f"[hn_launch] Parsed {len(results)} candidates "
            f"(skipped {skipped_no_name} no_name, {skipped_no_url} no_url)"
        )
        return results

    def _fetch_window(
        self,
        tag: str,
        min_points: int,
        ts_start: Optional[int],
        ts_end: Optional[int],
    ) -> list[dict]:
        """Fetch one slice (single page) from Algolia.

        ts_start / ts_end are Unix seconds; either can be None.
        Returns up to HITS_PER_PAGE rows. If the window is denser than 1000
        you'll silently drop the tail — callers should slice fine enough that
        no single window exceeds 1000.
        """
        filters = [f"points>={min_points}"]
        if ts_start is not None:
            filters.append(f"created_at_i>={ts_start}")
        if ts_end is not None:
            filters.append(f"created_at_i<{ts_end}")
        numeric = ",".join(filters)

        params = {
            "tags": f"story,{tag}",
            "hitsPerPage": HITS_PER_PAGE,
            "page": 0,
            "numericFilters": numeric,
        }
        try:
            r = requests.get(ALGOLIA_BASE, params=params, timeout=30)
            r.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"[hn_launch] Algolia request failed ({numeric}): {e}")
            return []

        data = r.json()
        return data.get("hits") or []

    def _fetch_sliced(self, tag: str, min_points: int) -> list[dict]:
        """Walk Algolia month-by-month and dedup by objectID.

        Used for Show HN where the total exceeds the per-query 1000 cap.
        """
        all_hits: list[dict] = []
        seen_ids: set[str] = set()
        windows_fetched = 0

        for year in range(SLICE_START_YEAR, SLICE_END_YEAR):
            for month in range(1, 13):
                ts_start = int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp())
                next_year = year + (1 if month == 12 else 0)
                next_month = 1 if month == 12 else month + 1
                ts_end = int(datetime(next_year, next_month, 1, tzinfo=timezone.utc).timestamp())

                hits = self._fetch_window(tag, min_points, ts_start, ts_end)
                windows_fetched += 1

                new_hits = [h for h in hits if str(h.get("objectID")) not in seen_ids]
                seen_ids.update(str(h.get("objectID")) for h in new_hits)
                all_hits.extend(new_hits)

                if len(hits) >= HITS_PER_PAGE:
                    logger.warning(
                        f"[hn_launch] {tag} {year}-{month:02d}: window saturated at "
                        f"{HITS_PER_PAGE} hits — may be dropping tail. "
                        f"Consider lowering MIN_SHOW_POINTS or slicing finer."
                    )
                if windows_fetched % 12 == 0:
                    logger.info(
                        f"[hn_launch] {tag}: {windows_fetched} windows scanned, "
                        f"{len(all_hits)} unique hits so far"
                    )
                time.sleep(0.2)  # ~5 req/sec, well within HN Algolia limits.

        return all_hits
