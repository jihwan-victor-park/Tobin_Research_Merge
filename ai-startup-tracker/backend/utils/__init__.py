"""Utility modules for the AI startup tracker pipeline."""
from .domain import canonicalize_domain, extract_domains_from_text, is_product_domain
from .normalize import normalize_company_name, fuzzy_name_match
from .scoring import compute_ai_score, compute_startup_score
from .dedup import resolve_entity, deduplicate_candidates
