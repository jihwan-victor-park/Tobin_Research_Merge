# Global AI Startup Tracker (GitHub-first)

Discover emerging AI startups from GitHub, classify them with LLM, enrich/verify against Crunchbase and PitchBook parquet data, and explore results through an interactive Streamlit dashboard.

---

## Architecture

```
GitHub API (weekly)          Crunchbase (.parquet)       PitchBook (.parquet)
      |                            |                           |
      v                            v                           v
 github_weekly_discover.py   import_crunchbase.py        import_pitchbook.py
      |                            |                           |
      +------------+---------------+---------------------------+
                   v
            PostgreSQL DB
       +----------------------------+
       |  companies                 |  <- core entity table
       |  github_signals            |  <- repo-level data
       |  github_repo_snapshots     |  <- time-series metrics
       |  funding_signals           |  <- PitchBook deals
       |  source_matches            |  <- audit trail
       +----------------------------+
                   |
           +-------+-------+
           v               v
  run_llm_classify.py   pipeline_dashboard.py
  (LLM classification)  (Streamlit frontend)
```

## Quick Start

### 1. Setup

```bash
cd ai-startup-tracker
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env: set GITHUB_TOKEN, DATABASE_URL, TOGETHER_API_KEY (for LLM)
```

### 2. Create database

```bash
createdb ai_startup_tracker

# Initialize tables
python -c "from backend.db.connection import init_db; init_db()"
```

### 3. Run GitHub Discovery

```bash
# Discover AI repos from the last 30 days
python scripts/github_weekly_discover.py --since-days 30

# Skip LLM classification (just save to DB, classify later)
python scripts/github_weekly_discover.py --since-days 30 --no-llm
```

### 4. Run LLM Classification (standalone)

```bash
# Classify all unclassified snapshots
python scripts/run_llm_classify.py

# Classify a limited batch
python scripts/run_llm_classify.py --batch-limit 500

# Dry run (classify but don't save)
python scripts/run_llm_classify.py --dry-run
```

### 5. Import Crunchbase & PitchBook data

```bash
python scripts/import_crunchbase.py --path data/organizations.parquet --categories data/category_groups.parquet
python scripts/import_pitchbook.py --deal data/pitchbook_other_glob_deal.parquet --relation data/pitchbook_other_glob_deal_investor_relation.parquet
```

### 6. Run Full Weekly Update

```bash
# Runs all steps: GitHub -> Crunchbase -> PitchBook -> Report
python scripts/run_weekly_update.py --init-db
```

### 7. Launch Dashboard

```bash
streamlit run frontend/pipeline_dashboard.py
```

### 8. Run Tests

```bash
pytest tests/ -v
```

---

## Pipeline Steps

### A) GitHub Discovery (`scripts/github_weekly_discover.py`)

- Searches GitHub for repos with 26 AI topics and 25 keywords
- 6 search strategies: topic search, keyword search, starred repos, topic x stars combos, org-owned repos, recently updated
- Extracts company domain from repo homepage, org profile, and README
- Computes `startup_likelihood` heuristic score (0-1)
- Saves ALL discovered repos to DB (both accepted and rejected)
- Optional LLM classification step (can be run separately)
- Resilient: retries with exponential backoff, owner caching, rate limit checks

### B) LLM Classification (`scripts/run_llm_classify.py`)

- Standalone script to classify unclassified snapshots
- Supports 3 backends: **Together.ai** (recommended), Groq, Ollama
- 3-tier filter: auto-accept (heuristic >= 0.70), auto-reject (< 0.10), LLM for middle range
- Categories: startup, personal_project, research, community_tool
- Incremental: saves after each batch, safe to interrupt and resume
- 3 consecutive failures = auto-stop

### C) Crunchbase Import (`scripts/import_crunchbase.py`)

- Loads `organizations.parquet` + `category_groups.parquet`
- Auto-detects column names (flexible schema handling)
- Computes `cb_ai_flag` from categories + description keywords
- Matches to existing companies by canonical domain
- Updates `verification_status` to `verified_cb`

### D) PitchBook Import (`scripts/import_pitchbook.py`)

- Loads `deal.parquet` + `deal_investor_relation.parquet`
- Matches companies by domain (preferred) or strict fuzzy name (>= 0.95)
- Creates `funding_signals` with deal date, size, round type, top 5 investors
- Batched inserts for performance

### E) Weekly Orchestrator (`scripts/run_weekly_update.py`)

- Runs all steps in sequence
- Generates `reports/weekly_report_YYYYMMDD.json`

---

## Dashboard Features (`frontend/pipeline_dashboard.py`)

- **Overview**: Total stats, geographic map, verification status breakdown
- **Trending Repos**: Velocity metrics (7-day stars/forks delta)
- **AI Categories**: Subdomain classification, stack layers, language distribution
- **Startup Directory**: Paginated company listings with filters
- **GitHub Signals**: Stars/forks distributions, repo-level details
- **Funding Data**: PitchBook deals, deal sizes, round types
- **Emerging vs Funded**: Compare GitHub-only startups vs CB/PB-verified ones

