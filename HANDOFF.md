# Handoff Document — June 12 2026 (Updated)

## Branch: `all-sources-batch`
Railway deploys from this branch automatically on push. **Never push to main directly.**

---

## What Was Done This Session (Current)

### Data Imports
- **Crunchbase bulk**: 620,956 companies imported — all 82 countries, founded 2000+, all tech categories, no AI score filter
- **`cb_ai_tagged` column added**: Crunchbase's own AI taxonomy backfilled onto all 620K CB companies (47,163 tagged TRUE)
- **PitchBook Global**: 228K new companies + 52K enriched + 181K FundingSignals added; country format fixed to full names
- **PitchBook VC-NA**: 43K new companies + 87K enriched + 87K more FundingSignals
- **`total_raised` column added**: USD float on Company (from PitchBook, millions × 1M)
- **TLD country inference**: 170 no-country companies filled via domain TLD

### Pipeline Fixes
- 211 broken sites reset to pending (all were DNS failures from network outage — sites are fine)
- `yc` and `crunchbase_parquet` pseudo-domains removed from site_health
- `plugandplaytechcenter.com` + `500.co` reset to pending for Playwright retry
- International scout run on all countries (results pending check)

### Dashboard
- **Research tab** (new): AI adoption curve, geographic AI concentration bar chart, country × year heatmap, CSV exports
- **Overview stat cards** fixed: now use `_load_overview_stats()` (full DB counts, not 15K-limited df)
- **AI adoption curve removed from Trends** (now lives only in Research tab)
- **`is_ai` flag** updated to include `cb_ai_tagged` alongside `ai_score >= 0.3`
- **`cb_ai_tagged` + `founded_year`** added to `load_startups()` SELECT

### Scraper Improvements (from previous session, still in place)
- `_is_portfolio_url()` + Playwright-first for /portfolio, /companies, /investments paths
- `_extract_pagination_links()` for real next-page detection from rendered HTML
- `source_domain` column links agentic-scraped companies back to site_health domains

---

## Current State

| Metric | Value |
|--------|-------|
| Total companies | ~915,000 |
| AI companies (cb_ai_tagged OR ai_score ≥ 0.3) | ~51,836 (5.7%) |
| Countries | 149 |
| FundingSignal rows | 268,981 |
| Scraper sources | 274 (43 healthy, 231 pending) |

**AI Adoption Trend (core research finding):**

| Year | AI% |
|------|-----|
| 2018 | 12.8% |
| 2020 | 14.1% |
| 2022 | 20.1% |
| 2023 | 36.2% |
| 2024 | 40.2% |

---

## Immediately Pending

### 1. Check scout results
```bash
tail -50 /tmp/scout_run2.log
# or:
grep -E "registered|found|new site" /tmp/scout_run2.log
```

### 2. Run orchestrator on 231 pending sites
```bash
cd ai-startup-tracker
.venv/bin/python -c "
from backend.orchestrator.orchestrator import Orchestrator
orch = Orchestrator()
results = orch.run_all_due()
print(f'{sum(r.success for r in results)}/{len(results)} succeeded')
for r in results:
    print(f'  [{\"OK\" if r.success else \"FAIL\"}] {r.domain} — {getattr(r, \"companies_found\", \"?\")} companies')
" 2>&1 | tee /tmp/orchestrator_run.log
```

---

## Future To-Dos

### High Priority

**A. VC Deal Analysis in Research tab**
FundingSignals has 268K rows with deal_date, round_type, deal_size. Add to Research:
- Round type distribution by year (Seed / Early VC / Growth)
- Median deal size trend over time
- AI vs non-AI first financing date distribution
- Top investors by company count (once investor names are available)

**B. Backfill `ai_tags` on CB AI companies**
47K companies have `cb_ai_tagged=TRUE` but no subdomain tags (LLM, robotics, etc.).
Run `scripts/reclassify_ai_with_llm.py` on these to assign subcategory tags.
Enables the AI subdomains chart in Trends to work for CB companies.

**C. GitHub weekly discovery**
`scripts/github_weekly_discover.py` — hasn't been run this session.
Catches very new AI repos/companies not yet in CB or PB.

### Medium Priority

**D. ProductHunt / HackerNews scrapers**
`scripts/run_producthunt.py`, `scripts/run_hn_launch.py`
Valuable for 2024-2026 companies not yet in CB.

**E. Founded year filter in Overview**
`founded_year` is now loaded in `load_startups()` but not exposed as a sidebar filter.
Add a year range slider to the Overview filters.

**F. Research tab: filterable AI companies table**
Add a searchable/filterable table of AI companies with country, year, stage, total_raised.
Useful for qualitative exploration alongside the quantitative charts.

**G. Deduplication pass**
~4,700 no-domain companies may duplicate domain-keyed CB/PB records.
`scripts/run_dedup.py` shows top duplicate pairs.

**H. Country normalisation audit**
149 countries in DB (target was 82). PitchBook may have introduced non-canonical strings.
`scripts/normalize_countries.py` to audit.

### Lower Priority

**I. Geocoding international cities**
`scripts/geocode_locations.py` only covers US cities.
World map in Research tab needs global geocoding.

**J. Railway sync**
`scripts/diff_sync_companies_to_railway.py` — sync to hosted DB for sharing/deployment.
Run when local DB is stable.

**K. Merge to main**
`all-sources-batch` is many commits ahead. Decide when to merge + deploy.

---

## AI Classifier Reference

```sql
-- Reliable AI signal (use both):
WHERE cb_ai_tagged = TRUE OR ai_score >= 0.3

-- DO NOT use ai_score alone for CB companies:
-- 98% of CB companies score 0 even if AI-tagged (descriptions lack AI jargon)
```

---

## Key File Locations

| File | Purpose |
|------|---------|
| `backend/agentic/engine.py` | Claude agent scraper (Playwright-first for portfolio pages) |
| `backend/discovery/scout.py` | Tavily discovery scout |
| `backend/orchestrator/orchestrator.py` | Scrape scheduling and routing |
| `backend/orchestrator/health.py` | site_health table management |
| `backend/utils/country.py` | `normalize_country()` + `GLOBE_COUNTRIES` |
| `backend/db/models.py` | SQLAlchemy ORM (Company, FundingSignal, etc.) |
| `frontend/pipeline_dashboard.py` | Streamlit dashboard (~2,400 lines) |
| `scripts/import_crunchbase_companies.py` | CB bulk importer (82 countries, sets cb_ai_tagged) |
| `scripts/import_pitchbook_companies.py` | PB importer (full country names, captures deal data) |
| `scripts/run_international_scout.py` | Multi-country scout runner |
| `data/scout_coverage.json` | Scout run history per country |
| `~/Downloads/organizations.parquet` | CB orgs (1.2GB) |
| `~/Downloads/organization_descriptions.parquet` | CB descriptions (separate file — required for import) |
| `~/Downloads/pitchbook_other_glob_company.parquet` | PB global (371MB) |
| `~/Downloads/pitchbook_vc_na_company.parquet` | PB VC-NA (84MB) |

---

## Known Issues
- Scout `--all` run on June 12 — results not yet checked; orchestrator needs re-run after
- `plugandplaytechcenter.com` + `500.co` reset to pending; Playwright may or may not get them
- 2024-2026 company counts are lower due to CB entry lag (expected, not a bug)
- `main` branch is 50+ commits behind `all-sources-batch` — merge decision pending
