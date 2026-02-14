"""
Database connection and session management
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from contextlib import contextmanager
from typing import Generator
from loguru import logger
import sys

from ..config import get_settings

# Configure logger
logger.remove()
logger.add(sys.stderr, level="INFO")

settings = get_settings()

# Base class for ORM models
Base = declarative_base()

# Create SQLAlchemy engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before using
    echo=settings.DEBUG,
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> bool:
    """Initialize database with schema and required extensions"""
    try:
        # 1) Test connection + enable pgvector extension FIRST
        #    (Vector type must exist before tables referencing it are created)
        with engine.begin() as conn:
            conn.execute(text("SELECT 1"))
            logger.info("Database connection successful")

            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            logger.info("pgvector extension enabled")

        # 2) Import models to register them with Base
        from . import models  # noqa: F401

        # 3) Create tables
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified")

        return True

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions

    Usage:
        with get_db_session() as session:
            session.query(...)
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database session error: {e}")
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI routes

    Usage:
        @app.get("/")
        def route(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
