# Handoff — June 13 2026

## Branch: `all-sources-batch`
Railway deploys from this branch automatically on push. **Never push to main directly.**

---

## Current State

| Metric | Value |
|--------|-------|
| Total companies | ~915,700 |
| AI companies (`cb_ai_tagged OR ai_score >= 0.5`) | ~52,141 |
| Countries | 112 (normalised, down from 149) |
| FundingSignal rows | 268,981 |
| Category coverage | 99.3% (909K/916K with 17 canonical verticals) |
| Healthy scraper sites | ~121 (was 43 at start of June) |

**AI Adoption Trend (core research finding):**

| Year | AI% |
|------|-----|
| 2018 | 12.8% |
| 2020 | 14.1% |
| 2022 | 20.1% |
| 2023 | 36.2% |
| 2024 | 40.2% |

ChatGPT-era inflection: AI's share of new company formation roughly tripled 2020→2024.

---

## Open Question: Is `ai_score` fit for purpose?

Discussed June 13, left open. Short answer: **no, not fully — but defensible for now.**

### The problem
`ai_score` was designed for GitHub repos where developer-chosen topics (`llm`, `rag`, `agents`) are high-precision signals. Applied to CB/PB it breaks down:

- GitHub repos reach 0.5 easily via topics alone (+0.3 strong topic + 0.2 moderate)
- CB companies max out at 0.5 only if cb_ai_tagged AND description has specific technical terms
- PitchBook companies (271K, no CB tag) max at 0.3 from text — permanently below the 0.5 threshold
- The 0.5 threshold excludes all PB companies by design; `cb_ai_tagged` was bolted on as an OR workaround

The score is not truly continuous — most companies land at exactly 0, 0.1, 0.2, or 0.3.

### What was tried
- Added "artificial intelligence", "generative ai", "ai-powered", "predictive analytics", "data science" to `MODERATE_AI_TEXT_KEYWORDS` (`backend/utils/scoring.py`)
- Ran `scripts/backfill_ai_score.py` on 885K unscored companies — 46K got non-zero scores
- At threshold 0.1: +22K AI companies, but they have a **flat year distribution (~1,200/yr from 2010–2025)** — they're legacy ML/analytics firms, not boom-era AI startups
- Kept 0.5 threshold: flat distribution means including them dilutes the research signal

### Recommended fix
LLM binary classifier on PitchBook's 271K companies: "Is AI the core product of this company?"
Claude Haiku, batch 25, ~$46 total, ~2h runtime. Keyword matching can't reliably distinguish
"AI company" from "company that uses some AI." Scope this before running.

---

## What Was Built Since June 3

### Scraper & Pipeline
- Playwright-first rendering for portfolio URLs (React/Next SPAs)
- Parallel orchestrator (ThreadPoolExecutor, workers=3) with Tavily 429 exponential backoff
- **Orchestrator cascade fix**: removed `_ANTHROPIC_DEAD` global + entire Together.ai fallback. Now does per-call Haiku downgrade on billing errors only — no more run-wide kill switch
- URL guard: `run_all_due` skips non-HTTP URLs (prevents pseudo-domains reaching Tavily)
- 32 new YAML scrape instructions for IL/SG/CN/KR/SA/PL VCs and accelerators
- `source_domain` column links scraped companies back to their site_health domain

### Data
- Crunchbase bulk import: 620K companies, 82 countries, `cb_ai_tagged`, `total_raised`
- PitchBook import fixed: 271K companies, full country names (not ISO), FundingSignals
- Country normalisation: 149 → 112 distinct countries
- `ai_tags` subdomain backfill: 10,860 CB AI companies tagged via keyword classifier

### Industry Taxonomy
- `backend/utils/industry.py`: 17 canonical verticals, CB (49 groups) + PB (~50 groups), unified vocabulary
- `companies.categories TEXT[]`: 99.3% coverage via CB parquet → PB parquet → Haiku LLM
- Scripts: `backfill_company_categories.py`, `classify_verticals_with_llm.py`, `backfill_ai_score.py`

### Dashboard
- Research tab: AI adoption curve, geographic concentration, country×year heatmap, CSV export
- Research section 3: AI adoption by industry vertical
- Research section 4: VC Deal Intelligence (deal volume, median size, first-financing AI vs non-AI)
- Overview: vertical filter via `categories` multiselect
- Trends fix: filter now `ai_score >= 0.5 OR cb_ai_tagged` (CB AI companies were invisible before)

