"""
Failure diagnosis — one-line natural-language explanation of *why* a scraper
keeps failing. Called from HealthMonitor.update() after consecutive_failures
hits the trigger threshold (currently 2).

The diagnosis is a short, human-readable string the dashboard can show next to
each pending site, so the operator can decide quickly whether to fix the
scraper, write a YAML override, or shrug and let the 90-day exclusion kick in.

Format: "<bucket>: <one short sentence>"
where bucket ∈ {javascript_spa, login_required, anti_bot, rate_limited,
                structure_changed, no_portfolio_page, network_error, other}.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_BUCKETS = (
    "javascript_spa",
    "login_required",
    "anti_bot",
    "rate_limited",
    "structure_changed",
    "no_portfolio_page",
    "network_error",
    "other",
)

_PROMPT = (
    "You are diagnosing why a web scraper keeps failing on a specific URL. "
    "Pick exactly one bucket from this list and write one short sentence "
    "explaining the likely cause based on the error and the URL itself.\n\n"
    "Buckets: " + ", ".join(_BUCKETS) + ".\n\n"
    "Reply on a single line, formatted exactly as:\n"
    "<bucket>: <one sentence, max 20 words>\n\n"
    "No prose before or after."
)


def diagnose_failure(
    domain: str,
    url: Optional[str],
    last_error: Optional[str],
    recent_html_sample: Optional[str] = None,
) -> Optional[str]:
    """Return a one-line diagnosis, or None if no LLM is configured."""
    # Lazy import keeps the orchestrator startup free of LLM dependencies.
    try:
        from backend.utils.llm_filter import (
            _call_anthropic, _call_groq, _call_ollama, _call_together,
            ANTHROPIC_API_KEY, GROQ_API_KEY, TOGETHER_API_KEY, LLM_BACKEND,
        )
    except Exception as e:
        logger.debug(f"diagnose: LLM transport unavailable: {e}")
        return None

    backend = (LLM_BACKEND or "together").lower()
    call_fn = {
        "together": _call_together,
        "groq": _call_groq,
        "ollama": _call_ollama,
        "anthropic": _call_anthropic,
    }.get(backend)
    if call_fn is None:
        return None
    if backend == "together" and not TOGETHER_API_KEY:
        return None
    if backend == "groq" and not GROQ_API_KEY:
        return None
    if backend == "anthropic" and not ANTHROPIC_API_KEY:
        return None

    user_parts = [
        f"Domain: {domain}",
        f"URL: {url or '(unknown)'}",
        f"Last error: {(last_error or '(none)')[:400]}",
    ]
    if recent_html_sample:
        user_parts.append(f"HTML sample (first 600 chars):\n{recent_html_sample[:600]}")
    user = "\n".join(user_parts)

    messages = [
        {"role": "system", "content": _PROMPT},
        {"role": "user", "content": user},
    ]
    try:
        raw = call_fn(messages, temperature=0.0)
    except Exception as e:
        logger.warning(f"diagnose call failed for {domain}: {e}")
        return None

    line = raw.strip().splitlines()[0].strip() if raw.strip() else ""
    if not line:
        return None
    # Validate bucket prefix; if missing, prepend "other:".
    bucket = line.split(":", 1)[0].strip().lower()
    if bucket not in _BUCKETS:
        line = f"other: {line}"
    return line[:240]
