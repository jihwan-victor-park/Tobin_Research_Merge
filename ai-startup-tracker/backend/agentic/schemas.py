from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ScrapedCompany(BaseModel):
    name: str
    description: Optional[str] = None
    website_url: Optional[str] = None
    profile_url: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    is_ai_startup: Optional[bool] = None
    ai_category: Optional[str] = None
    program: Optional[str] = None
    batch: Optional[str] = None
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    source_url: Optional[str] = None


class PlanResult(BaseModel):
    data_available: List[str] = Field(default_factory=list)
    strategy: str = "single_page_extract"
    subpage_hints: List[str] = Field(default_factory=list)
    pagination_hints: List[str] = Field(default_factory=list)
    quality_expectation_min_records: int = 5


class ValidationResult(BaseModel):
    is_good: bool
    reason: str
    completeness_score: float = Field(ge=0.0, le=1.0)
    valid_name_ratio: float = Field(ge=0.0, le=1.0)
    duplicate_ratio: float = Field(ge=0.0, le=1.0)
    record_count: int = 0


class RetryAttempt(BaseModel):
    attempt: int
    strategy: str
    fetched_urls: List[str] = Field(default_factory=list)
    validation: ValidationResult


class AgenticRunReport(BaseModel):
    run_id: str
    input_url: str
    started_at: datetime
    finished_at: datetime
    plan: PlanResult
    attempts: List[RetryAttempt]
    final_validation: ValidationResult
    total_records_before_clean: int
    total_records_after_clean: int
    saved_to_db: bool
    db_new_companies: int = 0
    db_updated_companies: int = 0
    # Phase 2: file-based scrape instructions (YAML per domain)
    site_domain: Optional[str] = None
    instruction_loaded: bool = False
    instruction_path: Optional[str] = None
    instruction_saved: bool = False
    instruction_saved_path: Optional[str] = None
    # Preview rows for UI (post-dedup cleaned records)
    extracted_preview: List[Dict[str, Any]] = Field(default_factory=list)
