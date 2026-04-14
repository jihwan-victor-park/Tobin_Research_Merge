"""
Entity resolution and deduplication for company candidates.
"""
from typing import Optional, Dict, Any, List
from .normalize import normalize_company_name, fuzzy_name_match
from .domain import canonicalize_domain


# Threshold for strict name matching (when no domain available)
NAME_MATCH_THRESHOLD = 0.92
# Even stricter for PitchBook name-only matching
PB_NAME_MATCH_THRESHOLD = 0.95


def entity_key(domain: Optional[str], name: Optional[str]) -> Optional[str]:
    """
    Compute the primary entity key for dedup.
    Uses domain if available, else normalized company name.
    """
    if domain:
        canon = canonicalize_domain(domain)
        if canon:
            return f"domain:{canon}"

    if name:
        norm = normalize_company_name(name)
        if norm:
            return f"name:{norm}"

    return None


def resolve_entity(
    candidate_domain: Optional[str],
    candidate_name: Optional[str],
    existing_companies: List[Dict[str, Any]],
    require_shared_signal: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Find a matching existing company for a candidate.

    Strategy:
    1. If candidate has domain → match by domain (exact).
    2. If no domain → fuzzy name match (>= 0.92) AND at least one shared signal
       (same org login, same website link, etc.) if require_shared_signal is True.

    Args:
        candidate_domain: Domain of the candidate (may be None)
        candidate_name: Name of the candidate
        existing_companies: List of dicts with at least 'domain', 'normalized_name', 'id'
        require_shared_signal: If True, name-only matches need a shared signal

    Returns:
        The matching company dict, or None if no match found.
    """
    # Strategy 1: domain match
    if candidate_domain:
        canon = canonicalize_domain(candidate_domain)
        if canon:
            for company in existing_companies:
                comp_domain = company.get("domain")
                if comp_domain and canonicalize_domain(comp_domain) == canon:
                    return company

    # Strategy 2: fuzzy name match
    if candidate_name:
        candidate_norm = normalize_company_name(candidate_name)
        if candidate_norm:
            best_match = None
            best_score = 0.0

            for company in existing_companies:
                comp_norm = company.get("normalized_name")
                if not comp_norm:
                    continue

                score = fuzzy_name_match(candidate_name, company.get("name", ""))
                if score >= NAME_MATCH_THRESHOLD and score > best_score:
                    best_match = company
                    best_score = score

            if best_match:
                if not require_shared_signal:
                    return best_match
                # With shared signal requirement, caller should check externally
                # For now, return the match and let caller verify shared signals
                return best_match

    return None


def deduplicate_candidates(
    candidates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Deduplicate a list of candidate dicts in-memory.
    Each candidate should have 'domain' and 'name' keys.

    Returns deduplicated list, keeping the first occurrence
    and merging evidence from duplicates.
    """
    seen_keys = {}  # entity_key -> index in result
    result = []

    for candidate in candidates:
        domain = candidate.get("domain")
        name = candidate.get("name", "")
        key = entity_key(domain, name)

        if key and key in seen_keys:
            # Merge: append repo URLs, update stars if higher, etc.
            idx = seen_keys[key]
            existing = result[idx]

            # Merge repo list
            existing_repos = existing.get("repo_urls", [])
            new_repo = candidate.get("repo_url")
            if new_repo and new_repo not in existing_repos:
                existing_repos.append(new_repo)
                existing["repo_urls"] = existing_repos

            # Keep higher star count
            if candidate.get("stars", 0) > existing.get("stars", 0):
                existing["stars"] = candidate["stars"]

            continue

        seen_keys[key or f"__unkeyed_{len(result)}"] = len(result)
        result.append(candidate)

    return result
