"""
Configuration management for AI Startup Tracker
"""
from pydantic_settings import BaseSettings
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Database
    DATABASE_URL: str
    POSTGRES_USER: str = "ai_tracker"
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str = "ai_startup_tracker"

    # API Keys
    GROQ_API_KEY: str
    GITHUB_TOKEN: Optional[str] = None
    SERPAPI_API_KEY: Optional[str] = None
    FIRECRAWL_API_KEY: Optional[str] = None

    # Scraping Configuration
    SCRAPING_ENABLED: bool = True
    SCRAPING_SCHEDULE_DAY: str = "monday"
    SCRAPING_SCHEDULE_TIME: str = "09:00"
    MAX_SCRAPED_ITEMS_PER_RUN: int = 500

    # AI Configuration
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"  # Local sentence-transformers model
    LLM_MODEL: str = "llama-3.3-70b-versatile"  # Groq model
    EMBEDDING_DIMENSION: int = 384  # Dimension for all-MiniLM-L6-v2
    SIMILARITY_THRESHOLD: float = 0.75
    LLM_CONFIDENCE_THRESHOLD: float = 0.70

    # Application Settings
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
