"""
SQLAlchemy ORM Models for AI Startup Tracker
"""
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, TIMESTAMP,
    DECIMAL, Enum, ARRAY, JSON, Date, func, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from datetime import datetime
import enum

from .connection import Base


# Enums
class StartupStatus(str, enum.Enum):
    ACTIVE = "active"
    STEALTH = "stealth"
    ACQUIRED = "acquired"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class DataSource(str, enum.Enum):
    DOMAIN_REGISTRATION = "domain_registration"
    PRODUCT_HUNT = "product_hunt"
    YC = "yc"
    BETALIST = "betalist"
    HACKERNEWS = "hackernews"
    GITHUB = "github"
    LINKEDIN = "linkedin"


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class Startup(Base):
    """Main startup entity"""
    __tablename__ = "startups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    url = Column(String(512), unique=True, nullable=False, index=True)
    domain = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    status = Column(Enum(StartupStatus), default=StartupStatus.UNKNOWN)
    is_stealth = Column(Boolean, default=False)

    # Location
    country = Column(String(100), index=True)
    city = Column(String(100))
    region = Column(String(100))
    latitude = Column(DECIMAL(10, 8))
    longitude = Column(DECIMAL(11, 8))

    # Categorization
    industry_vertical = Column(String(100), index=True)
    primary_tags = Column(ARRAY(Text))
    trend_cluster = Column(String(100))

    # Founder info
    founder_names = Column(ARRAY(Text))
    founder_backgrounds = Column(Text)
    has_notable_founders = Column(Boolean, default=False)

    # Metadata
    discovered_date = Column(TIMESTAMP, default=datetime.utcnow, nullable=False, index=True)
    last_updated = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    source = Column(Enum(DataSource), nullable=False, index=True)
    source_url = Column(String(512))

    # AI Analysis
    relevance_score = Column(DECIMAL(3, 2))  # 0.00 to 1.00
    confidence_score = Column(DECIMAL(3, 2))  # 0.00 to 1.00
    emergence_score = Column(DECIMAL(5, 2))  # 0.00 to 100.00 (trend analysis score)
    review_status = Column(Enum(ReviewStatus), default=ReviewStatus.PENDING, index=True)

    # Additional metadata (for storing extra fields like original_source)
    extra_metadata = Column(JSONB)

    # Embedding (1536 dimensions for text-embedding-3-small)
    content_embedding = Column(Vector(384))

    # Full text content
    landing_page_text = Column(Text)
    extracted_keywords = Column(ARRAY(Text))

    def __repr__(self):
        return f"<Startup(id={self.id}, name='{self.name}', vertical='{self.industry_vertical}')>"

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'domain': self.domain,
            'description': self.description,
            'status': self.status.value if self.status else None,
            'is_stealth': self.is_stealth,
            'country': self.country,
            'city': self.city,
            'industry_vertical': self.industry_vertical,
            'primary_tags': self.primary_tags,
            'founder_names': self.founder_names,
            'discovered_date': self.discovered_date.isoformat() if self.discovered_date else None,
            'source': self.source.value if self.source else None,
            'relevance_score': float(self.relevance_score) if self.relevance_score else None,
            'confidence_score': float(self.confidence_score) if self.confidence_score else None,
            'emergence_score': float(self.emergence_score) if self.emergence_score else None,
            'extra_metadata': self.extra_metadata,
        }


class ScrapedURL(Base):
    """Tracking scraped URLs to avoid duplicates"""
    __tablename__ = "scraped_urls"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(512), unique=True, nullable=False, index=True)
    source = Column(Enum(DataSource), nullable=False, index=True)
    scraped_at = Column(TIMESTAMP, default=datetime.utcnow, index=True)
    status = Column(String(50), default="success")
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)

    def __repr__(self):
        return f"<ScrapedURL(url='{self.url}', source='{self.source}', status='{self.status}')>"


class ScrapingJob(Base):
    """Tracking scraping job executions"""
    __tablename__ = "scraping_jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_type = Column(String(50), nullable=False)
    started_at = Column(TIMESTAMP, default=datetime.utcnow, index=True)
    completed_at = Column(TIMESTAMP)
    status = Column(String(50), default="running", index=True)
    items_processed = Column(Integer, default=0)
    items_added = Column(Integer, default=0)
    error_message = Column(Text)
    job_metadata = Column("metadata", JSONB)


    def __repr__(self):
        return f"<ScrapingJob(id={self.id}, type='{self.job_type}', status='{self.status}')>"


class TrendCluster(Base):
    """AI-detected trend clusters"""
    __tablename__ = "trend_clusters"

    id = Column(Integer, primary_key=True, index=True)
    cluster_name = Column(String(255), unique=True, nullable=False)
    description = Column(Text)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    startup_count = Column(Integer, default=0)
    centroid_embedding = Column(Vector(384))
    keywords = Column(ARRAY(Text))
    is_emerging = Column(Boolean, default=True)

    def __repr__(self):
        return f"<TrendCluster(name='{self.cluster_name}', count={self.startup_count})>"


class WeeklyAnalytics(Base):
    """Weekly analytics snapshots"""
    __tablename__ = "weekly_analytics"

    id = Column(Integer, primary_key=True, index=True)
    week_start_date = Column(Date, nullable=False, unique=True)
    week_end_date = Column(Date, nullable=False)
    total_new_startups = Column(Integer, default=0)
    total_stealth_startups = Column(Integer, default=0)
    top_vertical = Column(String(100))
    top_region = Column(String(100))
    emerging_trends = Column(ARRAY(Text))
    analytics_metadata = Column("metadata", JSONB)


    def __repr__(self):
        return f"<WeeklyAnalytics(week={self.week_start_date}, new_startups={self.total_new_startups})>"


# Create indexes programmatically (for complex indexes)
Index('idx_startups_embedding_cosine', Startup.content_embedding, postgresql_using='hnsw', postgresql_ops={'content_embedding': 'vector_cosine_ops'})
