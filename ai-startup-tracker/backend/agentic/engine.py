"""
Agentic web scraper engine (Tavily + Claude).

Two-stage flow:
  FAST PATH: Tavily → Claude extract (1 call) → validate → save
  AGENT FALLBACK: If fast path gets too few results, switch to Claude tool-use agent
                  that autonomously decides which tools to call (fetch, search subpages, etc.)
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests

try:
    import json_repair
except ImportError:
    json_repair = None  # type: ignore

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore

from backend.db.connection import session_scope
from backend.db.models import (
    Company, IncubatorSignal, IncubatorSource, LocationSource, VerificationStatus,
)
from backend.utils.dedup import deduplicate_candidates
from backend.utils.domain import canonicalize_domain
from backend.utils.normalize import normalize_company_name

from .instruction_yaml import (
    build_initial_fetch_urls,
    build_strategy_order,
    domain_for_url,
    instruction_path_for_domain,
    load_instruction,
    merge_plan_with_instruction,
    save_instruction_success,
    should_persist_instruction,
)
from .schemas import AgenticRunReport, PlanResult, RetryAttempt, ScrapedCompany, ValidationResult


TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"
DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# Default strategy order when no instruction exists
DEFAULT_STRATEGIES = ["single_page_extract", "subpage_discovery", "pagination_probe"]

# JSON / UI preview rows (full run still saves all rows to DB)
EXTRACTED_PREVIEW_CAP = 500


# ── Helpers ──────────────────────────────────────────────────────────────

def _anthropic_model() -> str:
    return (os.getenv("ANTHROPIC_MODEL") or DEFAULT_CLAUDE_MODEL).strip()


def _extract_json_block(text: str) -> str:
    """Prefer first balanced JSON object/array."""
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fenced:
        return fenced.group(1).strip()
    return _slice_first_balanced_json(text) or text


def _slice_first_balanced_json(text: str) -> Optional[str]:
    """Return the first top-level `{...}` or `[...]` with string-aware brace matching."""
    i = 0
    while i < len(text) and text[i] not in "{[":
        i += 1
    if i >= len(text):
        return None
    start = i
    stack: List[str] = []
    pairs = {"{": "}", "[": "]"}
    in_string = False
    escape_next = False
    for j in range(i, len(text)):
        ch = text[j]
        if in_string:
            if escape_next:
                escape_next = False
            elif ch == "\\":
                escape_next = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if not stack:
                return None
            op = stack[-1]
            if pairs.get(op) != ch:
                return None
            stack.pop()
            if not stack:
                return text[start : j + 1]
    return None


def _parse_llm_json(raw: str) -> Any:
    """Parse JSON from Claude output: strict first, then json-repair."""
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Empty model response")

    block = _extract_json_block(raw)
    for candidate in (block, raw):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    if json_repair is not None:
        for candidate in (raw, block):
            try:
                return json_repair.loads(candidate)
            except Exception:
                continue

    raise RuntimeError(
        "Could not parse JSON from model output. "
        f"First 500 chars: {raw[:500]!r}"
    )


def _call_claude_json(
    anthropic_api_key: str,
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    max_tokens: int = 4000,
) -> Dict[str, Any]:
    """Call Claude via official SDK; response must be a JSON object."""
    if anthropic is None:
        raise RuntimeError("Install the anthropic package: pip install anthropic")
    model_id = (model or _anthropic_model()).strip()
    client = anthropic.Anthropic(api_key=anthropic_api_key)
    try:
        msg = client.messages.create(
            model=model_id,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except anthropic.APIError as e:
        code = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
        raise RuntimeError(
            f"Anthropic API error ({code}): {e}. "
            f"Model={model_id!r}. Set ANTHROPIC_MODEL to a valid model id, e.g. {DEFAULT_CLAUDE_MODEL!r}."
        ) from e

    raw_parts: List[str] = []
    for block in msg.content:
        if getattr(block, "type", None) == "text":
            raw_parts.append(getattr(block, "text", "") or "")
    raw = "\n".join(raw_parts).strip()
    parsed = _parse_llm_json(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError(
            f"Expected a JSON object from Claude, got {type(parsed).__name__}. "
            f"First 400 chars: {raw[:400]!r}"
        )
    return parsed


# ── Tavily ───────────────────────────────────────────────────────────────

def _tavily_extract(api_key: str, urls: List[str]) -> List[Dict[str, Any]]:
    payload = {
        "api_key": api_key,
        "urls": urls,
        "include_images": False,
        "extract_depth": "advanced",
        "format": "text",
        "timeout": 60,
    }
    resp = requests.post(TAVILY_EXTRACT_URL, json=payload, timeout=120)
    resp.raise_for_status()
    body = resp.json()
    results = body.get("results", [])
    return results if isinstance(results, list) else []


def _playwright_wait_ms() -> int:
    try:
        return max(500, int(os.getenv("AGENTIC_PLAYWRIGHT_WAIT_MS", "4500").strip()))
    except ValueError:
        return 4500


def _playwright_browser_enabled() -> bool:
    if os.getenv("AGENTIC_PLAYWRIGHT", "1").strip().lower() in ("0", "false", "no"):
        return False
    try:
        import importlib.util

        return importlib.util.find_spec("playwright") is not None
    except Exception:
        return False


def _playwright_extract_urls(urls: List[str], *, max_urls: int = 3) -> List[Dict[str, Any]]:
    """Headless Chromium; same shape as Tavily ``{url, raw_content}`` for SPAs / lazy lists."""
    if not _playwright_browser_enabled():
        return []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    urls = [u.strip() for u in urls if (u or "").strip()][:max_urls]
    if not urls:
        return []

    wait_ms = _playwright_wait_ms()
    out: List[Dict[str, Any]] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 2000},
                )
                page = ctx.new_page()
                for url in urls:
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=90000)
                        page.wait_for_timeout(wait_ms)
                        text = page.inner_text("body")
                        out.append({"url": url, "raw_content": text or ""})
                    except Exception as e:
                        out.append({"url": url, "raw_content": f"[playwright error on {url}: {e}]"})
                ctx.close()
            finally:
                browser.close()
    except Exception as e:
        return [{"url": urls[0], "raw_content": f"[playwright launch failed: {e}]"}]
    return out


def _chunks_text_total(chunks: List[Dict[str, Any]]) -> int:
    return sum(len((c.get("raw_content") or "").strip()) for c in chunks)


def _maybe_enrich_chunks_playwright(
    chunks: List[Dict[str, Any]],
    candidate_urls: List[str],
    thin_threshold: int = 900,
) -> List[Dict[str, Any]]:
    """If Tavily returned almost nothing, retry top URLs with a real browser."""
    if not chunks or _chunks_text_total(chunks) >= thin_threshold:
        return chunks
    if not _playwright_browser_enabled():
        return chunks
    pw = _playwright_extract_urls(candidate_urls[:3], max_urls=3)
    if pw and _chunks_text_total(pw) > _chunks_text_total(chunks):
        return pw
    return chunks


# ── Extract records (THE ONLY LLM CALL) ─────────────────────────────────

def _extract_records(
    api_key: str,
    input_url: str,
    extracted_chunks: List[Dict[str, Any]],
) -> List[ScrapedCompany]:
    """Single Claude call: extract company records with location + AI classification."""
    text_bundle = []
    for chunk in extracted_chunks:
        url = chunk.get("url", "")
        content = (chunk.get("raw_content") or "")[:12000]
        text_bundle.append(f"URL: {url}\nCONTENT:\n{content}")
    combined = "\n\n---\n\n".join(text_bundle)

    prompt = f"""Extract startup/company records from the content below.

