# scripts/

83 scripts, grouped by what they are for. Nothing here has been moved — the
paths in `docs/`, `reports/` and the paper's `SOURCES.md` still resolve. This
file is the map.

## How to run anything here

**Almost every script talks to the production database on Railway.** The
`DATABASE_URL` in `.env` points at a local Postgres that is empty, so running a
script directly will connect to nothing useful:

```bash
# Correct — injects Railway's DATABASE_PUBLIC_URL for the duration of the command
railway run -s Postgres -- .venv/bin/python scripts/<name>.py

# Wrong — silently hits the empty local database
.venv/bin/python scripts/<name>.py
```

The Railway proxy drops idle connections, so anything long-running needs a
reconnect loop (`analysis/_db.py` has one).

---

## 1. Pipeline — run these to keep the system moving

| Script | Purpose |
|---|---|
| `run_daily.py` | Single daily entry point; runs the others in order |
| `run_orchestrator.py` | **Main scraping CLI.** `--batch`, `--retry`, `--url` |
| `run_weekly_update.py` | Weekly: GitHub discovery → Crunchbase → PitchBook |
| `github_weekly_discover.py` | GitHub topic/keyword scan for new repos |
| `run_batch_by_category.py` | Agentic scrape over pending sites in chosen categories |
| `retry_pending_with_fallback.py` | Retry sites whose last attempt died on credit/rate limits |
| `run_agentic_scrape.py` | One site through the Tavily + Claude agent |
| `run_scout.py` / `run_international_scout.py` | Discover new source URLs |
| `live_agent_monitor.py` | Tail live scraper/healer activity |
| `morning_report.py` | Markdown summary of overnight activity |

> The pipeline is currently idle. Last scrape run 2026-07-09; the launchd job in
> `scripts/launchd/` is not loaded. Railway runs the dashboard only, no cron.

## 2. Bulk imports — load a whole source

| Script | Source |
|---|---|
| `import_crunchbase.py`, `import_crunchbase_companies.py` | Crunchbase parquet |
| `import_pitchbook.py`, `import_pitchbook_companies.py` | PitchBook parquet |
| `import_gov_grants.py` | NIH, NSF, EU CORDIS |
| `import_sbir_bulk.py` | Full SBIR/STTR award file |
| `import_grant_people.py` | Named leadership from NIH RePORTER |

Raw source files live in `data/` and are git-ignored (~7 GB).

## 3. Single-site scrapers (CLI wrappers)

`scrape_incubators.py` · `scrape_international_incubators.py` ·
`run_hn_launch.py` · `run_huggingface_scrape.py` · `run_producthunt.py` ·
`run_taaft.py`

## 4. AI classification — deciding `y_AI`

| Script | What it decides |
|---|---|
| `classify_pb_ai_with_llm.py` | "Is AI the core product?" for PitchBook rows the keyword cascade can't judge |
| `classify_verticals_with_llm.py` | Industry vertical when `categories` is empty |
| `classify_github_entities.py` | Is this name-only entity a company or a person? (built `github_entity_check`) |
| `reclassify_ai_with_llm.py`, `run_llm_classify.py`, `run_llm_classify_failover.py` | Batch (re)classification |
| `reverify_ai_mentioned.py` | Re-check companies that are AI *only* by the broad mention flag |
| `backfill_ai_score.py`, `backfill_ai_mentioned.py`, `backfill_cb_ai_tags.py` | Fill the flags without API cost |

The canonical predicate is `backend/utils/ai_filter.py` — four signals unioned.
Do not hand-write the SQL; import it.

## 5. Enrichment — filling missing fields

| Script | Fills |
|---|---|
| `enrich_fields.py` | **Main enrichment.** Evidence-tiered, writes per-value source + confidence into `company_enrichment` |
| `enrich_companies_with_ai.py` | Domain/country/description via one Tavily search + one LLM extraction |
| `enrich_from_github_profiles.py` | GitHub profile → bio, location, repo count (built `github_profile`) |
| `enrich_from_revelio.py` | NAICS + founded year from the employment dataset |
| `enrich_hidden_from_scraped.py` | Free: accelerator batch → cohort year, grant → first-award year |
| `wayback_founding_year.py` | Internet Archive first capture as a founding-year proxy |
| `check_domain_liveness.py` | Survival *proxy* — did the domain answer today |
| `geocode_locations.py`, `infer_country_from_tld.py` | Location (TLD inference was a measured dead end) |

## 6. Data hygiene

`normalize_countries.py` · `normalize_countries_railway.py` ·
`fix_railway_countries.py` *(one-time)* · `run_dedup.py` ·
`backfill_company_categories.py` · `backfill_site_health_from_companies.py` ·
`sync_site_categories.py` · `apply_buckets.py` · `classify_failures.py` ·
`rediscover_seed_urls.py`

## 7. Local → Railway sync

`diff_sync_companies_to_railway.py` · `sync_hidden_enrichment_to_railway.py` ·
`sync_llm_ai_verified_to_railway.py`

Only needed when work was done against a local copy. Most work now runs directly
against Railway, so these are largely historical.

## 8. Research analysis — the paper

These produce the numbers in `paper/`. `paper/CLAIM_EVIDENCE.md` maps each claim
to the script and output file that produces it.

| Script | Produces |
|---|---|
| `research_analysis.py` | The core cross-sectional analysis (`output/01-28_*.csv`) |
| `match_cb_exits.py` | Exit outcomes (acquired / IPO / closed) |
| `funding_trajectories_cb.py` | Seed → Series A/B/C graduation rates |
| `investor_network_cb.py` | Which investors back AI companies |
| `cb_ai_founders.py`, `founder_analysis.py`, `build_founder_profiles.py`, `build_workforce_signals.py` | Founder and workforce aggregates |
| `cb_ai_identity_panel.py`, `cb_ai_description_evolution.py` | When firms acquired an AI identity, and how their text changed |
| `ai_repackaging.py`, `pb_longitudinal_repackaging.py`, `pb_cb_unified_panel.py`, `classify_repackagers_cb.py`, `classify_commercial_sample.py` | AI-repackaging: genuine pivot vs relabeling |
| `wayback_ai_event_study.py`, `wayback_repackaging.py` | Dating AI adoption from the Internet Archive |

> The multi-vintage panel scripts need snapshot files under
> `data/pb_longitudinal/`, which were deleted to free disk. Those results are
> **not currently reproducible** — see `paper/RESEARCH_GAPS.md` §2.1.

Newer analysis lives in `analysis/` and `experiments/`, not here.

## 9. Taxonomy — "what do these AI companies actually do"

`taxonomy_pilot.py` → `taxonomy_pilot_label.py` → `taxonomy_build.py` →
`taxonomy_add_hidden.py` → `taxonomy_promote_pending.py` → `taxonomy_relabel.py`

Embedding-based bottom-up clustering. Populates `company_taxonomy` (111,678 rows)
and feeds the dashboard's Landscape page.

## 10. Reports and utilities

`generate_site_report.py` · `inventory_report.py` · `discover_from_news.py` ·
`dropbox_shard_fetcher.py`

## Non-Python

`launchd/` — macOS daily-job plist (**not currently loaded**) ·
`night_run.sh`, `run_enrichment_overnight.sh`, `run_scraping_plan.sh`,
`start_classify_when_funded.sh`, `wait_then_phase2.sh` — overnight wrappers ·
`migrate_*.sql` — one-off column migrations, superseded by the guarded
`ALTER TABLE` list in `backend/db/connection.py:init_db()`
