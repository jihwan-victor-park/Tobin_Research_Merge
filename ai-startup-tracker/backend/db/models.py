"""
SQLAlchemy ORM models for the GitHub-first AI startup tracker.

Tables:
  - companies: Core entity table
  - github_signals: Repository-level data linked to companies
  - github_repo_snapshots: Time-series repo metrics per collection run
  - funding_signals: Deal/round data from PitchBook
  - incubator_signals: Portfolio data from accelerators/incubators
  - source_matches: Audit trail for entity matching across sources
  - scrape_runs: Audit trail for every scrape execution
  - site_health: Per-domain health tracking for self-healing
"""
import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime,
    ForeignKey, Enum, UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# ── Enums ──────────────────────────────────────────────────────────────

class LocationSource(str, enum.Enum):
    crunchbase = "crunchbase"
    pitchbook = "pitchbook"
    github = "github"
    unknown = "unknown"


class VerificationStatus(str, enum.Enum):
    emerging_github = "emerging_github"
    verified_cb = "verified_cb"
    verified_pb = "verified_pb"
    verified_cb_pb = "verified_cb_pb"


class MatchMethod(str, enum.Enum):
    domain = "domain"
    name_strict = "name_strict"
    manual = "manual"


class IncubatorSource(str, enum.Enum):
    capital_factory = "capital_factory"
    gener8tor = "gener8tor"
    village_global = "village_global"
    # New sources — if DB already exists, run:
    #   ALTER TYPE incubator_source_enum ADD VALUE '<value>';
    founder_institute = "founder_institute"
    seedcamp = "seedcamp"
    beenext = "beenext"
    antler = "antler"
    entrepreneur_first = "entrepreneur_first"
    pioneer_fund = "pioneer_fund"
    dreamit = "dreamit"
    # University Incubators
    berkeley_skydeck = "berkeley_skydeck"
    mit_engine = "mit_engine"
    stanford_startx = "stanford_startx"
    uiuc_enterpriseworks = "uiuc_enterpriseworks"
    cmu_swartz = "cmu_swartz"
    harvard_ilabs = "harvard_ilabs"
    georgia_tech_atdc = "georgia_tech_atdc"
    michigan_zell_lurie = "michigan_zell_lurie"
    # Major Accelerators
    techstars = "techstars"
    five_hundred_global = "five_hundred_global"
    alchemist = "alchemist"
    sosv = "sosv"
    plug_and_play = "plug_and_play"
    masschallenge = "masschallenge"
    lux_capital = "lux_capital"
    # Trend / Discovery
    betalist = "betalist"
    wellfound = "wellfound"
    f6s = "f6s"
    hn_who_is_hiring = "hn_who_is_hiring"
    techcrunch_battlefield = "techcrunch_battlefield"
    # International Incubators (from international_incubators.csv)
    era_nyc = "era_nyc"
    startup_chile = "startup_chile"
    flat6labs = "flat6labs"
    ventures_platform = "ventures_platform"
    hax = "hax"
    surge = "surge"
    brinc = "brinc"
    sparklabs = "sparklabs"
    parallel18 = "parallel18"
    wayra = "wayra"
    nxtp_ventures = "nxtp_ventures"
    allvp = "allvp"
    astrolabs = "astrolabs"
    grindstone = "grindstone"
    seedstars = "seedstars"
    station_f = "station_f"
    startupbootcamp = "startupbootcamp"
    h_farm = "h_farm"
    sting_stockholm = "sting_stockholm"
    rockstart = "rockstart"
    # Agentic scraper (auto-detected)
    agentic_scrape = "agentic_scrape"