Output strict JSON object:
{{
  "records": [
    {{
      "name": "company name",
      "description": "one-line description",
      "website_url": "https://...",
      "profile_url": "link to their profile on the source site",
      "industry": "e.g. FinTech, HealthTech, SaaS, etc.",
      "country": "country name or null",
      "city": "city name or null",
      "is_ai_startup": true or false,
      "ai_category": "one of: Agents, RAG, Model/Training, Inference, Vision, Audio, Data, DevTools, Other, or null",
      "program": "program or cohort name, or null",
      "batch": "batch name like 'W26', 'Fall 2025', or null",
      "confidence": 0.0 to 1.0
    }}
  ]
}}

Rules:
- Extract ALL companies/startups listed on the page. Do not skip any.
- For location: infer country and city from the text. If the page is for an incubator in a known city, use that city for companies without explicit location.
- For is_ai_startup: true if the company works on AI, ML, LLM, deep learning, computer vision, NLP, data science, or similar. false otherwise.
- For ai_category: classify only if is_ai_startup is true. Use null otherwise.
- Do not invent data. If a field is not available, use null.
- Prefer URLs found in the text over guessing.

Input URL: {input_url}

Content:
{combined}"""

    parsed = _call_claude_json(
        anthropic_api_key=api_key,
        system_prompt="You are a precise information extractor. Return JSON only. No explanation.",
        user_prompt=prompt,
        max_tokens=4000,
    )
    raw_records = parsed.get("records", [])
    out: List[ScrapedCompany] = []
    for item in raw_records:
        try:
            out.append(ScrapedCompany(**item))
        except Exception:
            continue
    return out


# ── Rule-based validation (NO LLM) ──────────────────────────────────────

def _validate_records(
    records: List[ScrapedCompany],
    min_records: int = 1,
) -> ValidationResult:
    """Simple rule-based validation — no Claude call."""
    if not records:
        return ValidationResult(
            is_good=False,
            reason="No records extracted",
            completeness_score=0.0,
            valid_name_ratio=0.0,
            duplicate_ratio=0.0,
            record_count=0,
        )

    valid_name_count = 0
    normalized_names: List[str] = []
    for r in records:
        norm = normalize_company_name(r.name or "")
        if norm:
            valid_name_count += 1
            normalized_names.append(norm)
    valid_ratio = valid_name_count / max(len(records), 1)

    duplicate_ratio = 0.0
    if normalized_names:
        c = Counter(normalized_names)
        dup_count = sum(v - 1 for v in c.values() if v > 1)
        duplicate_ratio = dup_count / max(len(normalized_names), 1)

    # Score: enough records + valid names + low duplicates
    score = 0.0
    if len(records) >= min_records:
        score += 0.4
    score += min(valid_ratio, 1.0) * 0.4
    score += (1.0 - min(duplicate_ratio, 1.0)) * 0.2

    is_good = len(records) >= min_records and valid_ratio >= 0.5 and duplicate_ratio < 0.5

    return ValidationResult(
        is_good=is_good,
        reason=f"{len(records)} records, {valid_ratio:.0%} valid names, {duplicate_ratio:.0%} duplicates",
        completeness_score=round(score, 3),
        valid_name_ratio=round(valid_ratio, 3),
        duplicate_ratio=round(duplicate_ratio, 3),
        record_count=len(records),
    )


# ── Strategy selection (NO LLM) ─────────────────────────────────────────

def _pick_strategies(instr: Optional[Dict[str, Any]], max_retries: int) -> List[str]:
    """Pick strategy order: use instruction if available, else defaults."""
    if instr:
        # Build a PlanResult-like object for build_strategy_order
        preferred = instr.get("preferred_strategy", "single_page_extract")
        plan_like = PlanResult(
            strategy=preferred,
            subpage_hints=instr.get("subpage_hints", []),
            pagination_hints=instr.get("pagination_hints", []),
            quality_expectation_min_records=instr.get("quality_expectation_min_records", 5),
        )
        return build_strategy_order(plan_like, instr, max_retries)
    return DEFAULT_STRATEGIES[: max_retries + 1]


def _derive_retry_urls(input_url: str, strategy: str, instr: Optional[Dict[str, Any]]) -> List[str]:
    """Build URLs to fetch for a given strategy."""
    base = input_url.rstrip("/")
    urls = [input_url]

    if strategy == "single_page_extract":
        return urls

    if strategy == "subpage_discovery":
        hints = (instr or {}).get("subpage_hints", ["/portfolio", "/companies", "/startups"])
        for h in hints[:4]:
            if h.startswith("http"):
                urls.append(h)
            else:
                urls.append(urljoin(base + "/", h.lstrip("/")))

    elif strategy == "pagination_probe":
        for suffix in ["?page=1", "?page=2", "?p=1", "?p=2"]:
            urls.append(base + suffix)

    return list(dict.fromkeys(urls))


# ── Postprocess ──────────────────────────────────────────────────────────

def _postprocess_records(records: List[ScrapedCompany]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for r in records:
        domain = canonicalize_domain(r.website_url or r.profile_url or "")
        candidates.append(
            {
                "name": (r.name or "").strip(),
                "normalized_name": normalize_company_name(r.name or ""),
                "domain": domain,
                "description": r.description,
                "website_url": r.website_url,
                "profile_url": r.profile_url or r.source_url,
                "industry": r.industry,
                "country": r.country,
                "city": r.city,
                "is_ai_startup": r.is_ai_startup,
                "ai_category": r.ai_category,
                "program": r.program,
                "batch": r.batch,
                "confidence": r.confidence,
            }
        )
    # Dedup
    dedup_input = [{"name": c["name"], "domain": c["domain"]} for c in candidates]
    deduped_keys = deduplicate_candidates(dedup_input)
    key_set = {
        (normalize_company_name(d.get("name", "")), canonicalize_domain(d.get("domain", "")))
        for d in deduped_keys
    }
    output = []
    for c in candidates:
        key = (c["normalized_name"], c["domain"])
        if key in key_set:
            output.append(c)
            key_set.remove(key)
    return output


def _cleaned_to_scraped(cleaned: List[Dict[str, Any]]) -> List[ScrapedCompany]:
    """Rebuild ScrapedCompany rows so validation/YAML counts match post-dedup output."""
    out: List[ScrapedCompany] = []
    for r in cleaned:
        name = (r.get("name") or "").strip()
        try:
            cf = r.get("confidence")
            conf = float(cf) if cf is not None else 0.7
        except (TypeError, ValueError):
            conf = 0.7
        try:
            out.append(
                ScrapedCompany(
                    name=name,
                    description=r.get("description"),
                    website_url=r.get("website_url"),
                    profile_url=r.get("profile_url"),
                    industry=r.get("industry"),
                    country=r.get("country"),
                    city=r.get("city"),
                    is_ai_startup=r.get("is_ai_startup"),
                    ai_category=r.get("ai_category"),
                    program=r.get("program"),
                    batch=r.get("batch"),
                    confidence=conf,
                )
            )
        except Exception:
            continue
    return out


# ── LLM Enrichment (fill missing fields) ────────────────────────────────

_ENRICH_FIELDS = ("country", "city", "industry", "is_ai_startup", "ai_category")
_ENRICH_BATCH_SIZE = 50


def _needs_enrichment(rec: Dict[str, Any]) -> bool:
    """True if any key field is missing."""
    return (
        not rec.get("country")
        or not rec.get("industry")
        or rec.get("is_ai_startup") is None
    )


def _enrich_records(
    api_key: str,
    records: List[Dict[str, Any]],
    progress_callback: Optional[Callable[[str], None]] = None,
) -> List[Dict[str, Any]]:
    """Ask Claude to fill in missing country, city, industry, is_ai_startup, ai_category.

    Only sends companies that actually have gaps. Batches up to 50 per call.
    """
    to_enrich = [(i, r) for i, r in enumerate(records) if _needs_enrichment(r)]
    if not to_enrich:
        return records

    _notify(progress_callback, f"Enriching {len(to_enrich)} companies with missing fields…")

    for batch_start in range(0, len(to_enrich), _ENRICH_BATCH_SIZE):
        batch = to_enrich[batch_start : batch_start + _ENRICH_BATCH_SIZE]
        companies_for_prompt = []
        for _, rec in batch:
            companies_for_prompt.append({
                "name": rec.get("name", ""),
                "description": rec.get("description", ""),
                "website_url": rec.get("website_url", ""),
                "industry": rec.get("industry"),
                "country": rec.get("country"),
                "city": rec.get("city"),
                "is_ai_startup": rec.get("is_ai_startup"),
                "ai_category": rec.get("ai_category"),
            })

        prompt = f"""Fill in missing fields for these companies based on your knowledge.
