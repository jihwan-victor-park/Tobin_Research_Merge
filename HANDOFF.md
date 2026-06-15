# Handoff — June 14 2026

## Branch: `all-sources-batch`
Railway deploys from this branch automatically on push. **Never push to main directly.**

---

## Current State

| Metric | Value |
|--------|-------|
| Total companies | ~916K |
| AI companies (`cb_ai_tagged OR ai_score >= 0.5`) | ~52,194 |
| Countries | 110 (normalised, confirmed clean) |
| FundingSignal rows | 268,981 |
| Category coverage | 99.3% (912K/916K, 17 canonical verticals) |
| Healthy scraper sites | 145 |
| Location coverage | 99.6% (912K with country; 110 countries) |

**AI Adoption Trend (core research finding):**

| Year | AI% |
|------|-----|
| 2015 | 5.3% |
| 2018 | 10.0% |
| 2020 | 11.0% |
| 2022 | 14.8% |
| 2023 | 24.5% |
| 2024 | 24.0%* |

*2023–2024 understated due to CB entry lag for recently-founded companies.

---

## Source Breakdown

| Source | Companies | Notes |
|--------|-----------|-------|
| Crunchbase | 621K | 82 countries, founded 2000+, CB AI taxonomy |
| PitchBook (net-new) | 281K | Not in CB; full deal data |
| GitHub discovery | 8K | LLM-classified repos |
| **Total** | **~916K** | |
| *of which: incubator-affiliated* | *19K* | *YC, Techstars, Stanford, Antler etc — cuts across all sources* |

---

## Open Question: Is `ai_score` fit for purpose?

Short answer: **no, not fully — but defensible for now.**

`ai_score` was designed for GitHub repos (where topics like `llm`, `rag`, `agents` are high-precision developer-chosen signals). Applied to CB/PB it breaks down:

- GitHub repos reach 0.5 easily via topics alone
- PitchBook companies (271K, no CB tag) max at 0.3 from text — permanently below threshold
- The 0.5 threshold effectively excludes all PB companies by design; `cb_ai_tagged` was bolted on as an OR workaround
- The score is not truly continuous — most companies land at exactly 0, 0.1, 0.2, or 0.3

We tried lowering the threshold to 0.1: it adds 22K companies but they have a **flat year distribution (~1,200/yr from 2010–2025)** — legacy ML/analytics firms where AI is peripheral, not boom-era AI startups. Kept 0.5 threshold.

**Recommended fix**: LLM binary classifier on PitchBook's 271K companies — "Is AI the core product of this company?" Claude Haiku, batch 25, ~$46 total, ~2h runtime. Keyword matching can't reliably distinguish "AI company" from "company that uses some AI."

For now: `cb_ai_tagged = TRUE OR ai_score >= 0.5` is the correct research filter. It's conservative but clean and describable.

---

## Pending

**A. Retry ~73 rate-limit broken scrapers** — all `consecutive_failures=1`, just re-run `python scripts/run_orchestrator.py --batch`

**B. Backfill categories for new orchestrator companies** — `python scripts/backfill_company_categories.py`

**C. GitHub weekly discovery** — `scripts/github_weekly_discover.py` not run since early June.

---

## Future To-Dos

**A. PitchBook AI classifier (LLM)** — resolves the open `ai_score` question. Haiku binary — "Is AI the core product?" — batch 25, ~$46, ~2h.

**B. Merge to main / push to Railway** — 15+ commits ahead of main.

**C. ProductHunt / HackerNews scrapers** — good for 2024-2026 companies not yet in CB.

**D. Research tab: filterable company table** — searchable with country, year, stage, total_raised.

**E. Geocoding (lat/lng)** — world map needs global geocoding, currently US cities only. Country coverage is solved (99.6%); this is for pin-level map only.

**F. LinkedIn data integration** — design sketched; new `linkedin_signals` table + `linkedin_id` in `source_matches`. Deferred.

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
| `backend/agentic/engine.py` | Agent scraper — Haiku fallback on billing errors (no Together.ai) |
| `backend/orchestrator/orchestrator.py` | Scheduling, routing, parallel execution |
| `backend/utils/scoring.py` | `compute_ai_score()` — see open question above |
| `backend/utils/industry.py` | 17-category taxonomy + CB/PB mapping dicts |
| `backend/utils/country.py` | `normalize_country()` + `GLOBE_COUNTRIES` |
| `backend/db/models.py` | SQLAlchemy ORM |
| `frontend/pipeline_dashboard.py` | Streamlit dashboard (~2,500 lines) |
| `scripts/run_orchestrator.py` | **Use this — not `python -m backend.orchestrator.orchestrator`** |
| `scripts/import_crunchbase_companies.py` | CB bulk importer (sets `cb_ai_tagged`) |
| `scripts/import_pitchbook_companies.py` | PB importer (FundingSignals, full country names) |
| `scripts/backfill_company_categories.py` | CB+PB parquet → canonical `categories` |
| `scripts/backfill_ai_score.py` | Scores unscored companies via regex (no API) |

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
- `incubator_source` on `companies` is NULL for all rows — use `incubator_signals` table for affiliation data