# ── Companies ──────────────────────────────────────────────────────────

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(512), nullable=False)
    domain = Column(String(512), nullable=True, unique=True)
    normalized_name = Column(String(512), nullable=True, index=True)

    # Location
    country = Column(String(200), nullable=True)
    city = Column(String(200), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_source = Column(
        Enum(LocationSource, name="location_source_enum", create_type=True),
        nullable=True, default=LocationSource.unknown,
    )

    # Verification
    verification_status = Column(
        Enum(VerificationStatus, name="verification_status_enum", create_type=True),
        nullable=False, default=VerificationStatus.emerging_github,
    )

    # Company details (merged from Alastair branch schema)
    description = Column(Text, nullable=True)
    founded_year = Column(Integer, nullable=True)
    team_size = Column(Integer, nullable=True)
    stage = Column(String(64), nullable=True)  # pre-seed, seed, series_a, etc.
    operating_status = Column(String(64), nullable=True)  # operating, acquired, closed

    # Scores
    ai_score = Column(Float, nullable=True)
    startup_score = Column(Float, nullable=True)
    ai_tags = Column(ARRAY(Text), nullable=True)

    # Timestamps
    first_seen_at = Column(DateTime, nullable=True, default=datetime.utcnow)
    last_seen_at = Column(DateTime, nullable=True, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Incubator affiliation (NULL if not from any incubator)
    incubator_source = Column(
        Enum(IncubatorSource, name="incubator_source_enum", create_type=True),
        nullable=True,
    )

    # Relationships
    github_signals = relationship("GithubSignal", back_populates="company", cascade="all, delete-orphan")
    funding_signals = relationship("FundingSignal", back_populates="company", cascade="all, delete-orphan")
    incubator_signals = relationship("IncubatorSignal", back_populates="company", cascade="all, delete-orphan")
    source_matches = relationship("SourceMatch", back_populates="company", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_companies_domain", "domain", unique=True, postgresql_where=Column("domain").isnot(None)),
        Index("ix_companies_verification", "verification_status"),
        Index("ix_companies_ai_score", "ai_score"),
        Index("ix_companies_startup_score", "startup_score"),
    )

    def __repr__(self):
        return f"<Company id={self.id} name={self.name!r} domain={self.domain!r}>"


# ── GitHub Signals ─────────────────────────────────────────────────────

class GithubSignal(Base):
    __tablename__ = "github_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    repo_full_name = Column(String(512), nullable=False, unique=True)
    repo_url = Column(String(1024), nullable=True)
    owner_login = Column(String(256), nullable=True)
    owner_type = Column(String(64), nullable=True)  # "User" or "Organization"
    description = Column(Text, nullable=True)
    topics = Column(ARRAY(Text), nullable=True)
    homepage_url = Column(String(1024), nullable=True)

    created_at = Column(DateTime, nullable=True)  # repo created_at
    pushed_at = Column(DateTime, nullable=True)
    stars = Column(Integer, nullable=True, default=0)
    forks = Column(Integer, nullable=True, default=0)

    readme_snippet = Column(Text, nullable=True)
    collected_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    company = relationship("Company", back_populates="github_signals")

    __table_args__ = (
        Index("ix_github_signals_company", "company_id"),
        Index("ix_github_signals_owner", "owner_login"),
        Index("ix_github_signals_stars", "stars"),
    )

    def __repr__(self):
        return f"<GithubSignal repo={self.repo_full_name!r} stars={self.stars}>"


# ── GitHub Repo Snapshots (time-series metrics) ───────────────────────

class GithubRepoSnapshot(Base):
    """Point-in-time snapshot of a repo's metrics for trend analysis."""
    __tablename__ = "github_repo_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_full_name = Column(String(512), nullable=False, index=True)
    collected_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Core metrics from GitHub search API
    stars = Column(Integer, nullable=True, default=0)
    forks = Column(Integer, nullable=True, default=0)
    open_issues = Column(Integer, nullable=True, default=0)
    watchers = Column(Integer, nullable=True, default=0)
    size_kb = Column(Integer, nullable=True, default=0)

    # Repo metadata
    pushed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True)
    language = Column(String(128), nullable=True)
    license = Column(String(128), nullable=True)
    owner_login = Column(String(256), nullable=True)
    owner_type = Column(String(64), nullable=True)
    default_branch = Column(String(128), nullable=True)
    topics = Column(ARRAY(Text), nullable=True)
    description = Column(Text, nullable=True)
    homepage_url = Column(String(1024), nullable=True)

    # Classification (filled by classify_repo)
    ai_subdomain = Column(String(64), nullable=True)
    stack_layer = Column(String(64), nullable=True)

    # Derived scores
    startup_likelihood = Column(Float, nullable=True)
    trend_score = Column(Float, nullable=True)

    # LLM classification
    llm_classification = Column(String(32), nullable=True)  # startup, personal_project, research, community_tool
    llm_confidence = Column(Float, nullable=True)
    llm_reason = Column(Text, nullable=True)

    # Velocity deltas (computed from prior snapshot)
    stars_7d_delta = Column(Integer, nullable=True)
    forks_7d_delta = Column(Integer, nullable=True)
    issues_7d_delta = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("repo_full_name", "collected_at", name="uq_snapshot_repo_time"),
        Index("ix_snapshots_repo", "repo_full_name"),
        Index("ix_snapshots_collected", "collected_at"),
        Index("ix_snapshots_trend", "trend_score"),
        Index("ix_snapshots_subdomain", "ai_subdomain"),
    )

    def __repr__(self):
        return f"<Snapshot repo={self.repo_full_name!r} stars={self.stars} trend={self.trend_score}>"


# ── Funding Signals ────────────────────────────────────────────────────

class FundingSignal(Base):
    __tablename__ = "funding_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    source = Column(String(64), nullable=False, default="pitchbook")
    deal_date = Column(DateTime, nullable=True)
    round_type = Column(String(128), nullable=True)
    deal_size = Column(Float, nullable=True)  # in USD
    investors = Column(ARRAY(Text), nullable=True)
    raw_metadata = Column(JSONB, nullable=True)
    collected_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    company = relationship("Company", back_populates="funding_signals")

    __table_args__ = (
        Index("ix_funding_signals_company", "company_id"),
        Index("ix_funding_signals_deal_date", "deal_date"),
    )

    def __repr__(self):
        return f"<FundingSignal company_id={self.company_id} round={self.round_type}>"