---

## Scoring

### Startup Likelihood (0-1)

| Signal | Weight |
|--------|--------|
| Has product domain (not github.com/docs/etc.) | +0.25 |
| Repo owned by GitHub organization | +0.15 |
| Commercial keywords (pricing, enterprise, waitlist, demo) | +0.15 |
| Has Crunchbase/PitchBook record | +0.15 |
| Multiple contributors / recent activity | +0.10 |
| Has professional README with branding | +0.10 |
| Stars > 100 | +0.10 |

### LLM Classification

| Category | Description |
|----------|-------------|
| `startup` | Commercial product, SaaS, platform by a company/team |
| `personal_project` | Individual side project, portfolio, learning exercise |
| `research` | Academic research, paper implementations, benchmarks |
| `community_tool` | Open-source utilities without commercial intent |

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `companies` | Core entity (name, domain, location, scores, verification) |
| `github_signals` | Per-repo data (stars, forks, topics, README snippet) |
| `github_repo_snapshots` | Time-series snapshots with LLM classification |
| `funding_signals` | PitchBook deals (date, size, round, investors) |
| `source_matches` | Audit trail (CB/PB IDs, match method, confidence) |

---

## Project Structure

```
ai-startup-tracker/
├── backend/
│   ├── db/
│   │   ├── models.py              # SQLAlchemy ORM (companies, signals, snapshots)
│   │   └── connection.py          # DB engine + session management
│   ├── utils/
│   │   ├── llm_filter.py          # LLM classifier (Together.ai / Groq / Ollama)
│   │   ├── classify.py            # Rule-based AI subdomain/stack layer classifier
│   │   ├── scoring.py             # Heuristic scoring (ai_score, startup_likelihood)
│   │   ├── domain.py              # Domain extraction + canonicalization
│   │   ├── normalize.py           # Company name normalization + fuzzy match
│   │   ├── dedup.py               # Entity resolution + deduplication
│   │   └── trends.py              # Trend analysis utilities
│   ├── scrapers/                   # Legacy scrapers (YC, ProductHunt, etc.)
│   ├── database/                   # Legacy DB schema
│   └── intelligence/               # Legacy embeddings + LLM analyzer
│
├── frontend/
│   ├── pipeline_dashboard.py       # Main Streamlit dashboard (use this)
│   └── dashboard.py                # Legacy dashboard
│
├── scripts/
│   ├── github_weekly_discover.py   # GitHub repo discovery pipeline
│   ├── run_llm_classify.py         # Standalone LLM classification
│   ├── import_crunchbase.py        # Crunchbase parquet import
│   ├── import_pitchbook.py         # PitchBook parquet import
│   ├── run_weekly_update.py        # Weekly orchestrator
│   ├── backfill_locations.py       # Backfill missing location data from GitHub
│   ├── fix_locations.py            # Fix/normalize location strings
│   └── geocode_locations.py        # Geocode location strings
│
├── tests/
│   ├── test_domain.py              # Domain extraction tests
│   ├── test_normalize.py           # Name normalization tests
│   ├── test_scoring.py             # Scoring function tests
│   └── test_dedup.py               # Deduplication tests
│
├── data/                           # Parquet files + reports
│   ├── organizations.parquet       # Crunchbase organizations
│   ├── category_groups.parquet     # Crunchbase categories
│   ├── pitchbook_*.parquet         # PitchBook deals + investor relations
│   └── revelio_*.parquet           # Revelio Labs workforce data
│
├── reports/                        # Generated weekly reports
├── requirements.txt
├── .env.example
└── README.md
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `GITHUB_TOKEN` | Yes | GitHub personal access token |
| `TOGETHER_API_KEY` | For LLM | Together.ai API key (recommended LLM backend) |
| `GROQ_API_KEY` | For LLM | Groq API key (alternative, strict rate limits) |
| `LLM_BACKEND` | No | `together` (default), `groq`, or `ollama` |
| `LLM_MODEL` | No | Model name (default: `meta-llama/Llama-3.3-70B-Instruct-Turbo`) |
| `CB_ORGANIZATIONS_PATH` | No | Path to Crunchbase organizations.parquet |
| `CB_CATEGORIES_PATH` | No | Path to Crunchbase category_groups.parquet |
| `PB_DEAL_PATH` | No | Path to PitchBook deal.parquet |
| `PB_RELATION_PATH` | No | Path to PitchBook deal_investor_relation.parquet |

---

## Design Decisions

- **Domain as primary key**: Companies are matched by canonical domain first, then normalized name
- **DB-first pipeline**: All repos saved to DB before LLM classification, so processing work is never lost
- **Incremental LLM**: Classification can be interrupted and resumed; saves after each batch
- **3-tier LLM filter**: High-confidence heuristics skip LLM entirely, saving API calls
- **Idempotent**: Running any script twice produces the same result (upserts, not inserts)
- **NULL locations**: Unknown locations stay NULL (never defaulted to a specific city)
- **Flexible parquet schemas**: Column detection adapts to whatever column names exist
