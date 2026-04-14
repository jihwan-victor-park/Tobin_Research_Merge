"""
File-based scrape instructions (YAML) per registrable domain.

Stored under: data/scrape_instructions/<domain>.yaml
No vector DB — simple load/save for agent reuse.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from backend.utils.domain import canonicalize_domain

from .schemas import PlanResult, ValidationResult

INSTRUCTION_SUBDIR = "data/scrape_instructions"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def instruction_dir() -> Path:
    d = _project_root() / INSTRUCTION_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def domain_for_url(url: str) -> Optional[str]:
    return canonicalize_domain(url)


def _safe_domain_filename(domain: str) -> str:
    d = (domain or "").strip().lower()
    d = re.sub(r"[^\w.\-]+", "_", d)
    return d or "unknown"


def instruction_path_for_domain(domain: str) -> Path:
    return instruction_dir() / f"{_safe_domain_filename(domain)}.yaml"


def load_instruction(domain: Optional[str]) -> Optional[Dict[str, Any]]:
    if not domain:
        return None
    path = instruction_path_for_domain(domain)
    if not path.is_file():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else None


def merge_plan_with_instruction(plan: PlanResult, instr: Dict[str, Any]) -> PlanResult:
    """Prefer saved strategy/hints when instruction exists."""
    sub = list(instr.get("subpage_hints") or [])
    merged_sub = sub + [h for h in plan.subpage_hints if h not in sub]
    pag = list(instr.get("pagination_hints") or [])
    merged_pag = pag + [h for h in plan.pagination_hints if h not in pag]
    strategy = (instr.get("preferred_strategy") or "").strip() or plan.strategy
    min_rec = instr.get("quality_expectation_min_records")
    qmin = int(min_rec) if min_rec is not None else plan.quality_expectation_min_records
    return plan.model_copy(
        update={
            "strategy": strategy,
            "subpage_hints": merged_sub[:30],
            "pagination_hints": merged_pag[:30],
            "quality_expectation_min_records": max(1, qmin),
        }
    )


def build_initial_fetch_urls(input_url: str, instr: Optional[Dict[str, Any]]) -> List[str]:
    """Seed URLs: input first, then instruction seed_urls (deduped)."""
    urls: List[str] = [input_url.strip()]
    if not instr:
        return urls
    for u in instr.get("seed_urls") or []:
        u = (u or "").strip()
        if u and u not in urls:
            urls.append(u)
    return urls


def build_strategy_order(
    plan: PlanResult,
    instr: Optional[Dict[str, Any]],
    max_retries: int,
) -> List[str]:
    """Order retry strategies: instruction fallback_order wins when present."""
    defaults = ["single_page_extract", "subpage_discovery", "pagination_probe", "search_probe"]
    base = plan.strategy
    if instr and instr.get("fallback_order"):
        order = [str(s).strip() for s in instr["fallback_order"] if str(s).strip()]
        for d in defaults:
            if d not in order:
                order.append(d)
    else:
        order = [base] + [s for s in defaults if s != base]
    # Dedupe preserving order
    seen = set()
    out: List[str] = []
    for s in order:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out[: max_retries + 1]


def should_persist_instruction(validation: ValidationResult) -> bool:
    """Persist when validation marked good or clearly useful partial success."""
    if validation.is_good:
        return True
    if validation.record_count >= 3 and validation.valid_name_ratio >= 0.5:
        return True
    return False


def save_instruction_success(
    domain: str,
    input_url: str,
    plan: PlanResult,
    winning_strategy: str,
    validation: ValidationResult,
    run_id: str,
) -> str:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    path = instruction_path_for_domain(domain)
    existing = load_instruction(domain) or {}

    created = existing.get("created_at") or now
    doc: Dict[str, Any] = {
        "version": 1,
        "domain": domain,
        "created_at": created,
        "updated_at": now,
        "seed_urls": list(
            dict.fromkeys([input_url] + list(existing.get("seed_urls") or []))
        )[:20],
        "preferred_strategy": winning_strategy or plan.strategy,
        "fallback_order": existing.get("fallback_order")
        or [
            plan.strategy,
            "subpage_discovery",
            "pagination_probe",
            "search_probe",
        ],
        "subpage_hints": plan.subpage_hints[:30],
        "pagination_hints": plan.pagination_hints[:20],
        "quality_expectation_min_records": plan.quality_expectation_min_records,
        "last_success": {
            "run_id": run_id,
            "at": now,
            "input_url": input_url,
            "strategy": winning_strategy,
            "record_count": validation.record_count,
            "valid_name_ratio": round(validation.valid_name_ratio, 4),
            "duplicate_ratio": round(validation.duplicate_ratio, 4),
            "completeness_score": round(validation.completeness_score, 4),
        },
        "notes": existing.get("notes"),
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return str(path)