---

## Immediately Pending

### 1. Commit YAML scrape instructions (~60 uncommitted files)
```bash
git add ai-startup-tracker/data/scrape_instructions/
git commit -m "Add/update scrape instructions from June 13 orchestrator run"
```

### 2. Check orchestrator completed
```bash
cd ai-startup-tracker && source .venv/bin/activate
python - <<'EOF'
import sys; sys.path.insert(0, '.')
from backend.db.connection import get_engine
from sqlalchemy import text
engine = get_engine()
with engine.connect() as c:
    rows = c.execute(text("SELECT status, COUNT(*) FROM site_health GROUP BY status ORDER BY COUNT(*) DESC")).fetchall()
    for s, n in rows: print(f"  {s}: {n}")
EOF
```
If pending sites remain: `python scripts/run_orchestrator.py --batch`

### 3. Backfill categories for new orchestrator companies
```bash
python scripts/backfill_company_categories.py
```

---

## Future To-Dos

**A. PitchBook AI classifier (LLM)** — resolves the open question. Haiku binary, ~$46, ~2h.

**B. Founded year slider** in Overview sidebar — `founded_year` loaded but not exposed as filter.

**C. Merge to main / push to Railway** — 15+ commits ahead.

**D. GitHub weekly discovery** — `scripts/github_weekly_discover.py` not run since early June.

**E. ProductHunt / HackerNews scrapers** — good for 2024-2026 companies not yet in CB.

**F. Retry 6 rate-limit broken sites** (all `consecutive_failures=1`, just re-run batch):
`rice.edu`, `fsid-iisc.in`, `startupbootcamp.org`, `siliconcatalyst.com`, `accubate.app`, `generalcatalyst.com`

**G. Geocoding** — world map needs global geocoding, currently US cities only.

---

## Key Commands
```bash
cd ai-startup-tracker && source .venv/bin/activate

python scripts/run_orchestrator.py --batch           # run pending scraper sites
python scripts/backfill_company_categories.py        # fill categories after new imports
python scripts/backfill_ai_score.py                  # score unscored companies (no API)
python scripts/classify_verticals_with_llm.py        # Haiku classifier for uncategorised
python scripts/run_international_scout.py --all      # discover new international sources
streamlit run frontend/pipeline_dashboard.py         # dashboard
```

## Key Files

| File | Purpose |
|------|---------|
| `backend/agentic/engine.py` | Agent scraper — Haiku fallback on billing errors |
| `backend/orchestrator/orchestrator.py` | Scheduling, routing, parallel execution |
| `backend/utils/scoring.py` | `compute_ai_score()` — see open question |
| `backend/utils/industry.py` | 17-category taxonomy + CB/PB mapping |
| `backend/db/models.py` | SQLAlchemy ORM |
| `frontend/pipeline_dashboard.py` | Streamlit dashboard (~2,500 lines) |
| `scripts/run_orchestrator.py` | **Use this — not `python -m backend.orchestrator.orchestrator`** |
| `scripts/import_crunchbase_companies.py` | CB bulk importer (sets `cb_ai_tagged`) |
| `scripts/import_pitchbook_companies.py` | PB importer (FundingSignals, full country names) |

## Parquet Files (local only)

| File | Notes |
|------|-------|
| `~/Downloads/organizations.parquet` | CB orgs (1.2GB) |
| `~/Downloads/organization_descriptions.parquet` | **Required for CB import** via `--descs` flag |
| `~/Downloads/pitchbook_other_glob_company.parquet` | PB global (371MB) |
| `~/Downloads/pitchbook_vc_na_company.parquet` | PB VC-NA (84MB) |

## Known Gotchas
- CB import: always pass `--descs ~/Downloads/organization_descriptions.parquet` — project-root copy is stale
- Orchestrator: use `scripts/run_orchestrator.py --batch`, not `python -m backend.orchestrator.orchestrator`
- AI filter: `cb_ai_tagged = TRUE OR ai_score >= 0.5` — never use `ai_score` alone for CB/PB
- 2024–2026 company counts are lower due to CB entry lag — expected, not a data error
