"""
Unified AI-or-not classifier — single source of truth used by every scraper.

Decision flow (cheap → expensive):
  1. Strong AI keyword hit on name/description/tags → (True, 1.0, 'keyword')
  2. No tech-adjacent term anywhere               → (False, 1.0, 'keyword')
  3. Ambiguous (tech but no clear AI marker)      → one-shot LLM → (?, conf, 'llm')

The LLM step reuses the chat transports already wired in
`backend.utils.llm_filter` (Together.ai by default, Anthropic / Groq / Ollama
via LLM_BACKEND env). If no LLM key is configured the function falls back to
the keyword decision so callers always get a usable answer.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ── Keyword vocabularies ──────────────────────────────────────────────────

AI_KEYWORDS = [
    "artificial intelligence", "machine learning", "large language model", "llm",
    "generative ai", "generative", "gpt", "neural network", "deep learning", "nlp",
    "natural language processing", "computer vision", "data science", "autonomous",
    "robotics", "predictive", "recommendation engine", "transformer",
    "diffusion", "reinforcement learning", "rag", "retrieval augmented",
    "foundation model", "fine-tuning", "embeddings", "agentic", "ai agent",
    "ai-powered", "ai-driven", "ai assistant", "copilot", "chatbot",
]
# 'ai' alone is too noisy ("Aida", "Maine"), so require a word boundary AND
# either a hyphen or following whitespace+keyword. We treat plain " ai " as
# AI but only when it isn't part of a longer word.
_AI_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:" + "|".join(re.escape(k) for k in AI_KEYWORDS) + r")(?![a-z0-9])",
    re.IGNORECASE,
)
_BARE_AI_PATTERN = re.compile(r"(?<![a-z0-9])ai(?![a-z0-9])", re.IGNORECASE)

# Words that suggest tech/software but aren't AI by themselves. Presence of
# any of these (without an AI keyword) = "ambiguous" → escalate to LLM.
TECH_HINTS = [
    "software", "saas", "platform", "api", "cloud", "data", "analytics",
    "automation", "developer", "infrastructure", "iot", "fintech", "healthtech",
    "biotech", "blockchain", "crypto", "web3", "mobile app", "marketplace",
    "no-code", "low-code", "devops",
]
_TECH_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:" + "|".join(re.escape(k) for k in TECH_HINTS) + r")(?![a-z0-9])",
    re.IGNORECASE,
)


# ── Public entry point ────────────────────────────────────────────────────

def classify_ai(
    name: str,
    description: Optional[str] = None,
    tags: Optional[str] = None,
    keyword_only: bool = False,
) -> Tuple[bool, float, str]:
    """Return (is_ai, confidence, source).

    source ∈ {'keyword', 'llm', 'fallback'}.
    Confidence is 1.0 for keyword decisions, 0.0–1.0 for LLM, and 0.5 for
    fallback (LLM unavailable on an ambiguous case → defaults to False).

    keyword_only=True skips the per-record LLM escalation entirely: ambiguous
    cases (tech but no explicit AI marker) return a conservative (False, 0.5,
    'keyword_only') instead of making a network call. This is what high-volume
    scrapers should use — paying one LLM round-trip per company turns a 5k-row
    portfolio fetch into thousands of sequential API calls, which times out and
    leaves the run only partially saved. The bulk pass
    (`scripts/reclassify_ai_with_llm.py`) re-resolves the ambiguous rows later.
    """
    text = " ".join(filter(None, [name, description, tags])).strip()
    if not text:
        return (False, 1.0, "keyword")

    if _AI_PATTERN.search(text) or _BARE_AI_PATTERN.search(text):
        return (True, 1.0, "keyword")

    # Strong miss: no tech hints anywhere → almost certainly not AI.
    if not _TECH_PATTERN.search(text):
        return (False, 1.0, "keyword")

    # Ambiguous. Without LLM escalation, default to a conservative miss and
    # let the bulk reclassifier resolve it later.
    if keyword_only:
        return (False, 0.5, "keyword_only")

    # Ambiguous → ask the LLM.
    decision = _llm_decide(name=name, description=description, tags=tags)
    if decision is None:
        return (False, 0.5, "fallback")
    is_ai, confidence = decision
    return (is_ai, confidence, "llm")


# ── LLM step ──────────────────────────────────────────────────────────────

_LLM_SYSTEM = (
    "You decide whether a company is an AI startup. Reply with strict JSON: "
    '{"is_ai": true|false, "confidence": 0.0-1.0}. '
    "Treat as AI only if the core product applies machine learning, LLMs, "
    "computer vision, robotics autonomy, or similar AI methods. Companies that "
    "merely use AI internally (e.g. CRM that adds an AI summarizer) are NOT "
    "AI startups. No prose, JSON only."
)


def _llm_decide(
    name: str,
    description: Optional[str],
    tags: Optional[str],
) -> Optional[Tuple[bool, float]]:
    """One-shot LLM call. Returns None if no LLM is configured."""
    # Lazy import so the keyword path never pays the import cost.
    try:
        from backend.utils.llm_filter import (
            _call_anthropic, _call_groq, _call_ollama, _call_together,
            ANTHROPIC_API_KEY, GROQ_API_KEY, TOGETHER_API_KEY, LLM_BACKEND,
        )
    except Exception as e:
        logger.debug(f"LLM transport unavailable: {e}")
        return None

    backend = (os.getenv("CLASSIFY_AI_BACKEND") or LLM_BACKEND or "together").lower()
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

    user = (
        f"Name: {name}\n"
        f"Description: {description or '(none)'}\n"
        f"Tags: {tags or '(none)'}\n"
        "Answer the JSON now."
    )
    messages = [
        {"role": "system", "content": _LLM_SYSTEM},
        {"role": "user", "content": user},
    ]

    try:
        raw = call_fn(messages, temperature=0.0)
    except Exception as e:
        logger.debug(f"classify_ai LLM call failed: {e}")
        return None

    raw = raw.strip()
    if raw.startswith("```"):
        # Strip markdown fence.
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        data = json.loads(raw)
    except Exception:
        # Try to pluck out a json object from the text.
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except Exception:
            return None

    is_ai = bool(data.get("is_ai"))
    try:
        confidence = float(data.get("confidence", 0.6))
    except (TypeError, ValueError):
        confidence = 0.6
    confidence = max(0.0, min(1.0, confidence))
    return (is_ai, confidence)
