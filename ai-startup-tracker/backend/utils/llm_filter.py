"""
LLM-based startup classifier using Together.ai, Groq, or Ollama.

Evaluates GitHub repos to distinguish real startups/companies from
personal projects, research repos, and community tools.

Backend options (set LLM_BACKEND in .env):
  - "together" (recommended): Together.ai cloud, generous free tier
  - "groq": Groq cloud, very fast but strict rate limits on free tier
  - "ollama": Local Ollama server, no rate limits but requires working GPU
"""
import json
import logging
import os
import time
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("llm_filter")

# API keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")

# Backend config
LLM_BACKEND = os.getenv("LLM_BACKEND", "together")  # "together", "groq", or "ollama"
LLM_MODEL = os.getenv("LLM_MODEL", "meta-llama/Llama-3.3-70B-Instruct-Turbo")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Repos with heuristic startup_likelihood >= this skip LLM (already confident)
HIGH_CONFIDENCE_THRESHOLD = 0.70

# Repos with heuristic startup_likelihood < this get auto-rejected (save LLM calls)
LOW_CONFIDENCE_THRESHOLD = 0.10

# LLM must return confidence >= this to classify as startup
LLM_STARTUP_CONFIDENCE = 0.6

# How many repos to send per LLM call
BATCH_SIZE = 25

# Retry settings
MAX_RETRIES = 3
INITIAL_BACKOFF = 30

SYSTEM_PROMPT = """You are an expert analyst that classifies GitHub repositories into categories.
Your job is to determine whether a repository belongs to a STARTUP/COMPANY or is something else.

Categories:
- "startup": A commercial product, SaaS, platform, or tool built by a company or team aiming to be a business. Signs include: custom domain/website, organization account, commercial language (pricing, enterprise, API keys, waitlist, demo), professional README with branding, multiple contributors, clear product positioning.
- "personal_project": An individual's side project, portfolio piece, experiment, or learning exercise. Signs include: user account (not org), no website/domain, informal README, single contributor, no commercial language, names like "my-*" or "*-playground".
- "research": Academic research, paper implementations, benchmarks, or experimental ML work. Signs include: paper references, arxiv links, university affiliations, benchmark results, "reproduce" language.
- "community_tool": Open-source utilities, libraries, or frameworks built by the community without commercial intent. Signs include: MIT/Apache license focus, "contributions welcome", no pricing/enterprise language, purely technical documentation.

For each repo, respond with a JSON object containing:
- "classification": one of "startup", "personal_project", "research", "community_tool"
- "confidence": float 0.0-1.0 indicating how confident you are
- "reason": one sentence explaining why"""

def _build_repo_summary(rec: Dict) -> str:
    """Build a concise text summary of a repo for the LLM."""
    parts = []
    parts.append(f"Repo: {rec.get('repo_full_name', 'unknown')}")
    parts.append(f"Owner type: {rec.get('owner_type', 'unknown')}")

    desc = rec.get("description", "")
    if desc:
        parts.append(f"Description: {desc[:200]}")

    domain = rec.get("domain")
    if domain:
        parts.append(f"Website domain: {domain}")

    homepage = rec.get("homepage_url", "")
    if homepage:
        parts.append(f"Homepage: {homepage}")

    topics = rec.get("topics", [])
    if topics:
        parts.append(f"Topics: {', '.join(topics[:10])}")

    parts.append(f"Stars: {rec.get('stars', 0)}, Forks: {rec.get('forks', 0)}")

    lang = rec.get("language")
    if lang:
        parts.append(f"Language: {lang}")

    readme = rec.get("readme_snippet", "")
    if readme:
        parts.append(f"README excerpt:\n{readme[:500]}")

    return "\n".join(parts)