Only fill fields that are null/empty. Do NOT change fields that already have values.

For each company return:
- country: country name (e.g. "USA", "UK", "Germany")
- city: city name if you know it, otherwise null
- industry: sector (e.g. "FinTech", "HealthTech", "SaaS", "DevTools", "E-commerce")
- is_ai_startup: true if the company works on AI/ML/LLM/deep learning, false otherwise
- ai_category: if is_ai_startup is true, one of: Agents, RAG, Model/Training, Inference, Vision, Audio, Data, DevTools, Other. null if not AI.

Output strict JSON: {{"results": [{{same fields as input, with nulls filled}}]}}
Keep the same order as input.

Companies:
{json.dumps(companies_for_prompt, default=str)}"""

        try:
            parsed = _call_claude_json(
                anthropic_api_key=api_key,
                system_prompt="You are a startup knowledge expert. Fill in missing company information based on your knowledge. Return JSON only.",
                user_prompt=prompt,
                max_tokens=4000,
            )
            enriched_list = parsed.get("results", [])
            for j, (idx, _rec) in enumerate(batch):
                if j >= len(enriched_list):
                    break
                enriched = enriched_list[j]
                for field in _ENRICH_FIELDS:
                    if not records[idx].get(field) and enriched.get(field) is not None:
                        records[idx][field] = enriched[field]
        except Exception as e:
            _notify(progress_callback, f"Enrichment batch failed: {e}")

    filled = sum(1 for i, _ in to_enrich if not _needs_enrichment(records[i]))
    _notify(progress_callback, f"Enriched {filled}/{len(to_enrich)} companies.")
    return records


# ── Save to DB ───────────────────────────────────────────────────────────

def _save_to_db(records: List[Dict[str, Any]], source_url: str = "") -> Tuple[int, int]:
    """Save to Company table + IncubatorSignal if applicable."""
    new_count = 0
    updated_count = 0
    now = datetime.now(timezone.utc)

    with session_scope() as session:
        for r in records:
            name = (r.get("name") or "").strip()
            if not name:
                continue
            domain = r.get("domain")
            norm_name = r.get("normalized_name")

            # Find or create Company
            company = None
            if domain:
                company = session.query(Company).filter(Company.domain == domain).first()
            if company is None and norm_name:
                company = session.query(Company).filter(Company.normalized_name == norm_name).first()

            if company is None:
                company = Company(
                    name=name,
                    domain=domain,
                    normalized_name=norm_name,
                    verification_status=VerificationStatus.emerging_github,
                    location_source=LocationSource.unknown,
                    first_seen_at=now,
                    last_seen_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(company)
                new_count += 1
            else:
                company.last_seen_at = now
                company.updated_at = now
                if not company.domain and domain:
                    company.domain = domain
                if not company.normalized_name and norm_name:
                    company.normalized_name = norm_name
                updated_count += 1

            # Update location if extracted
            country = r.get("country")
            city = r.get("city")
            if country and not company.country:
                company.country = country
                company.city = city

            # Update AI score based on LLM classification
            if r.get("is_ai_startup") and (company.ai_score is None or company.ai_score < 0.6):
                company.ai_score = 0.7

            # Flush to get company.id for IncubatorSignal
            session.flush()

            # Create IncubatorSignal if this looks like incubator data
            has_incubator_data = r.get("program") or r.get("batch")
            is_portfolio_url = any(
                kw in (source_url or "").lower()
                for kw in ["portfolio", "companies", "startups", "alumni", "cohort", "batch"]
            )
            if has_incubator_data or is_portfolio_url:
                existing_signal = (
                    session.query(IncubatorSignal)
                    .filter(
                        IncubatorSignal.company_name_raw == name,
                    )
                    .first()
                )
                if not existing_signal:
                    signal = IncubatorSignal(
                        company_id=company.id,
                        source=IncubatorSource.agentic_scrape,
                        company_name_raw=name,
                        website_url=r.get("website_url"),
                        industry=r.get("industry"),
                        batch=r.get("batch"),
                        program=r.get("program"),
                        description=r.get("description"),
                        profile_url=r.get("profile_url"),
                        collected_at=now,
                    )
                    session.add(signal)

    return new_count, updated_count


# ── Tool Use Agent (fallback for hard-to-scrape sites) ───────────────────

AGENT_TOOLS = [
    {
        "name": "fetch_page",
        "description": "Fetch and extract clean text content from one or more URLs using Tavily. Use this to get page content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "urls": {"type": "array", "items": {"type": "string"}, "description": "URLs to fetch (max 6)"}
            },
            "required": ["urls"],
        },
    },
    {
        "name": "fetch_page_rendered",
        "description": (
            "Fetch visible page text after JavaScript runs in headless Chromium (Playwright). "
            "Use when fetch_page returns only navigation, footers, empty shells, or messages about "
            "dynamic/SPA content. Max 2 URLs per call — use the real portfolio/listing URLs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "urls": {"type": "array", "items": {"type": "string"}, "description": "URLs to load in browser (max 2)"}
            },
            "required": ["urls"],
        },
    },
    {
        "name": "extract_companies",
        "description": "Extract structured company/startup records from raw text content. Returns a list of companies with name, industry, location, AI classification.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Raw page text to extract companies from"},
                "source_url": {"type": "string", "description": "The URL this content came from"},
            },
            "required": ["content", "source_url"],
        },
    },
    {
        "name": "read_instruction",
        "description": "Read previously saved scraping instructions for a domain. Returns the YAML instruction if it exists, or null.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Registrable domain like 'example.com'"}
            },
            "required": ["domain"],
        },
    },
    {
        "name": "save_results",
        "description": "Save the final list of extracted company records to the database. Call this when you are satisfied with the results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "records": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of company records to save",
                },
                "source_url": {"type": "string"},
            },
            "required": ["records", "source_url"],
        },
    },
]

AGENT_SYSTEM_PROMPT = """You are an AI web scraping agent. You were called because a fast extraction attempt got too few results.

