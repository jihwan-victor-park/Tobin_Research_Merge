"""Classify the ~460 pending scraper sites into actionable failure buckets.

Combines three signals per domain:
  1. DB state — last ScrapeRun (status, error_message) + SiteHealth (consecutive_failures,
     last_error, pending_reason).
  2. Instruction YAML existence — data/scrape_instructions/<domain>.yaml.
  3. Live HTTP probe — DNS, status, content length, parked-page / off-topic
     keywords. This is what catches LLM-hallucinated entries with bogus URLs.

Output: reports/failure_buckets.md — per-bucket counts, fix recommendation,
and sample domains.
"""
from __future__ import annotations

import concurrent.futures as futures
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from sqlalchemy import desc
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.db.connection import session_scope  # noqa: E402
from backend.db.models import ScrapeRun, SiteHealth  # noqa: E402

INSTRUCTION_DIR = ROOT / "data" / "scrape_instructions"
REPORT_PATH = ROOT / "reports" / "failure_buckets.md"
TSV_PATH = ROOT / "reports" / "failure_buckets.tsv"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Keywords that indicate the page is at least topically about
# startups / VCs / incubators. If NONE appear, the LLM-generated entry
# likely points at an unrelated site.
TOPIC_KEYWORDS = re.compile(
    r"\b(incubator|accelerator|portfolio|startup|venture|cohort|invest|fund|"
    r"founder|company|companies|seed|pre-?seed|series\s+[a-c]|demo\s*day|"
    r"alumni|backed|deal\s*flow|lp|gp|emerging\s+manager|innovation\s+lab|"
    r"entrepreneur|raised|funding|capital)\b",
    re.IGNORECASE,
)

# Parked / placeholder page signals
PARKED_KEYWORDS = re.compile(
    r"(domain\s+for\s+sale|buy\s+this\s+domain|parked\s+domain|godaddy|"
    r"namecheap\s+marketplace|sedo\.com|this\s+domain\s+is\s+for\s+sale|"
    r"hugedomains|under\s+construction|coming\s+soon\s*$)",
    re.IGNORECASE,
)


@dataclass
class ProbeResult:
    reachable: bool = False
    status_code: Optional[int] = None
    final_url: Optional[str] = None
    content_length: int = 0
    has_topic_keywords: bool = False
    is_parked: bool = False
    error: Optional[str] = None


@dataclass
class SiteRow:
    domain: str
    url: Optional[str]
    health_status: str
    consecutive_failures: int
    last_error: Optional[str]
    pending_reason: Optional[str]
    last_run_status: Optional[str] = None
    last_run_error: Optional[str] = None
    last_run_records: int = 0
    total_runs: int = 0
    has_instruction_yaml: bool = False
    probe: ProbeResult = field(default_factory=ProbeResult)
    bucket: str = "Z_UNKNOWN"
    bucket_reason: str = ""


def _make_session() -> requests.Session:
    sess = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.6,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=50, pool_maxsize=50)
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)
    sess.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return sess


def _try_once(sess: requests.Session, target: str, timeout: float) -> ProbeResult:
    try:
        resp = sess.get(target, timeout=timeout, allow_redirects=True)
    except requests.exceptions.ConnectionError as exc:
        msg = str(exc)
        if "Name or service not known" in msg or "nodename" in msg or "getaddrinfo" in msg:
            return ProbeResult(error="dns_fail")
        return ProbeResult(error=f"conn:{type(exc).__name__}")
    except requests.Timeout:
        return ProbeResult(error="timeout")
    except requests.RequestException as exc:
        return ProbeResult(error=f"req_err:{type(exc).__name__}")

    text = resp.text[:50_000] if resp.text else ""
    return ProbeResult(
        reachable=resp.status_code < 400,
        status_code=resp.status_code,
        final_url=resp.url,
        content_length=len(text),
        has_topic_keywords=bool(TOPIC_KEYWORDS.search(text)),
        is_parked=bool(PARKED_KEYWORDS.search(text)),
    )


def probe(domain: str, url: Optional[str], timeout: float = 6.0) -> ProbeResult:
    """Live HTTP probe with retries and fallback URLs.

    Tries (in order):
      1. The stored seed URL (if any).
      2. https://<domain>
      3. https://www.<domain>
    Returns the first reasonable result (200-ish OR a clear DNS NXDOMAIN
    consistent across attempts).
    """
    sess = _make_session()
    candidates: list[str] = []
    if url:
        candidates.append(url if url.startswith(("http://", "https://")) else f"https://{url}")
    candidates.append(f"https://{domain}")
    if not domain.startswith("www."):
        candidates.append(f"https://www.{domain}")

    seen: set[str] = set()
    last: ProbeResult = ProbeResult(error="no_attempt")
    for target in candidates:
        if target in seen:
            continue
        seen.add(target)
        result = _try_once(sess, target, timeout)
        last = result
        # Good outcomes — stop early.
        if result.reachable:
            return result
        # 4xx that aren't 404 (e.g. 403, 429) tell us "alive but blocked" —
        # keep, but try the next candidate in case the seed URL was just stale.
        if result.status_code and result.status_code < 500 and result.status_code != 404:
            # remember and continue trying; if next attempt 200s we prefer it
            continue
    return last


