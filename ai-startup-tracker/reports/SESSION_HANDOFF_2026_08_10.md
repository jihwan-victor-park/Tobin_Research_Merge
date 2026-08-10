# Session Handoff — 2026-08-10 (post-compaction continuity)

Read this first after a context compaction. Everything below is committed on
`main` unless marked otherwise.

## Git / deploy state
- All three remotes aligned at **`de999eb`**: `origin/all-sources-batch`,
  `collaborator/main` (Railway deploy branch), `collaborator/alastair-updated-work`.
- **Push workflow (every commit, all three):**
  ```
  git push origin all-sources-batch
  git push collaborator all-sources-batch:main               # deploys
  git push collaborator all-sources-batch:alastair-updated-work
  ```
- Before pushing to `main`, `git fetch collaborator` + merge if Victor pushed.
- **Division of labor:** Victor = `enrich_fields.py` (classify/web/deep), Revelio
  founder pipeline, dashboard styling, scrapers. Me = analysis, longitudinal
  study, enrichment. Confirmed no overlap on the longitudinal work.

## The master findings doc
`reports/ECONOMIC_ANALYSIS_FINDINGS_2026_07_15.md` — sections 1-9, the source of
truth for all numbers. Also `reports/ENRICHMENT_SOURCE_LANDSCAPE.md`.

## What exists now (this session's build)

### A. Cross-sectional "hidden company" analysis (done)
- Hidden = not CB/PB (~54.7K); not on LinkedIn either (~52K). Higher AI-adoption
  (**20.7%** vs CB 12.3% / PB 10.6%). Enriched founding-year 8%→27% via proxies
  (`cohort_year`, `grant_first_award_year` on Railway `companies`), survival
  proxy (`domain_status`). research_analysis.py sections 9-13.
- "What AI companies are doing" (Victor's `company_enrichment` table, classify
  stage): hidden AI = more agents (14.5% vs 4% CB), open-source, less pure-B2B.
  6,344 hidden + 4,046 commercial classified. research_analysis.py 19-21.
- Founder aggregates (Revelio): AI founders more elite/technical (prestige 0.45
  vs 0.35, more PhDs), NO gender difference. research_analysis.py 14-18.
- Dashboard: founder + enrichment findings wired into `page_research()` in
  `frontend/pipeline_dashboard.py` (reads output/*.csv via `_read_output_csv`).

### B. Longitudinal AI-repackaging study (the recent thread — COMPLETE)
PitchBook 2021→2025 panel, joined on CompanyID (exact). Findings doc §6-9.
- **Panel:** 641,442 companies in both years; 7,648 ADDED AI language.
- **Nature** (LLM diff-classifier, n=2,000): 18% genuine `repackaged_to_ai`,
  34% added-feature, 3.4% text-washing, 33% keyword-FP, 10% born-AI.
- **Triangulation** (headcount+funding delta, free): 28% of added-AI show NO
  growth → text under-detects washing ~8x.
- **By sector:** IT repackages most (2.5%); B2B-services washes most (20%).
- **By cohort:** younger firms repackage ~4x more (pre-2010 0.7% → 2016-21 4%).
- **Exit outcomes** (CB 2023 match by domain): 578K matched, 33K acquired, 11K
  IPO, 17K closed. Repackaged firms CLOSE 3-5x less than same-age never-AI peers
  (cohort-matched). Caveat: survivorship-in-measurement (adding AI by 2025 needs
  being alive to update the profile).
- **Wayback for hidden = informative NEGATIVE:** ~90% of hidden AI companies have
  no archived 2021 homepage — they're born-AI-era, not repackagers. Repackaging
  is a commercial/established-company phenomenon.

## Key scripts (all committed)
- `scripts/ai_repackaging.py` — the 2021-vs-now diff-classifier (`--self-test`).
- `scripts/pb_longitudinal_repackaging.py` — panel + `--triangulate` + `--classify N`.
- `scripts/match_cb_exits.py` — exit outcomes; `--write` persists `cb_status`.
- `scripts/wayback_repackaging.py` — hidden repackaging (checkpointed; negative).
- `scripts/classify_commercial_sample.py`, `enrich_hidden_from_scraped.py`,
  `check_domain_liveness.py`, `export_enriched.py`, `founder_analysis.py`,
  `enrich_from_revelio.py`, `sync_hidden_enrichment_to_railway.py`.
- Output CSVs: `output/01-28*.csv` (numbered analyses).

## Data on disk (GIT-IGNORED, `data/pb_longitudinal/`)
`pb2021_company.dat` (pipe-delim), `pitchbook_{vc,pe,other}_glob_company.parquet`
(2025), `cb2023_{organizations,organization_descriptions,acquisitions,ipos}.parquet`.
**Disk ~4.3 GB free (97% used) — tight.** Pulled from shared Dropbox folder links
(`&dl=1` downloads directly, NO token needed). Folder structures differ: 2021 PB
= single Company.dat; 2025 PB = split parquets; CB = full dump. NOT re-downloaded:
CB `people`/`degrees` (founders) + `funding_rounds` (need CB zip re-pull, 2 GB).

## OPEN ITEMS / next steps
1. **`cb_status` DB write — DEFERRED.** Railway proxy was unstable 8/9-8/10 and
   the 567K-row write kept dropping. Data is safe in `output/23_exit_outcomes.csv`.
   Re-run `python scripts/match_cb_exits.py --write` when Railway settles.
2. CB `people`/`degrees` (commercial founders) + `funding_rounds` — re-download CB.
3. Rigor upgrade for repackaging: need the EXACT date AI was added (a mid-point
   snapshot, e.g. 2023) for a proper event-study rather than 2021-vs-2025 endpoints.

## Operational gotchas (bit us this session)
- **Railway proxy (`viaduct.proxy.rlwy.net`) drops connections constantly** — every
  DB script needs reconnect-retry; big writes are painful.
- **Local Postgres ≠ Railway** (separate DBs). Most session work ran directly
  against Railway. See memory `feedback_local_db_needs_railway_sync`.
- **Anthropic credits:** mine ran out mid-session (topped up). Victor's key is
  SEPARATE — his runs are unaffected by my credit state.
- **duckdb:** `matched`, `both`, `name` are reserved (alias them); `SET
  enable_progress_bar=false` or it floods stdout.
- **Don't double-background** (`&` + run_in_background) — loses stdout capture;
  persist results to a CSV instead.
- **PII:** `scripts/founder_poc/*.parquet` and `data/pb_longitudinal/` are
  git-ignored; commit AGGREGATES only (Victor's policy).