# ── Incubator Signals ──────────────────────────────────────────────────

class IncubatorSignal(Base):
    """Portfolio company data scraped from accelerator/incubator websites."""
    __tablename__ = "incubator_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    source = Column(
        Enum(IncubatorSource, name="incubator_source_enum", create_type=True),
        nullable=False,
    )
    company_name_raw = Column(String(512), nullable=False)  # name as scraped
    website_url = Column(String(1024), nullable=True)
    logo_url = Column(String(1024), nullable=True)
    industry = Column(String(256), nullable=True)
    batch = Column(String(128), nullable=True)  # e.g. "Batch 20", "Fall 2024"
    program = Column(String(128), nullable=True)  # e.g. "Cohort", "Europe Cohort"
    description = Column(Text, nullable=True)
    profile_url = Column(String(1024), nullable=True)  # link to incubator profile page
    collected_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    company = relationship("Company", back_populates="incubator_signals")

    __table_args__ = (
        UniqueConstraint("source", "company_name_raw", name="uq_incubator_source_name"),
        Index("ix_incubator_signals_company", "company_id"),
        Index("ix_incubator_signals_source", "source"),
    )

    def __repr__(self):
        return f"<IncubatorSignal source={self.source} name={self.company_name_raw!r}>"


# ── Source Matches (audit trail) ───────────────────────────────────────

class SourceMatch(Base):
    __tablename__ = "source_matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    crunchbase_id = Column(String(256), nullable=True)
    pitchbook_id = Column(String(256), nullable=True)
    match_method = Column(
        Enum(MatchMethod, name="match_method_enum", create_type=True),
        nullable=False,
    )
    match_confidence = Column(Float, nullable=True)  # 0.0–1.0
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    company = relationship("Company", back_populates="source_matches")

    __table_args__ = (
        Index("ix_source_matches_company", "company_id"),
        Index("ix_source_matches_cb", "crunchbase_id"),
        Index("ix_source_matches_pb", "pitchbook_id"),
    )

    def __repr__(self):
        return f"<SourceMatch company_id={self.company_id} method={self.match_method}>"


# ── Scrape Runs (audit trail for every scrape) ───────────────────────

class ScrapeRun(Base):
    """Audit trail for every scrape execution — easy or hard tier."""
    __tablename__ = "scrape_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain = Column(String(512), nullable=False)
    url = Column(String(1024), nullable=False)
    difficulty = Column(String(16), nullable=False)  # "easy" or "hard"
    scraper_name = Column(String(128), nullable=False)  # e.g. "yc_scraper", "agentic_engine"
    status = Column(String(32), nullable=False)  # success, zero_result, error, escalated
    error_message = Column(Text, nullable=True)
    records_found = Column(Integer, default=0)
    records_new = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    duration_seconds = Column(Float, nullable=True)
    escalated_from = Column(String(16), nullable=True)  # "easy" if auto-escalated to hard
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_scrape_runs_domain", "domain"),
        Index("ix_scrape_runs_status", "status"),
        Index("ix_scrape_runs_started_at", "started_at"),
    )

    def __repr__(self):
        return f"<ScrapeRun domain={self.domain!r} status={self.status} records={self.records_found}>"


# ── Site Health (per-domain health tracking for self-healing) ────────

class SiteHealth(Base):
    """Per-domain health tracking for the self-healing scraper system."""
    __tablename__ = "site_health"

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain = Column(String(512), nullable=False)
    url = Column(String(1024), nullable=True)  # primary seed URL
    difficulty = Column(String(16), nullable=False, default="hard")  # easy, hard, excluded
    scraper_name = Column(String(128), nullable=True)  # registered easy scraper class name
    status = Column(String(32), nullable=False, default="pending")  # healthy, degraded, broken, excluded, pending
    consecutive_failures = Column(Integer, default=0)
    last_success_at = Column(DateTime, nullable=True)
    last_failure_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    last_record_count = Column(Integer, nullable=True)
    next_scrape_at = Column(DateTime, nullable=True)
    exclude_until = Column(DateTime, nullable=True)  # 3-month revisit date
    exclude_reason = Column(Text, nullable=True)
    total_runs = Column(Integer, default=0)
    total_successes = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("domain", name="uq_site_health_domain"),
        Index("ix_site_health_status", "status"),
        Index("ix_site_health_difficulty", "difficulty"),
        Index("ix_site_health_next_scrape", "next_scrape_at"),
    )

    def __repr__(self):
        return f"<SiteHealth domain={self.domain!r} status={self.status} difficulty={self.difficulty}>"
