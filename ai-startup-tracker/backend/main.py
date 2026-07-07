"""
FastAPI backend for the Startup Intelligence Platform.

Endpoints:
  GET  /api/stats                   — aggregate stats + per-source breakdown
  GET  /api/companies               — paginated, filterable company list
  GET  /api/stats/founding-years    — companies founded per year
  GET  /api/stats/locations         — AI-flagged companies by country
  GET  /api/stats/score-distribution — ai_score histogram (10 buckets)
  POST /api/scout                   — submit URL for scout agent (async)
  GET  /api/scout/{job_id}          — poll scout job status
"""
import asyncio
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, text, or_
from sqlalchemy.orm import sessionmaker

from backend.db.models import Company, IncubatorSignal

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://localhost/ai_startup_tracker"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

app = FastAPI(title="Startup Intelligence API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


from backend.utils.country import normalize_country as _normalize_country, GLOBE_COUNTRIES


# ── /api/stats ────────────────────────────────────────────────────────────────

@app.get("/api/stats")
def get_stats():
    db = SessionLocal()
    try:
        total = db.query(Company).count()
        ai_flagged = db.query(Company).filter(Company.ai_score >= 0.6).count()
        with_domain = (
            db.query(Company)
            .filter(Company.domain.isnot(None), Company.domain != "")
            .count()
        )

        # Per-source breakdown via incubator_signals (source of truth for source tags)
        rows = db.execute(
            text("""
                SELECT
                    s.source::text AS source,
                    COUNT(DISTINCT s.company_id) AS total,
                    COUNT(DISTINCT s.company_id) FILTER (
                        WHERE c.ai_score >= 0.6
                    ) AS ai_flagged
                FROM incubator_signals s
                JOIN companies c ON c.id = s.company_id
                GROUP BY s.source
                ORDER BY total DESC
            """)
        ).fetchall()

        sources = [
            {
                "source": r.source,
                "total": r.total,
                "ai_flagged": r.ai_flagged,
                "ai_pct": round(r.ai_flagged / r.total * 100, 1) if r.total else 0,
            }
            for r in rows
        ]

        raw_country_rows = db.execute(text("""
            SELECT DISTINCT country FROM companies
            WHERE country IS NOT NULL AND country != ''
              AND country NOT ILIKE '%remote%'
        """)).fetchall()
        country_count = sum(
            1 for r in raw_country_rows
            if _normalize_country(r.country) in GLOBE_COUNTRIES
        )

        return {
            "total_companies": total,
            "ai_flagged": ai_flagged,
            "ai_pct": round(ai_flagged / total * 100, 1) if total else 0,
            "with_domain": with_domain,
            "countries": country_count,
            "sources": sources,
        }
    finally:
        db.close()


# ── /api/companies ────────────────────────────────────────────────────────────

@app.get("/api/companies")
def get_companies(
    search: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    ai_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    db = SessionLocal()
    try:
        q = db.query(Company)

        if search:
            term = f"%{search}%"
            q = q.filter(
                or_(
                    Company.name.ilike(term),
                    Company.description.ilike(term),
                )
            )

        if source:
            # Filter via incubator_signals join — cast to text to avoid enum type mismatch
            q = q.join(IncubatorSignal, IncubatorSignal.company_id == Company.id).filter(
                text("incubator_signals.source::text = :src")
            ).params(src=source).distinct()

        if ai_only:
            q = q.filter(Company.ai_score >= 0.6)

        total = q.count()

        companies = (
            q.order_by(Company.ai_score.desc().nullslast(), Company.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        # Fetch primary source for each company
        company_ids = [c.id for c in companies]
        source_map = {}
        if company_ids:
            sig_rows = db.execute(
                text("""
                    SELECT DISTINCT ON (company_id) company_id, source::text
                    FROM incubator_signals
                    WHERE company_id = ANY(:ids)
                    ORDER BY company_id, source
                """),
                {"ids": company_ids},
            ).fetchall()
            source_map = {r.company_id: r.source for r in sig_rows}

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
            "companies": [
                {
                    "id": c.id,
                    "name": c.name,
                    "description": c.description,
                    "source": source_map.get(c.id),
                    "domain": c.domain,
                    "ai_score": c.ai_score,
                    "uses_ai": (c.ai_score >= 0.6) if c.ai_score is not None else False,
                    "founded_year": c.founded_year,
                    "city": c.city,
                    "country": c.country,
                }
                for c in companies
            ],
        }
    finally:
        db.close()


# ── /api/stats/founding-years ─────────────────────────────────────────────────

@app.get("/api/stats/founding-years")
def get_founding_years():
    db = SessionLocal()
    try:
        rows = db.execute(
            text("""
                SELECT founded_year, COUNT(*) AS count
                FROM companies
                GROUP BY founded_year
                ORDER BY founded_year ASC NULLS LAST
            """)
        ).fetchall()

        result = []
        for r in rows:
            result.append({
                "year": r.founded_year,  # None becomes null in JSON → rendered as "Unknown"
                "count": r.count,
            })
        return result
    finally:
        db.close()


# ── /api/stats/locations ──────────────────────────────────────────────────────

@app.get("/api/stats/locations")
def get_locations():
    # country column exists in the schema — returns AI-flagged companies grouped by country
    db = SessionLocal()
    try:
        rows = db.execute(
            text("""
                SELECT country, COUNT(*) AS count
                FROM companies
                WHERE ai_score >= 0.1
                  AND country IS NOT NULL AND country != ''
                  AND country NOT ILIKE '%remote%'
                GROUP BY country
                ORDER BY count DESC
            """)
        ).fetchall()

        # Normalize and re-aggregate
        agg: dict[str, int] = {}
        for r in rows:
            norm = _normalize_country(r.country)
            if norm:
                agg[norm] = agg.get(norm, 0) + r.count

        return [
            {"country": k, "count": v}
            for k, v in sorted(agg.items(), key=lambda x: -x[1])
        ]
    finally:
        db.close()


# ── /api/stats/score-distribution ────────────────────────────────────────────

@app.get("/api/stats/score-distribution")
def get_score_distribution():
    db = SessionLocal()
    try:
        rows = db.execute(
            text("""
                SELECT
                    FLOOR(ai_score * 10) / 10 AS bucket_start,
                    COUNT(*) AS count
                FROM companies
                WHERE ai_score IS NOT NULL
                GROUP BY bucket_start
                ORDER BY bucket_start
            """)
        ).fetchall()

        # Fill all 10 buckets (0.0 through 0.9) even if empty
        bucket_map = {float(r.bucket_start): r.count for r in rows}
        result = []
        for i in range(10):
            lo = round(i * 0.1, 1)
            hi = round(lo + 0.1, 1)
            # Clamp 1.0 scores into the last bucket
            count = bucket_map.get(lo, 0)
            if lo == 0.9:
                count += bucket_map.get(1.0, 0)
            result.append({"bucket": f"{lo:.1f}–{hi:.1f}", "count": count})
        return result
    finally:
        db.close()


# ── Scout agent job queue ─────────────────────────────────────────────────────

# agent/ lives at ai_startup_scraper/ — two levels up from ai-startup-tracker/backend/
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

class JobStatus:
    def __init__(self, job_id: str, url: str):
        self.job_id = job_id
        self.url = url
        self.status = "pending"          # pending | running | complete | error
        self.submitted_at = datetime.now(timezone.utc).isoformat()
        self.result = None
        self.error = None

    def to_dict(self):
        return {
            "job_id": self.job_id,
            "status": self.status,
            "url": self.url,
            "submitted_at": self.submitted_at,
            "result": self.result,
            "error": self.error,
        }


# In-memory job store — fine for local/dev use
jobs: dict[str, JobStatus] = {}


async def _run_scout_job(job: JobStatus) -> None:
    """Run the scout agent in a thread so it doesn't block the event loop."""
    job.status = "running"
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "agent/agent.py", job.url, "scout"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=300,  # 5-minute hard cap
        )

        if proc.returncode != 0:
            job.status = "error"
            job.error = proc.stderr.strip() or f"Process exited with code {proc.returncode}"
            return

        stdout = proc.stdout.strip()
        if not stdout:
            job.status = "error"
            job.error = "Agent produced no output"
            return

        import json
        try:
            raw = json.loads(stdout)
        except json.JSONDecodeError:
            # stdout has progress lines mixed in — grab the last JSON object
            import re
            matches = re.findall(r'(\{[\s\S]*\})', stdout)
            if matches:
                raw = json.loads(matches[-1])
            else:
                job.status = "error"
                job.error = f"Could not parse agent output: {stdout[:300]}"
                return

        # Shape the result for the frontend
        structured = raw.get("structured_result") or {}
        tool_log = raw.get("tool_call_log", [])
        job.result = {
            "summary": raw.get("raw_response", ""),
            "tool_calls": [
                {
                    "tool": t.get("tool_name", t.get("tool", "?")),
                    "input_summary": str(t.get("input", t.get("url", "")))[:120],
                }
                for t in tool_log
            ],
            "instruction_draft": structured,
            "tool_calls_used": raw.get("tool_calls_used", len(tool_log)),
            "success": raw.get("success", True),
        }
        job.status = "complete"

    except subprocess.TimeoutExpired:
        job.status = "error"
        job.error = "Scout agent timed out after 5 minutes"
    except Exception as e:
        job.status = "error"
        job.error = str(e)


class ScoutRequest(BaseModel):
    url: str


@app.post("/api/scout")
async def submit_scout(req: ScoutRequest):
    if not req.url.startswith("http"):
        raise HTTPException(status_code=400, detail="URL must start with http or https")
    job_id = str(uuid.uuid4())
    job = JobStatus(job_id=job_id, url=req.url)
    jobs[job_id] = job
    asyncio.create_task(_run_scout_job(job))
    return {"job_id": job_id}


@app.get("/api/scout/{job_id}")
def get_scout_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
