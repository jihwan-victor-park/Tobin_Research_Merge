"""Tests for file-based scrape instruction YAML helpers."""
import pytest

from backend.agentic.instruction_yaml import (
    build_initial_fetch_urls,
    build_strategy_order,
    merge_plan_with_instruction,
    should_persist_instruction,
)
from backend.agentic.schemas import PlanResult, ValidationResult


def test_build_initial_fetch_urls_merges_instruction():
    instr = {"seed_urls": ["https://example.com/portfolio"]}
    urls = build_initial_fetch_urls("https://example.com/", instr)
    assert urls[0] == "https://example.com/"
    assert "https://example.com/portfolio" in urls


def test_merge_plan_prefers_instruction_strategy():
    plan = PlanResult(strategy="pagination_probe", subpage_hints=["/a"], quality_expectation_min_records=3)
    instr = {
        "preferred_strategy": "subpage_discovery",
        "subpage_hints": ["/portfolio"],
        "quality_expectation_min_records": 10,
    }
    merged = merge_plan_with_instruction(plan, instr)
    assert merged.strategy == "subpage_discovery"
    assert "/portfolio" in merged.subpage_hints
    assert merged.quality_expectation_min_records == 10


def test_build_strategy_order_respects_fallback_order():
    plan = PlanResult(strategy="pagination_probe")
    instr = {"fallback_order": ["search_probe", "single_page_extract"]}
    order = build_strategy_order(plan, instr, max_retries=3)
    assert order[0] == "search_probe"


def test_should_persist_instruction():
    good = ValidationResult(
        is_good=True,
        reason="ok",
        completeness_score=0.9,
        valid_name_ratio=0.9,
        duplicate_ratio=0.1,
        record_count=10,
    )
    assert should_persist_instruction(good) is True
    partial = ValidationResult(
        is_good=False,
        reason="ok",
        completeness_score=0.5,
        valid_name_ratio=0.6,
        duplicate_ratio=0.2,
        record_count=5,
    )
    assert should_persist_instruction(partial) is True
    bad = ValidationResult(
        is_good=False,
        reason="bad",
        completeness_score=0.1,
        valid_name_ratio=0.2,
        duplicate_ratio=0.9,
        record_count=1,
    )
    assert should_persist_instruction(bad) is False
