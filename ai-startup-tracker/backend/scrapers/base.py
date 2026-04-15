"""
BaseScraper — abstract base class for all scrapers (easy and hard tier).

Every scraper implements `scrape()` which returns a list of ScrapedCompany.
The `run()` template method handles: scrape -> validate -> dedup -> save.
"""
from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from collections import Counter
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from backend.agentic.schemas import ScrapedCompany, ValidationResult
from backend.db.connection import session_scope
from backend.db.models import (
    Company,
    IncubatorSignal,
    IncubatorSource,
    LocationSource,
    ScrapeRun,
    VerificationStatus,
)
from backend.utils.dedup import deduplicate_candidates
from backend.utils.domain import canonicalize_domain
from backend.utils.normalize import normalize_company_name

logger = logging.getLogger(__name__)

# ── AI keyword detection (consolidated from Alastair's duplicated lists) ──

AI_KEYWORDS = [
    "artificial intelligence", "machine learning", "large language model", "llm",
    "generative ai", "generative", "gpt", "neural network", "deep learning", "nlp",
    "natural language processing", "computer vision", "data science", "autonomous",
    "robotics", "predictive", "recommendation engine", "ai", "transformer",
    "diffusion", "reinforcement learning", "rag", "retrieval augmented",
    "foundation model", "fine-tuning", "embeddings",
]
_AI_PATTERNS = [re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE) for kw in AI_KEYWORDS]


class BaseScraper(ABC):
    """Abstract base class for all scrapers."""

    name: str = "base"          # e.g. "yc", "techstars"
    domain: str = ""            # e.g. "ycombinator.com"
    difficulty: str = "easy"    # "easy" or "hard"
    source_url: str = ""        # primary URL to scrape

    @abstractmethod
    def scrape(self) -> List[ScrapedCompany]:
        """Fetch and parse companies. Returns Pydantic models, NO DB writes."""
        ...

    def detect_ai(self, text: str) -> bool:
        """Check if text contains AI-related keywords (word-boundary regex)."""
        if not text:
            return False
        return any(p.search(text) for p in _AI_PATTERNS)

    def run(self, save_to_db: bool = True) -> ScrapeRunResult:
        """Template method: scrape -> validate -> dedup -> save -> log."""
        started_at = datetime.now(timezone.utc)
        status = "success"
        error_message = None
        records_found = 0
        records_new = 0
        records_updated = 0

        try:
            # 1. Scrape
            raw_records = self.scrape()
            records_found = len(raw_records)
            logger.info(f"[{self.name}] Scraped {records_found} raw records")

            if not raw_records:
                status = "zero_result"
                return ScrapeRunResult(
                    scraper_name=self.name, domain=self.domain, status=status,
                    records_found=0, records_new=0, records_updated=0,
                    started_at=started_at, finished_at=datetime.now(timezone.utc),
                )

            # 2. Validate
            validation = validate_records(raw_records)
            if not validation.is_good:
                logger.warning(f"[{self.name}] Validation failed: {validation.reason}")
                status = "zero_result" if validation.record_count == 0 else "error"
                error_message = f"Validation: {validation.reason}"

            # 3. Postprocess + dedup
            cleaned = postprocess_records(raw_records)
            logger.info(f"[{self.name}] {len(raw_records)} raw -> {len(cleaned)} after dedup")

            # 4. Save to DB
            if save_to_db and cleaned:
                records_new, records_updated = save_companies_to_db(
                    cleaned, source_url=self.source_url
                )
                logger.info(f"[{self.name}] DB: {records_new} new, {records_updated} updated")

        except Exception as e:
            status = "error"
            error_message = str(e)
            logger.error(f"[{self.name}] Error: {e}", exc_info=True)

        finished_at = datetime.now(timezone.utc)

        # 5. Log scrape run
        if save_to_db:
            _log_scrape_run(
                domain=self.domain,
                url=self.source_url,
                difficulty=self.difficulty,
                scraper_name=self.name,
                status=status,
                error_message=error_message,
                records_found=records_found,
                records_new=records_new,
                records_updated=records_updated,
                duration_seconds=(finished_at - started_at).total_seconds(),
                started_at=started_at,
                finished_at=finished_at,
            )

        return ScrapeRunResult(
            scraper_name=self.name,
            domain=self.domain,
            status=status,
            error_message=error_message,
            records_found=records_found,
            records_new=records_new,
            records_updated=records_updated,
            started_at=started_at,
            finished_at=finished_at,
        )