# ── classification rules ──────────────────────────────────────────────


BUCKETS = {
    "H_DEAD_SITE": "Domain unreachable / parked / LLM-hallucinated → drop from inventory",
    "I_OFFTOPIC": "Domain alive but homepage has zero startup/VC/portfolio keywords → likely wrong site, drop or downgrade",
    "C_HTTP_BLOCKED": "HTTP 403 / 429 / blocked by anti-bot → fix with proxy + UA rotation",
    "B_ANTI_BOT_JS": "Tavily/fetch returned thin content, likely JS-only or bot-blocked → Playwright + stealth",
    "E_PARSE_FAIL": "LLM extraction returned invalid JSON / unparseable → tighten prompt or use tool_use mode",
    "F_PAGINATION": "Pagination hints present but agent budget exceeded → bump budget / pagination strategy",
    "D_WRONG_URL": "Page fetched fine but 0 records — seed URL points at wrong page → re-discover with LLM web search",
    "G_STRUCTURE_BROKEN": "Site fetches fine, instructions exist, repeated 0-records → no portfolio page, swap to aggregator",
    "A_NEVER_TRIED": "0 runs and live probe looks fine → just queue it",
    "Z_UNKNOWN": "Did not match any rule — needs manual look",
}


def classify(row: SiteRow) -> tuple[str, str]:
    p = row.probe
    err_blob = " ".join(
        filter(None, [row.last_error or "", row.last_run_error or "", row.pending_reason or ""])
    ).lower()

    # 1) Site itself is dead — highest priority filter
    if p.error == "dns_fail":
        return "H_DEAD_SITE", "DNS lookup failed"
    if p.is_parked:
        return "H_DEAD_SITE", "Parked / for-sale page"
    if p.status_code is not None and p.status_code >= 400 and p.status_code not in (403, 429):
        return "H_DEAD_SITE", f"HTTP {p.status_code} on root"
    if p.error in {"timeout"} and row.total_runs == 0:
        # No run history + can't even probe — treat as dead-ish
        return "H_DEAD_SITE", "Probe timed out, no run history"

    # 2) Probe worked but content is off-topic
    if p.reachable and p.content_length > 500 and not p.has_topic_keywords:
        return "I_OFFTOPIC", "No startup/VC/portfolio keywords on homepage"

    # 3) HTTP block (note: probe may have succeeded, but past runs failed)
    if p.status_code in (403, 429) or any(
        k in err_blob for k in ("403", "429", "forbidden", "rate limit", "blocked", "captcha", "cloudflare")
    ):
        return "C_HTTP_BLOCKED", "HTTP 403/429 or block keyword"

    # 4) Anti-bot / JS-only / thin content
    if any(
        k in err_blob
        for k in ("no content", "empty", "thin", "playwright", "render", "javascript required", "tavily returned")
    ):
        return "B_ANTI_BOT_JS", "Empty / thin content from fetch"

    # 5) LLM parse failure
    if any(k in err_blob for k in ("json", "parse", "decode", "invalid extraction", "validation")):
        return "E_PARSE_FAIL", "LLM output parse / validation failure"

    # 6) Pagination / agent budget
    if any(k in err_blob for k in ("pagination", "budget", "max_calls", "exceeded")):
        return "F_PAGINATION", "Pagination / agent budget"

    # 7) Site fetches fine but extraction yields nothing
    if row.total_runs > 0 and row.last_run_records == 0 and p.reachable:
        if row.has_instruction_yaml and row.consecutive_failures >= 2:
            return "G_STRUCTURE_BROKEN", "Instructions exist, repeated 0-records"
        return "D_WRONG_URL", "Page reachable but 0 records extracted"

    # 8) Never been tried
    if row.total_runs == 0 and p.reachable:
        return "A_NEVER_TRIED", "0 runs, probe OK"

    return "Z_UNKNOWN", f"runs={row.total_runs} probe_ok={p.reachable} err={(err_blob or 'none')[:60]}"


# ── main pipeline ─────────────────────────────────────────────────────


