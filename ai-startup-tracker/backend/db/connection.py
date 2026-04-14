"""
Database connection management for the pipeline.
Reads DATABASE_URL from environment / .env file.
"""
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from dotenv import load_dotenv

load_dotenv()

_engine = None
_SessionLocal = None


def get_engine():
    """Get or create the SQLAlchemy engine (singleton)."""
    global _engine
    if _engine is None:
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://localhost:5432/ai_startup_tracker",
        )
        _engine = create_engine(
            database_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            echo=False,
        )
    return _engine


def get_session_factory():
    """Get or create the session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


def get_session() -> Session:
    """Create a new database session."""
    factory = get_session_factory()
    return factory()


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """Create all tables if they don't exist, and apply column migrations."""
    from .models import Base
    from sqlalchemy import text

    engine = get_engine()
    Base.metadata.create_all(engine, checkfirst=True)

    # Apply column migrations for existing tables
    migrations = [
        (
            "companies", "incubator_source",
            "ALTER TABLE companies ADD COLUMN incubator_source VARCHAR "
            "CHECK (incubator_source IN ('capital_factory', 'gener8tor', 'village_global'))"
        ),
        ("companies", "description", "ALTER TABLE companies ADD COLUMN description TEXT"),
        ("companies", "founded_year", "ALTER TABLE companies ADD COLUMN founded_year INTEGER"),
        ("companies", "team_size", "ALTER TABLE companies ADD COLUMN team_size INTEGER"),
        ("companies", "stage", "ALTER TABLE companies ADD COLUMN stage VARCHAR(64)"),
        ("companies", "operating_status", "ALTER TABLE companies ADD COLUMN operating_status VARCHAR(64)"),
    ]
    with engine.connect() as conn:
        for table, column, ddl in migrations:
            result = conn.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :column"
            ), {"table": table, "column": column})
            if result.fetchone() is None:
                conn.execute(text(ddl))
                print(f"  Added column {table}.{column}")
        conn.commit()

    print("Database tables created successfully.")