def _call_together(messages: List[Dict], temperature: float = 0.1) -> str:
    """Call Together.ai API (OpenAI-compatible)."""
    import requests

    if not TOGETHER_API_KEY:
        raise RuntimeError("TOGETHER_API_KEY not set")

    resp = requests.post(
        "https://api.together.xyz/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {TOGETHER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": LLM_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 4096,
        },
        timeout=90,
    )

    if resp.status_code == 429:
        retry_after = resp.headers.get("retry-after")
        wait = int(retry_after) + 2 if retry_after else INITIAL_BACKOFF
        raise RateLimitError(wait)

    if resp.status_code != 200:
        raise RuntimeError(f"Together.ai error ({resp.status_code}): {resp.text[:300]}")

    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def _call_ollama(messages: List[Dict], temperature: float = 0.1) -> str:
    """Call Ollama local API."""
    import requests

    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": LLM_MODEL,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": 2048,
                "num_ctx": 4096,
            },
            "format": "json",
        },
        timeout=120,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"Ollama error ({resp.status_code}): {resp.text[:200]}")

    data = resp.json()
    return data["message"]["content"].strip()


def _call_groq(messages: List[Dict], temperature: float = 0.1) -> str:
    """Call Groq cloud API."""
    import requests

    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set")

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": LLM_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 4096,
        },
        timeout=60,
    )

    if resp.status_code == 429:
        retry_after = resp.headers.get("retry-after")
        wait = int(retry_after) + 2 if retry_after else INITIAL_BACKOFF
        raise RateLimitError(wait)

    if resp.status_code != 200:
        raise RuntimeError(f"Groq API error ({resp.status_code}): {resp.text[:200]}")

    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


class RateLimitError(Exception):
    def __init__(self, wait_seconds: int):
        self.wait_seconds = wait_seconds
        super().__init__(f"Rate limited, retry after {wait_seconds}s")