class ScrapeRunResult:
    """Simple result object returned by BaseScraper.run()."""

    def __init__(
        self,
        scraper_name: str,
        domain: str,
        status: str,
        records_found: int = 0,
        records_new: int = 0,
        records_updated: int = 0,
        error_message: Optional[str] = None,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
    ):
        self.scraper_name = scraper_name
        self.domain = domain
        self.status = status
        self.records_found = records_found
        self.records_new = records_new
        self.records_updated = records_updated
        self.error_message = error_message
        self.started_at = started_at
        self.finished_at = finished_at

    @property
    def success(self) -> bool:
        return self.status == "success"

    def __repr__(self):
        return (
            f"<ScrapeRunResult {self.scraper_name} status={self.status} "
            f"found={self.records_found} new={self.records_new}>"
        )


# ── Shared functions (extracted from engine.py to avoid duplication) ──────


def validate_records(
    records: List[ScrapedCompany], min_records: int = 1
) -> ValidationResult:
    """Simple rule-based validation — no LLM call."""
    if not records:
        return ValidationResult(
            is_good=False, reason="No records extracted",
            completeness_score=0.0, valid_name_ratio=0.0,
            duplicate_ratio=0.0, record_count=0,
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


def postprocess_records(records: List[ScrapedCompany]) -> List[dict]:
    """Normalize + deduplicate scraped records."""
    candidates = []
    for r in records:
        domain = canonicalize_domain(r.website_url or "")
        candidates.append({
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
        })

    # Deduplicate
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


def save_companies_to_db(
    records: List[dict], source_url: str = ""
) -> Tuple[int, int]:
    """Save to Company table + IncubatorSignal. Returns (new_count, updated_count)."""
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
                    description=r.get("description"),
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
                if not company.description and r.get("description"):
                    company.description = r.get("description")
                updated_count += 1

            # Update location if extracted
            country = r.get("country")
            city = r.get("city")
            if country and not company.country:
                company.country = country
                company.city = city

            # Update AI score
            if r.get("is_ai_startup") and (company.ai_score is None or company.ai_score < 0.6):
                company.ai_score = 0.7

            session.flush()

            # Create IncubatorSignal if applicable
            has_incubator_data = r.get("program") or r.get("batch")
            is_portfolio_url = any(
                kw in (source_url or "").lower()
                for kw in ["portfolio", "companies", "startups", "alumni", "cohort", "batch"]
            )
            if has_incubator_data or is_portfolio_url:
                existing = (
                    session.query(IncubatorSignal)
                    .filter(IncubatorSignal.company_name_raw == name)
                    .first()
                )
                if not existing:
                    industry = r.get("industry")
                    if industry and len(industry) > 255:
                        industry = industry[:255]
                    signal = IncubatorSignal(
                        company_id=company.id,
                        source=IncubatorSource.agentic_scrape,
                        company_name_raw=name,
                        website_url=r.get("website_url"),
                        industry=industry,
                        batch=r.get("batch"),
                        program=r.get("program"),
                        description=r.get("description"),
                        profile_url=r.get("profile_url"),
                        collected_at=now,
                    )
                    session.add(signal)

    return new_count, updated_count


def _log_scrape_run(**kwargs):
    """Insert a ScrapeRun audit record."""
    try:
        with session_scope() as session:
            run = ScrapeRun(**kwargs)
            session.add(run)
    except Exception as e:
        logger.error(f"Failed to log scrape run: {e}")