Your goal: extract ALL startup/company records from the given website.

Strategy:
1. Check read_instruction for this domain — it may have hints from previous scrapes
2. Use fetch_page to get content from promising URLs (try subpages like /portfolio, /companies, /startups, pagination like ?page=2)
3. If fetch_page returns almost no company names (nav-only, empty, or "dynamic content"), use fetch_page_rendered on the SAME key URLs — it runs a real browser and often fixes React/Next.js SPAs
4. Use extract_companies on the fetched content to get structured data
5. If you think there are more pages (pagination, "load more", etc.), fetch additional pages
6. When you have a good set of results, use save_results

For each company extract: name, description, website_url, industry, country, city, is_ai_startup (bool), ai_category, program, batch, confidence (0-1).

Budget: at most 6 fetch_page calls total, and at most 4 fetch_page_rendered calls total (each up to 2 URLs). Prefer fetch_page_rendered early when the site looks JS-heavy."""


def _execute_agent_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    tavily_api_key: str,
    anthropic_api_key: str,
    source_url: str,
    save_to_db_flag: bool,
    agent_state: Optional[Dict[str, Any]] = None,
) -> str:
    """Execute an agent tool call and return the result as a string."""
    state = agent_state if agent_state is not None else {}

    if tool_name == "fetch_page":
        urls = tool_input.get("urls", [])[:6]
        results = _tavily_extract(tavily_api_key, urls)
        # Return truncated content
        out = []
        for r in results:
            content = (r.get("raw_content") or "")[:8000]
            out.append(f"URL: {r.get('url', '')}\nCONTENT:\n{content}")
        return "\n\n---\n\n".join(out) if out else "No content returned from Tavily."

    if tool_name == "fetch_page_rendered":
        used = int(state.get("rendered_batches", 0))
        if used >= 4:
            return (
                "fetch_page_rendered budget exhausted (max 4 calls). "
                "Use extract_companies on text you already have or save_results."
            )
        urls = tool_input.get("urls", [])[:2]
        if not urls:
            return "No URLs provided."
        if not _playwright_browser_enabled():
            return (
                "Playwright is disabled (AGENTIC_PLAYWRIGHT=0) or not installed. "
                "Install: pip install playwright && playwright install chromium"
            )
        state["rendered_batches"] = used + 1
        results = _playwright_extract_urls(urls, max_urls=2)
        if not results:
            return "fetch_page_rendered returned no results (browser failed to start?)."
        out = []
        for r in results:
            content = (r.get("raw_content") or "")[:16000]
            out.append(f"URL: {r.get('url', '')}\nCONTENT:\n{content}")
        return "\n\n---\n\n".join(out)

    elif tool_name == "extract_companies":
        content = tool_input.get("content", "")
        src = tool_input.get("source_url", source_url)
        # Build a fake chunk for _extract_records
        chunks = [{"url": src, "raw_content": content}]
        records = _extract_records(anthropic_api_key, src, chunks)
        return json.dumps([r.model_dump() for r in records], default=str)

    elif tool_name == "read_instruction":
        domain = tool_input.get("domain", "")
        instr = load_instruction(domain)
        if instr:
            return json.dumps(instr, default=str)
        return "No instruction found for this domain."

    elif tool_name == "save_results":
        raw_records = tool_input.get("records", [])
        src = tool_input.get("source_url", source_url)
        # Parse into ScrapedCompany, postprocess, save
        parsed: List[ScrapedCompany] = []
        for item in raw_records:
            try:
                parsed.append(ScrapedCompany(**item))
            except Exception:
                continue
        cleaned = _postprocess_records(parsed)
        if save_to_db_flag and cleaned:
            new_c, upd_c = _save_to_db(cleaned, source_url=src)
            return json.dumps({"saved": True, "new": new_c, "updated": upd_c, "total": len(cleaned)})
        return json.dumps({"saved": False, "total": len(cleaned), "records": cleaned[:50]})

    return f"Unknown tool: {tool_name}"


def _run_tool_use_agent(
    url: str,
    initial_records: List[ScrapedCompany],
    tavily_api_key: str,
    anthropic_api_key: str,
    save_to_db_flag: bool,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[List[ScrapedCompany], int, int]:
    """Run Claude tool-use agent loop. Returns (records, new_count, updated_count)."""
    if anthropic is None:
        raise RuntimeError("Install the anthropic package: pip install anthropic")

    client = anthropic.Anthropic(api_key=anthropic_api_key)
    model_id = _anthropic_model()

    # Give agent context about what already happened
    initial_summary = f"{len(initial_records)} companies" if initial_records else "0 companies"
    initial_names = ", ".join(r.name for r in initial_records[:10])
    user_msg = (
        f"Scrape this URL and extract ALL startup/company records: {url}\n\n"
        f"A fast extraction already ran and found only {initial_summary}. "
        f"That seems too few. Please try to find more.\n"
        f"Already found: {initial_names}{'...' if len(initial_records) > 10 else ''}"
    )

    messages: List[Dict[str, Any]] = [{"role": "user", "content": user_msg}]
    all_records: List[ScrapedCompany] = list(initial_records)
    new_count, updated_count = 0, 0
    max_iterations = 10
    agent_state: Dict[str, Any] = {"rendered_batches": 0}

    for iteration in range(max_iterations):
        response = client.messages.create(
            model=model_id,
            max_tokens=4000,
            system=AGENT_SYSTEM_PROMPT,
            tools=AGENT_TOOLS,
            messages=messages,
        )

        # Collect assistant content
        assistant_content = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text = block.text.strip()
                if text:
                    _notify(progress_callback, f"Agent: {text[:200]}")
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tool_calls.append(block)
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        messages.append({"role": "assistant", "content": assistant_content})

        if not tool_calls:
            break  # Agent is done

        # Execute tools and add results
        tool_results = []
        for tc in tool_calls:
            _notify(progress_callback, f"Agent tool: {tc.name}")
            result_str = _execute_agent_tool(
                tc.name,
                tc.input,
                tavily_api_key,
                anthropic_api_key,
                url,
                save_to_db_flag,
                agent_state,
            )

            # If extract_companies was called, accumulate records
            if tc.name == "extract_companies":
                try:
                    parsed = json.loads(result_str)
                    for item in parsed:
                        try:
                            all_records.append(ScrapedCompany(**item))
                        except Exception:
                            pass
                except Exception:
                    pass

            # If save_results was called, extract counts
            if tc.name == "save_results":
                try:
                    save_info = json.loads(result_str)
                    new_count = save_info.get("new", 0)
                    updated_count = save_info.get("updated", 0)
                except Exception:
                    pass

            max_reply = 24000 if tc.name in ("fetch_page", "fetch_page_rendered") else 8000
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result_str[:max_reply],
            })

        messages.append({"role": "user", "content": tool_results})

        if response.stop_reason == "end_turn":
            break

    return all_records, new_count, updated_count


# ── Progress helper ──────────────────────────────────────────────────────

def _notify(progress: Optional[Callable[[str], None]], message: str) -> None:
    if progress:
        progress(message)


# ── Cooldown check ───────────────────────────────────────────────────────

COOLDOWN_DAYS = 7


def _check_cooldown(instr: Optional[Dict[str, Any]]) -> Optional[str]:
    """Return ISO timestamp of last success if within cooldown period, else None."""
    if not instr:
        return None
    last = instr.get("last_success")
    if not last or not isinstance(last, dict):
        return None
    at_str = last.get("at")
    if not at_str:
        return None
    try:
        last_dt = datetime.fromisoformat(at_str.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - last_dt
        if age.days < COOLDOWN_DAYS:
            return at_str
    except (ValueError, TypeError):
        pass
    return None


def _load_last_report(site_domain: str) -> Optional[Dict[str, Any]]:
    """Load the most recent agentic run report for a domain from reports/agentic_runs/."""
    import glob as _glob
    report_dir = os.path.join(os.path.dirname(__file__), "..", "..", "reports", "agentic_runs")
    if not os.path.isdir(report_dir):
        return None
    files = sorted(_glob.glob(os.path.join(report_dir, "agentic_run_*.json")), reverse=True)
    for f in files[:50]:  # check last 50 reports
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("site_domain") == site_domain:
                return data
        except Exception:
            continue
    return None


# ── Main entry point ─────────────────────────────────────────────────────

def run_agentic_scrape(
    url: str,
    save_to_db: bool = True,
    max_retries: int = 2,
    force: bool = False,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> AgenticRunReport:
    tavily_api_key = os.getenv("TAVILY_API_KEY", "").strip()
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not tavily_api_key:
        raise RuntimeError("TAVILY_API_KEY is required")
    if not anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required")

    started = datetime.now(timezone.utc)
    run_id = f"agentic_run_{started.strftime('%Y%m%d_%H%M%S')}"

    # 1. Load instruction YAML
    _notify(progress_callback, "Loading scrape instructions…")
    site_domain = domain_for_url(url)
    instr = load_instruction(site_domain) if site_domain else None
    instruction_loaded = bool(instr)
    instr_path_str = str(instruction_path_for_domain(site_domain)) if site_domain else None

    # 1b. Cooldown check — skip if recently scraped (unless force=True)
    if not force:
        cooldown_at = _check_cooldown(instr)
        if cooldown_at:
            _notify(progress_callback,
                    f"Skipped — already scraped on {cooldown_at[:10]} "
                    f"(within {COOLDOWN_DAYS}-day cooldown). Use force=True to override.")
            # Return a report with cached data from last run
            last_report = _load_last_report(site_domain) if site_domain else None
            preview = (last_report or {}).get("extracted_preview", [])
            return AgenticRunReport(
                run_id=run_id,
                input_url=url,
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                plan=PlanResult(),
                attempts=[],
                final_validation=ValidationResult(
                    is_good=True,
                    reason=f"Cooldown: last scraped {cooldown_at[:10]}",
                    completeness_score=1.0, valid_name_ratio=1.0,
                    duplicate_ratio=0.0,
                    record_count=len(preview),
                ),
                total_records_before_clean=len(preview),
                total_records_after_clean=len(preview),
                saved_to_db=False,
                db_new_companies=0,
                db_updated_companies=0,
                site_domain=site_domain,
                instruction_loaded=instruction_loaded,
                instruction_path=instr_path_str,
                instruction_saved=False,
                instruction_saved_path=None,
                extracted_preview=preview,
            )

    # 2. Pick strategies (rule-based, no LLM)
    strategies = _pick_strategies(instr, max_retries)
    min_records = (instr or {}).get("quality_expectation_min_records", 1)

    # Build a PlanResult for reporting
    plan = PlanResult(
        strategy=strategies[0] if strategies else "single_page_extract",
        subpage_hints=(instr or {}).get("subpage_hints", []),
        pagination_hints=(instr or {}).get("pagination_hints", []),
        quality_expectation_min_records=min_records,
        data_available=[],
    )

    attempts: List[RetryAttempt] = []
    best_records: List[ScrapedCompany] = []
    best_validation: Optional[ValidationResult] = None
    winning_strategy = strategies[0] if strategies else "single_page_extract"

    for idx, strategy in enumerate(strategies, start=1):
        # 3. Build URLs for this strategy
        if idx == 1:
            candidate_urls = build_initial_fetch_urls(url, instr)
        else:
            candidate_urls = _derive_retry_urls(url, strategy, instr)

        # 4. Tavily extract
        _notify(progress_callback, f"[{idx}/{len(strategies)}] Tavily extracting ({len(candidate_urls[:6])} URLs)…")
        chunks = _tavily_extract(tavily_api_key, candidate_urls[:6])
        before_pw = _chunks_text_total(chunks)
        chunks = _maybe_enrich_chunks_playwright(chunks, candidate_urls[:6])
        if _chunks_text_total(chunks) > before_pw:
            _notify(progress_callback, f"[{idx}/{len(strategies)}] Playwright fallback added richer text ({before_pw} → {_chunks_text_total(chunks)} chars)…")

        if not chunks:
            attempts.append(RetryAttempt(
                attempt=idx,
                strategy=strategy,
                fetched_urls=candidate_urls[:6],
                validation=ValidationResult(
                    is_good=False, reason="Tavily returned no content",
                    completeness_score=0.0, valid_name_ratio=0.0, duplicate_ratio=0.0, record_count=0,
                ),
            ))
            continue

        # 5. Claude extract (THE ONLY LLM CALL)
        _notify(progress_callback, f"[{idx}/{len(strategies)}] Claude extracting records…")
        records = _extract_records(anthropic_api_key, url, chunks)

        # 6. Rule-based validation (NO LLM)
        validation = _validate_records(records, min_records=max(1, min_records))
        attempts.append(RetryAttempt(
            attempt=idx,
            strategy=strategy,
            fetched_urls=candidate_urls[:6],
            validation=validation,
        ))

        if best_validation is None or validation.completeness_score > best_validation.completeness_score:
            best_validation = validation
            best_records = records
            winning_strategy = strategy

        if validation.is_good:
            best_records = records
            best_validation = validation
            winning_strategy = strategy
            break

    # 7. Check if fast path succeeded or need agent fallback
    if best_validation is None:
        best_validation = ValidationResult(
            is_good=False, reason="No valid attempt completed",
            completeness_score=0.0, valid_name_ratio=0.0, duplicate_ratio=0.0, record_count=0,
        )

    new_count, updated_count = (0, 0)
    raw_before_post = 0

    if best_validation.is_good:
        # ── Fast path succeeded ──
        _notify(progress_callback, "Normalizing and deduplicating…")
        raw_before_post = len(best_records)
        cleaned = _postprocess_records(best_records)
        cleaned = _enrich_records(anthropic_api_key, cleaned, progress_callback)
        preview = cleaned[:EXTRACTED_PREVIEW_CAP]
        if save_to_db and cleaned:
            _notify(progress_callback, f"Saving {len(cleaned)} records to database…")
            new_count, updated_count = _save_to_db(cleaned, source_url=url)
    else:
        # ── Fast path failed → Agent fallback ──
        _notify(progress_callback,
                f"Fast path got {best_validation.record_count} records "
                f"({best_validation.reason}). Switching to Agent mode…")
        try:
            agent_records, new_count, updated_count = _run_tool_use_agent(
                url=url,
                initial_records=best_records,
                tavily_api_key=tavily_api_key,
                anthropic_api_key=anthropic_api_key,
                save_to_db_flag=save_to_db,
                progress_callback=progress_callback,
            )
            raw_before_post = len(agent_records)
            cleaned = _postprocess_records(agent_records)
            cleaned = _enrich_records(anthropic_api_key, cleaned, progress_callback)
            preview = cleaned[:EXTRACTED_PREVIEW_CAP]
        except Exception as e:
            _notify(progress_callback, f"Agent failed: {e}. Using fast path results.")
            raw_before_post = len(best_records)
            cleaned = _postprocess_records(best_records)
            cleaned = _enrich_records(anthropic_api_key, cleaned, progress_callback)
            preview = cleaned[:EXTRACTED_PREVIEW_CAP]
            if save_to_db and cleaned:
                new_count, updated_count = _save_to_db(cleaned, source_url=url)

    # Align final_validation + instruction YAML with deduped rows (matches Done! / DB)
    best_validation = _validate_records(
        _cleaned_to_scraped(cleaned),
        min_records=max(1, min_records),
    )

    # 9. Save instruction YAML
    instruction_saved = False
    instruction_saved_path: Optional[str] = None
    if site_domain and should_persist_instruction(best_validation):
        _notify(progress_callback, "Saving scrape instruction YAML…")
        try:
            instruction_saved_path = save_instruction_success(
                site_domain, url, plan, winning_strategy, best_validation, run_id,
            )
            instruction_saved = True
        except OSError:
            instruction_saved = False

    finished = datetime.now(timezone.utc)
    _notify(progress_callback, f"Done! {len(cleaned)} companies extracted, {new_count} new, {updated_count} updated.")

    return AgenticRunReport(
        run_id=run_id,
        input_url=url,
        started_at=started,
        finished_at=finished,
        plan=plan,
        attempts=attempts,
        final_validation=best_validation,
        total_records_before_clean=raw_before_post,
        total_records_after_clean=len(cleaned),
        saved_to_db=save_to_db,
        db_new_companies=new_count,
        db_updated_companies=updated_count,
        site_domain=site_domain,
        instruction_loaded=instruction_loaded,
        instruction_path=instr_path_str,
        instruction_saved=instruction_saved,
        instruction_saved_path=instruction_saved_path,
        extracted_preview=preview,
    )


# ── Batch scrape ─────────────────────────────────────────────────────────

def run_batch_scrape(
    sites: List[Dict[str, Any]],
    save_to_db: bool = True,
    max_retries: int = 1,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> List[AgenticRunReport]:
    """Run agentic scrape on each site sequentially. One failure doesn't stop the batch."""
    reports: List[AgenticRunReport] = []
    for i, site in enumerate(sites, 1):
        name = site.get("name", site.get("url", ""))
        _notify(progress_callback, f"━━━ [{i}/{len(sites)}] {name} ━━━")
        try:
            report = run_agentic_scrape(
                url=site["url"],
                save_to_db=save_to_db,
                max_retries=max_retries,
                progress_callback=progress_callback,
            )
            reports.append(report)
        except Exception as e:
            _notify(progress_callback, f"FAILED {name}: {e}")
    return reports
