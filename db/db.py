"""
Database layer — SQLite setup and core operations for the startup intelligence platform.

Why SQLite:
  Simple, zero-config, file-based. Sufficient for 10k–100k companies.
  Easy to inspect with any SQLite viewer or pandas. Upgrade to PostgreSQL
  later when concurrent writes or hosted deployment is needed.
"""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "startups.db"


def get_connection() -> sqlite3.Connection:
    """Open (or create) the database and return a connection with row_factory set."""
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # allows dict-like column access
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create the companies table if it doesn't already exist, and run migrations."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            description  TEXT,
            founded_year INTEGER,
            batch        TEXT,
            website      TEXT,
            uses_ai      INTEGER DEFAULT 0,     -- stored as 0/1 (SQLite has no boolean)
            tags         TEXT DEFAULT '[]',     -- JSON array stored as string
            industries   TEXT DEFAULT '[]',     -- JSON array stored as string
            location     TEXT,
            team_size    INTEGER,
            status       TEXT,
            stage        TEXT,
            source       TEXT NOT NULL,         -- e.g. 'yc', 'techstars'
            extra        TEXT DEFAULT '{}',     -- JSON object for source-specific bonus fields
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name, source)                -- prevent duplicate entries per source
        )
    """)
    # Migration: add extra column to existing tables that predate it
    try:
        conn.execute("ALTER TABLE companies ADD COLUMN extra TEXT DEFAULT '{}'")
    except Exception:
        pass  # column already exists — safe to ignore
    conn.commit()


def insert_company(conn: sqlite3.Connection, company: dict) -> None:
    """
    Insert a company record, or update it if name+source already exists (upsert).

    Tags and industries are serialized as JSON strings since SQLite has no array type.
    The updated_at timestamp is refreshed on every upsert.
    """
    conn.execute("""
        INSERT INTO companies
            (name, description, founded_year, batch, website, uses_ai,
             tags, industries, location, team_size, status, stage, source, extra)
        VALUES
            (:name, :description, :founded_year, :batch, :website, :uses_ai,
             :tags, :industries, :location, :team_size, :status, :stage, :source, :extra)
        ON CONFLICT(name, source) DO UPDATE SET
            description  = excluded.description,
            founded_year = excluded.founded_year,
            batch        = excluded.batch,
            website      = excluded.website,
            uses_ai      = excluded.uses_ai,
            tags         = excluded.tags,
            industries   = excluded.industries,
            location     = excluded.location,
            team_size    = excluded.team_size,
            status       = excluded.status,
            stage        = excluded.stage,
            extra        = excluded.extra,
            updated_at   = CURRENT_TIMESTAMP
    """, {
        **company,
        # Serialize lists to JSON strings
        "tags": json.dumps(company.get("tags") or []),
        "industries": json.dumps(company.get("industries") or []),
        # Normalize boolean to int for SQLite
        "uses_ai": 1 if company.get("uses_ai") else 0,
        # Serialize extra bonus fields dict
        "extra": json.dumps(company.get("extra") or {}),
    })


def bulk_upsert(conn: sqlite3.Connection, companies: list[dict]) -> int:
    """
    Insert or update a list of company dicts in one executemany call.
    Much faster than calling insert_company() in a loop for large datasets.

    Serializes tags/industries/extra to JSON and normalizes uses_ai to int.
    Returns the number of rows processed.
    """
    def prepare(company: dict) -> dict:
        return {
            **company,
            "tags": json.dumps(company.get("tags") or []),
            "industries": json.dumps(company.get("industries") or []),
            "uses_ai": 1 if company.get("uses_ai") else 0,
            "extra": json.dumps(company.get("extra") or {}),
        }

    rows = [prepare(c) for c in companies]

    conn.executemany("""
        INSERT INTO companies
            (name, description, founded_year, batch, website, uses_ai,
             tags, industries, location, team_size, status, stage, source, extra)
        VALUES
            (:name, :description, :founded_year, :batch, :website, :uses_ai,
             :tags, :industries, :location, :team_size, :status, :stage, :source, :extra)
        ON CONFLICT(name, source) DO UPDATE SET
            description  = excluded.description,
            founded_year = excluded.founded_year,
            batch        = excluded.batch,
            website      = excluded.website,
            uses_ai      = excluded.uses_ai,
            tags         = excluded.tags,
            industries   = excluded.industries,
            location     = excluded.location,
            team_size    = excluded.team_size,
            status       = excluded.status,
            stage        = excluded.stage,
            extra        = excluded.extra,
            updated_at   = CURRENT_TIMESTAMP
    """, rows)

    return len(rows)


def get_stats(conn: sqlite3.Connection) -> None:
    """Print total companies, breakdown by source, and AI usage counts."""
    total = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    ai_count = conn.execute("SELECT COUNT(*) FROM companies WHERE uses_ai = 1").fetchone()[0]

    print(f"\n--- Database Stats ---")
    print(f"  Total companies : {total:,}")
    print(f"  Uses AI         : {ai_count:,} ({ai_count / total * 100:.1f}%)" if total else "  No data.")

    print(f"\n  Breakdown by source:")
    rows = conn.execute("""
        SELECT source,
               COUNT(*) AS total,
               SUM(uses_ai) AS ai_count
        FROM companies
        GROUP BY source
        ORDER BY total DESC
    """).fetchall()

    for row in rows:
        pct = row["ai_count"] / row["total"] * 100 if row["total"] else 0
        print(f"    {row['source']:<15} {row['total']:>5,} companies  |  {row['ai_count']:>4,} AI ({pct:.1f}%)")
