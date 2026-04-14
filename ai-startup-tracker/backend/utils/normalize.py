"""
Company name normalization and fuzzy matching utilities.
"""
import re
from typing import Optional

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None


# Suffixes to strip from company names
COMPANY_SUFFIXES = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|co|corp|corporation|"
    r"labs|lab|ai|io|tech|technologies|technology|software|"
    r"solutions|systems|platform|group|holding|holdings|"
    r"gmbh|sa|sas|sarl|bv|pty|pte)\b\.?",
    re.IGNORECASE,
)


def normalize_company_name(name: str) -> Optional[str]:
    """
    Normalize a company name for matching:
    - Lowercase
    - Remove punctuation
    - Remove common company suffixes (inc, llc, ltd, labs, ai, etc.)
    - Collapse whitespace
    - Strip

    Returns None if name is empty after normalization.
    """
    if not name or not isinstance(name, str):
        return None

    result = name.lower().strip()

    # Remove punctuation except hyphens (some company names use them)
    result = re.sub(r"[^\w\s-]", " ", result)

    # Remove company suffixes
    result = COMPANY_SUFFIXES.sub(" ", result)

    # Remove standalone single characters
    result = re.sub(r"\b\w\b", " ", result)

    # Collapse whitespace
    result = re.sub(r"\s+", " ", result).strip()

    # Remove leading/trailing hyphens
    result = result.strip("-").strip()

    return result if result else None


def fuzzy_name_match(name_a: str, name_b: str) -> float:
    """
    Compute fuzzy similarity between two company names.
    Returns a score between 0.0 and 1.0.

    Uses token_sort_ratio to handle word order differences.
    Falls back to simple ratio if rapidfuzz is not installed.
    """
    if not name_a or not name_b:
        return 0.0

    norm_a = normalize_company_name(name_a)
    norm_b = normalize_company_name(name_b)

    if not norm_a or not norm_b:
        return 0.0

    # Exact match
    if norm_a == norm_b:
        return 1.0

    if fuzz is not None:
        # rapidfuzz returns 0-100, normalize to 0-1
        return fuzz.token_sort_ratio(norm_a, norm_b) / 100.0

    # Fallback: simple character-level similarity (SequenceMatcher-like)
    from difflib import SequenceMatcher
    return SequenceMatcher(None, norm_a, norm_b).ratio()
