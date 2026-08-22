"""Shared DB connection + helpers for the paper's analysis scripts.

Run every script through the Railway env so DATABASE_PUBLIC_URL is present:
    railway run -s Postgres -- .venv/bin/python analysis/<script>.py
"""
import os, sys, time
import pandas as pd
import warnings
import psycopg2

warnings.filterwarnings("ignore", message=".*only supports SQLAlchemy.*")

RESULTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
os.makedirs(RESULTS, exist_ok=True)


def url() -> str:
    u = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("RAILWAY_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not u:
        sys.exit("No DATABASE_PUBLIC_URL — run under: railway run -s Postgres -- ...")
    return u


def connect(retries: int = 6):
    """Railway's TCP proxy drops connections; every call needs a retry loop."""
    last = None
    for i in range(retries):
        try:
            return psycopg2.connect(url(), connect_timeout=45, keepalives=1,
                                    keepalives_idle=30, keepalives_interval=10, keepalives_count=5)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise SystemExit(f"could not connect after {retries} tries: {last}")


def q(sql: str, params=None) -> pd.DataFrame:
    """Query with retries — the Railway TCP proxy drops connections mid-query."""
    for attempt in range(4):
        try:
            with connect() as c:
                return pd.read_sql(sql, c, params=params)
        except Exception:  # noqa: BLE001
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))


def save(df: pd.DataFrame, name: str) -> pd.DataFrame:
    path = os.path.join(RESULTS, name)
    df.to_csv(path, index=False)
    print(f"  -> results/{name}  ({len(df)} rows)")
    return df


# The project's AI filter, kept identical to backend/utils/ai_filter.py so the
# paper and the pipeline cannot drift apart.
AI_SQL = "(c.cb_ai_tagged = TRUE OR c.ai_score >= 0.5 OR c.llm_ai_verified = TRUE)"

# Coverage buckets. verification_status records which commercial databases
# matched the firm at import time.
BUCKET_SQL = """
CASE
  WHEN c.verification_status = 'verified_cb_pb' THEN 'both'
  WHEN c.verification_status = 'verified_cb'    THEN 'cb'
  WHEN c.verification_status = 'verified_pb'    THEN 'pb'
  ELSE 'unlisted'
END
"""