def classify_batch_with_llm(records: List[Dict]) -> List[Dict]:
    """
    Classify a batch of repos using Together.ai, Groq, or Ollama.
    """
    backend = LLM_BACKEND.lower()

    if backend == "groq" and not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not set, skipping LLM classification")
        return [{"classification": "unknown", "confidence": 0.0, "reason": "no API key"}] * len(records)
    if backend == "together" and not TOGETHER_API_KEY:
        logger.warning("TOGETHER_API_KEY not set, skipping LLM classification")
        return [{"classification": "unknown", "confidence": 0.0, "reason": "no API key"}] * len(records)

    # Build the user prompt with all repos
    repo_blocks = []
    for i, rec in enumerate(records):
        summary = _build_repo_summary(rec)
        repo_blocks.append(f"--- REPO {i+1} ---\n{summary}")

    user_prompt = (
        "Classify each of the following GitHub repositories. "
        "Return a JSON array with one object per repo, in the same order.\n\n"
        + "\n\n".join(repo_blocks)
        + "\n\nReturn ONLY the JSON array, no other text."
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    call_fn = {"together": _call_together, "groq": _call_groq, "ollama": _call_ollama}
    if backend not in call_fn:
        logger.error(f"Unknown LLM_BACKEND: {backend}. Use 'together', 'groq', or 'ollama'.")
        return [{"classification": "unknown", "confidence": 0.0, "reason": f"unknown backend: {backend}"}] * len(records)

    for attempt in range(MAX_RETRIES):
        try:
            content = call_fn[backend](messages)

            # Parse JSON from response (handle markdown code blocks)
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()

            results = json.loads(content)

            if not isinstance(results, list):
                results = [results]

            # Pad or trim to match input length
            while len(results) < len(records):
                results.append({"classification": "unknown", "confidence": 0.0, "reason": "missing from response"})
            results = results[:len(records)]

            return results

        except RateLimitError as e:
            logger.warning(
                f"Rate limited (attempt {attempt+1}/{MAX_RETRIES}). "
                f"Waiting {e.wait_seconds}s before retry..."
            )
            time.sleep(e.wait_seconds)
            continue
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            if attempt < MAX_RETRIES - 1:
                logger.info(f"Retrying batch (attempt {attempt+2}/{MAX_RETRIES})...")
                continue
            return [{"classification": "unknown", "confidence": 0.0, "reason": "parse error"}] * len(records)
        except Exception as e:
            error_msg = str(e)
            if "Connection refused" in error_msg and backend == "ollama":
                logger.error("Ollama is not running! Start it with: ollama serve")
                return [{"classification": "unknown", "confidence": 0.0, "reason": "Ollama not running"}] * len(records)
            logger.error(f"LLM classification failed: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(5)
                continue
            return [{"classification": "unknown", "confidence": 0.0, "reason": str(e)}] * len(records)

    logger.error(f"All {MAX_RETRIES} retries exhausted")
    return [{"classification": "unknown", "confidence": 0.0, "reason": "retries exhausted"}] * len(records)


def filter_startups_with_llm(records: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """
    Filter processed records using LLM classification.

    Strategy:
    - High heuristic score (>= 0.70): auto-include, skip LLM
    - Low heuristic score (< 0.10): auto-exclude, skip LLM
    - Middle range: use LLM to classify

    Returns: (accepted_records, rejected_records)
    """
    accepted = []
    rejected = []
    needs_llm = []

    for rec in records:
        likelihood = rec.get("startup_likelihood", 0.0) or 0.0

        if likelihood >= HIGH_CONFIDENCE_THRESHOLD:
            rec["llm_classification"] = "startup"
            rec["llm_confidence"] = None
            rec["llm_reason"] = "auto-accepted: high heuristic score"
            accepted.append(rec)
        elif likelihood < LOW_CONFIDENCE_THRESHOLD:
            rec["llm_classification"] = "personal_project"
            rec["llm_confidence"] = None
            rec["llm_reason"] = "auto-rejected: low heuristic score"
            rejected.append(rec)
        else:
            needs_llm.append(rec)

    logger.info(
        f"LLM filter: {len(accepted)} auto-accepted, {len(rejected)} auto-rejected, "
        f"{len(needs_llm)} need LLM classification"
    )

    # Process LLM batches
    total_batches = (len(needs_llm) + BATCH_SIZE - 1) // BATCH_SIZE
    consecutive_failures = 0

    for i in range(0, len(needs_llm), BATCH_SIZE):
        batch_num = i // BATCH_SIZE + 1
        batch = needs_llm[i:i + BATCH_SIZE]

        if consecutive_failures >= 3:
            logger.warning(f"3 consecutive LLM failures, falling back to heuristics for remaining {len(needs_llm) - i} repos")
            for rec in needs_llm[i:]:
                likelihood = rec.get("startup_likelihood", 0) or 0
                rec["llm_classification"] = "unknown"
                rec["llm_confidence"] = 0.0
                rec["llm_reason"] = "LLM unavailable, heuristic fallback"
                if likelihood >= 0.35:
                    accepted.append(rec)
                else:
                    rejected.append(rec)
            break

        logger.info(f"LLM batch {batch_num}/{total_batches} ({len(batch)} repos)...")
        results = classify_batch_with_llm(batch)

        batch_failed = all(r.get("classification") == "unknown" for r in results)
        if batch_failed:
            consecutive_failures += 1
        else:
            consecutive_failures = 0

        for rec, result in zip(batch, results):
            classification = result.get("classification", "unknown")
            confidence = float(result.get("confidence", 0.0))
            reason = result.get("reason", "")

            rec["llm_classification"] = classification
            rec["llm_confidence"] = confidence
            rec["llm_reason"] = reason

            if classification == "startup" and confidence >= LLM_STARTUP_CONFIDENCE:
                accepted.append(rec)
            elif classification == "unknown":
                if (rec.get("startup_likelihood", 0) or 0) >= 0.35:
                    accepted.append(rec)
                else:
                    rejected.append(rec)
            else:
                rejected.append(rec)

        # Pacing for cloud APIs (not needed for Ollama)
        if LLM_BACKEND.lower() != "ollama" and i + BATCH_SIZE < len(needs_llm) and consecutive_failures == 0:
            time.sleep(2)  # Together.ai is more generous, 2s is enough

    logger.info(
        f"After LLM filter: {len(accepted)} accepted, {len(rejected)} rejected"
    )

    return accepted, rejected