def load_pending_rows() -> list[SiteRow]:
    rows: list[SiteRow] = []
    with session_scope() as s:
        healths = (
            s.query(SiteHealth)
            .filter(SiteHealth.worker_state == "pending")
            .all()
        )
        for h in healths:
            row = SiteRow(
                domain=h.domain,
                url=h.url,
                health_status=h.status,
                consecutive_failures=h.consecutive_failures or 0,
                last_error=h.last_error,
                pending_reason=h.pending_reason,
                total_runs=h.total_runs or 0,
                has_instruction_yaml=(INSTRUCTION_DIR / f"{h.domain}.yaml").exists(),
            )
            last_run = (
                s.query(ScrapeRun)
                .filter(ScrapeRun.domain == h.domain)
                .order_by(desc(ScrapeRun.started_at))
                .first()
            )
            if last_run:
                row.last_run_status = last_run.status
                row.last_run_error = last_run.error_message
                row.last_run_records = last_run.records_found or 0
            rows.append(row)
    return rows


def probe_all(rows: list[SiteRow], workers: int = 10) -> None:
    print(f"[probe] hitting {len(rows)} domains with {workers} workers...", flush=True)
    started = time.time()
    done = 0
    with futures.ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(probe, r.domain, r.url): r for r in rows}
        for fut in futures.as_completed(future_map):
            r = future_map[fut]
            try:
                r.probe = fut.result()
            except Exception as exc:  # last-resort
                r.probe = ProbeResult(error=f"probe_crash:{type(exc).__name__}")
            done += 1
            if done % 50 == 0:
                print(f"  ...{done}/{len(rows)} in {time.time()-started:.1f}s", flush=True)
    print(f"[probe] done in {time.time()-started:.1f}s", flush=True)


def write_report(rows: list[SiteRow]) -> None:
    by_bucket: dict[str, list[SiteRow]] = defaultdict(list)
    for r in rows:
        by_bucket[r.bucket].append(r)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# Pending Scraper Failure Buckets")
    lines.append("")
    lines.append(f"Total pending sites analyzed: **{len(rows)}**")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Bucket | Count | Fix recommendation |")
    lines.append("|---|---:|---|")
    order = [
        "H_DEAD_SITE",
        "I_OFFTOPIC",
        "C_HTTP_BLOCKED",
        "B_ANTI_BOT_JS",
        "E_PARSE_FAIL",
        "F_PAGINATION",
        "D_WRONG_URL",
        "G_STRUCTURE_BROKEN",
        "A_NEVER_TRIED",
        "Z_UNKNOWN",
    ]
    for b in order:
        cnt = len(by_bucket.get(b, []))
        lines.append(f"| **{b}** | {cnt} | {BUCKETS[b]} |")

    lines.append("")
    lines.append("## Samples per bucket (up to 10)")
    for b in order:
        bucket_rows = by_bucket.get(b, [])
        if not bucket_rows:
            continue
        lines.append("")
        lines.append(f"### {b} ({len(bucket_rows)})")
        lines.append("")
        lines.append("| Domain | Runs | Probe | Reason |")
        lines.append("|---|---:|---|---|")
        for r in bucket_rows[:10]:
            probe_str = (
                f"{r.probe.status_code or '-'} "
                f"{'OK' if r.probe.reachable else (r.probe.error or 'fail')}"
            )
            lines.append(f"| {r.domain} | {r.total_runs} | {probe_str} | {r.bucket_reason} |")

    # Full dump for follow-up scripts
    lines.append("")
    lines.append("## Full domain → bucket mapping")
    lines.append("")
    lines.append("```")
    for b in order:
        for r in by_bucket.get(b, []):
            lines.append(f"{b}\t{r.domain}")
    lines.append("```")

    REPORT_PATH.write_text("\n".join(lines))
    print(f"[report] wrote {REPORT_PATH}")

    # Machine-readable companion for apply_buckets.py
    tsv_lines = ["bucket\tdomain\treason"]
    for b in order:
        for r in by_bucket.get(b, []):
            tsv_lines.append(f"{b}\t{r.domain}\t{r.bucket_reason}")
    TSV_PATH.write_text("\n".join(tsv_lines) + "\n")
    print(f"[report] wrote {TSV_PATH}")


def main() -> None:
    rows = load_pending_rows()
    print(f"[db] loaded {len(rows)} pending sites")
    probe_all(rows)
    for r in rows:
        r.bucket, r.bucket_reason = classify(r)
    write_report(rows)

    # Stdout summary
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r.bucket] += 1
    print("\n=== Bucket counts ===")
    for b in sorted(counts, key=lambda x: -counts[x]):
        print(f"  {b:24s} {counts[b]:4d}")


if __name__ == "__main__":
    main()
