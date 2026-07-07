# Info Sheet Page — Implementation Plan

Goal (from professor, Jul 7 2026): one clickable dashboard page that answers —
1. **Contribution sources** — which companies are covered by standard databases
   (Crunchbase/PitchBook), and for the rest, where they came from (GitHub? scraping?).
2. **What runs to finalize the database** — which scrapers/scout agents exist,
   which we want running but are currently NOT running.
3. **Scraping transparency** — how many websites we scrape, how many succeed,
   and monitoring of struggling ones.

Implementation: new "Info Sheet" tab (first tab) in
`frontend/pipeline_dashboard.py`, following the existing
`@st.cache_data + get_engine()` pattern. Each step is independently
committable and pushed to `merge` (Railway auto-deploys).

## Steps

- [x] **Step 1 — Scaffolding** (done Jul 7 2026)
  - This plan file committed to repo.
  - `page_info_sheet()` skeleton added, "Info Sheet" inserted as first tab.
  - Section placeholders for Steps 2–4, "as of" timestamp at top.

- [x] **Step 2 — Section 1: Data Sources & Contribution** (done Jul 7 2026)
  - Non-overlapping source breakdown query: `verified_cb` / `verified_pb` /
    scraper-unique (has incubator_signals, not CB/PB) / GitHub-unique.
    Table + stacked bar; totals must sum exactly to the companies count.
  - Scraper-unique breakdown by source (agentic sites, Techstars, YC, …).
  - Overlap note: companies our scrapers found that are ALSO in CB/PB.

- [ ] **Step 3 — Section 2: Scraping Operations**
  - Registered sites count; status breakdown (healthy/broken/degraded/pending/
    excluded); category breakdown (VC portfolio, university, accelerator, gov).
  - Last-30-days run stats: success rate, records collected, last run timestamp
    (red warning banner if pipeline stalled > 7 days).
  - Error-type breakdown (Tavily timeouts, Anthropic 429s, …).
  - Struggling-sites table: broken/degraded with last error + pending_reason.

- [ ] **Step 4 — Section 3: Pipeline Components — running vs not**
  - Inventory table of all pipeline components: SCRAPER (36 easy scrapers +
    agentic engine), HEALER, DISCOVERY (GitHub weekly, international scout),
    CLASSIFIER, enrichment scripts (Revelio, country normalizer, TLD inference).
  - Live status per component derived from DB: last activity, RUNNING /
    STALLED / NEVER RAN / INCOMPLETE.
  - Auto-detected gaps: scrape_runs stale, github_signals empty,
    naics_code column missing, no scheduler attached to Railway.

- [ ] **Step 5 — Verify & polish**
  - Run Streamlit locally against Railway DB; confirm page renders, queries
    are fast enough (raise cache TTLs if needed), numbers cross-check.
  - Final commit + confirm Railway deploy serves the page.

## Context needed to resume

- DB: Railway Postgres (URL in `reports/HANDOFF_2026_06_21.md` §Infrastructure).
- Known state (Jul 7): scraping stalled since Jun 15; launchd plist not loaded;
  Railway runs dashboard only; `naics_code` column does NOT exist on Railway;
  `github_signals` / `github_repo_snapshots` empty.
- Source-breakdown SQL reference: `reports/HANDOFF_2026_06_21.md` §Sources
  (verified_cb 650,200 / verified_pb 281,395 / scraper-unique 14,319 /
  GitHub-unique 32,248 = 978,162 total as of Jun 21).
- Push with `git push merge main` (NOT origin) to trigger Railway deploy.
