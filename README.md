# AI Startup Tracker

A research platform for tracking emerging AI startups. Built at the Tobin Center for Economic Policy, Yale University.

The system continuously discovers new AI companies from GitHub, VC portfolios, accelerators, and incubators; classifies and enriches them with Crunchbase and PitchBook data; and surfaces trends through an internal Streamlit dashboard.

---

## System Architecture

The tracker runs three continuous loops.

```
                          +------------------------------+
                          |       LOOP 1: DISCOVERY      |
                          |     (find new sources)       |
                          +------------------------------+
                                        |
                  +---------------------+---------------------+
                  |                     |                     |
          GitHub Search            Feed Loader            Scout Agent
          (26 topics x 25 kw)      (CSV / markdown /      (Claude investigates
          6 strategies             instruction library)    unknown URLs)
                  |                     |                     |
                  +---------------------+---------------------+
                                        |
                                        v
                          +------------------------------+
                          |       LOOP 2: SCRAPING       |
                          |  (collect data from sources) |
                          +------------------------------+
                                        |
                              Orchestrator (registry)
                                  /              \
                                 /                \
                                v                  v
                    +-------------------+   +-------------------+
                    |    EASY TIER      |   |    HARD TIER      |
                    |  Hardcoded        |   |  Agentic engine   |
                    |  scrapers         |   |  (Claude + Tavily |
                    |  (14 sites)       |   |   + Playwright)   |
                    +-------------------+   +-------------------+
                                 \                /
                                  \              /
                                   v            v
                           +---------------------------+
                           |    PostgreSQL database    |
                           |  companies / signals /    |
                           |  snapshots / funding /    |
                           |  scrape_runs / site_health|
                           +---------------------------+
                                        |
                                        v
                          +------------------------------+
                          |     LOOP 3: SELF-HEALING     |
                          |  (keep the system running)   |
                          +------------------------------+
                                        |
          easy fails 2x -> auto-escalate to hard tier
          hard fails 3x -> exclude site for 90 days
          zero-result     -> retry via hard tier within 48h
          excluded site   -> re-evaluated after 90 days
                                        |
                                        v
                               Streamlit dashboard
```

---

## Scraper Tiers

### Easy Tier (Hardcoded)

Deterministic scrapers for sites with known, stable structure. Each one is a subclass of `BaseScraper` that returns a list of `ScrapedCompany` Pydantic models. No DB writes happen inside the scraper; the base class handles validation, deduplication, and persistence.

| Scraper               | Source                          | Pattern            |
|-----------------------|---------------------------------|--------------------|
| `yc_scraper`          | Y Combinator                    | api_direct (Algolia) |
| `techstars_scraper`   | Techstars portfolio             | api_direct         |
| `seedcamp_scraper`    | Seedcamp portfolio              | bs_single          |
| `antler_scraper`      | Antler                          | bs_paginated       |
| `ef_scraper`          | Entrepreneur First              | wp_ajax            |
| `skydeck_scraper`     | Berkeley SkyDeck                | wp_ajax            |
| `harvard_scraper`     | Harvard iLab                    | bs_paginated       |
| `startx_scraper`      | Stanford StartX                 | bs_paginated       |
| `princeton_scraper`   | Princeton eLab                  | bs_paginated       |
| `columbia_scraper`    | Columbia Entrepreneurship       | rest_api           |
| `rice_owlspark_scraper` | Rice OwlSpark                 | bs_single          |
| `mit_deltav_scraper`  | MIT delta v                     | claude_extraction  |
| `capitalfactory_scraper`, `alchemist_scraper`, `eranyc_scraper`, `villageglobal_scraper` | VC / accelerator portfolios | bs_paginated |
| `crunchbase_import`   | Crunchbase `organizations.parquet` | parquet bulk    |

Pattern key:
- **api_direct** — call a backend JSON API (Algolia / Typesense / REST) and parse the response.
- **wp_ajax** — paginate a WordPress site via `admin-ajax.php`.
- **bs_single / bs_paginated** — BeautifulSoup on a static or paginated HTML page.
- **claude_extraction** — fetch page, ask Claude to extract rows when the DOM is messy.
- **parquet** — filter a bulk parquet dump locally (no HTTP).

### Hard Tier (Agentic Fallback)

For unknown, complex, or JavaScript-heavy sites — and for any easy-tier scraper that breaks. The hard tier is an agentic engine in `backend/scrapers/hard/engine.py` that combines three tools:

1. **Tavily** — extracts page content from URLs, including JS-rendered pages, without maintaining a browser.
2. **Claude tool use** — plans the extraction: which pages to fetch, how to parse the text, when to paginate. The agent can call `fetch_page`, `fetch_page_rendered`, and `tavily_extract` tools in a loop (budget: 10 iterations, 6 rendered fetches).
3. **Playwright** — last-resort browser rendering for SPAs where Tavily and plain HTTP fail.

When the agent finds a reliable pattern, it saves a YAML instruction file under `data/scrape_instructions/` so the next run can use a cheaper path.

---

## Self-Healing

The orchestrator (`backend/orchestrator/orchestrator.py`) routes every scrape through a registry (`backend/scrapers/registry.py`) and tracks per-domain health in the `site_health` table.

| Trigger                            | Action                                           |
|-----------------------------------|--------------------------------------------------|
| Easy scraper returns zero or errors | Auto-escalate to hard tier                      |
| Hard tier fails 3 times in a row  | Mark site `excluded` for 90 days                 |
| Site returned zero results        | Retry via hard tier within 48 hours              |
| Site marked excluded              | Auto-revisit after 90 days                       |
| Site scraped successfully         | 7-day cooldown before next scrape                |

Every run writes a row to `scrape_runs` (status, records found / new / updated, duration), giving the dashboard a full audit trail of scraper health.

Big-tech and incumbent names are excluded across all sources via a shared denylist (`backend/utils/denylist.py`), applied at import time in the Crunchbase scraper, in the HN Who-is-Hiring scraper, and in the dashboard view — so Google, OpenAI, Alibaba, and similar companies never surface as "emerging AI startups."

---

## Project Layout

```
ai-startup-tracker/
  backend/
    agentic/          hard-tier engine, instruction YAML, Pydantic schemas
    db/               SQLAlchemy models, session management
    discovery/        Loop 1: feed loader, (scout agent)
    orchestrator/     Loop 2 + 3: router, health monitor
    scrapers/
      base.py         BaseScraper ABC + template method
      registry.py     domain -> scraper class
      easy/           14 hardcoded scrapers (see table above)
      hard/           agentic engine wrapper
    utils/            denylist, domain canonicalization, LLM filter,
                      scoring, classification, dedup
  data/
    scrape_instructions/     100+ YAML instructions for the agentic engine
    scrape_schedule/         registered_sites.yaml (targets + difficulty)
    instruction_library.json reference documentation
  frontend/
    pipeline_dashboard.py    Streamlit dashboard (5 tabs)
  scripts/
    run_orchestrator.py      unified daily runner
    run_weekly_update.py     weekly: GitHub -> Crunchbase -> PitchBook
    github_weekly_discover.py GitHub discovery
    import_crunchbase.py     Crunchbase parquet import
    import_pitchbook.py      PitchBook parquet import
    run_llm_classify.py      standalone LLM classifier
    scrape_incubators.py     multi-source incubator batch
  tests/                     pytest unit tests
```

---

## Dashboard

Launch with `streamlit run ai-startup-tracker/frontend/pipeline_dashboard.py`.

Five tabs:

1. **Overview** — newly discovered startups, geographic map, verification breakdown.
2. **GitHub Discovery** — GitHub-sourced companies filtered to `llm_classification == "startup"`.
3. **Trends** — AI subdomain treemap, category emergence curves, funding scatter.
4. **Pipeline Health** — per-site scraper status, data freshness, coverage gaps.
5. **Scraper** — manual scrape trigger with easy/hard tier routing.

---

## Quick Start

```bash
cd ai-startup-tracker
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Set DATABASE_URL, GITHUB_TOKEN, ANTHROPIC_API_KEY, TAVILY_API_KEY,
#     TOGETHER_API_KEY (optional)

createdb ai_startup_tracker
python -c "from backend.db.connection import init_db; init_db()"

# Discover + classify + import (weekly)
python scripts/run_weekly_update.py --init-db

# Scrape a specific source (daily)
python scripts/run_orchestrator.py --url https://seedcamp.com/companies/

# Run the batch of due sites
python scripts/run_orchestrator.py --run-all-due

# Launch the dashboard
streamlit run frontend/pipeline_dashboard.py
```

---

## Environment Variables

| Variable                     | Required | Description                                      |
|------------------------------|----------|--------------------------------------------------|
| `DATABASE_URL`               | yes      | PostgreSQL connection string                     |
| `GITHUB_TOKEN`               | yes      | GitHub personal access token                     |
| `ANTHROPIC_API_KEY`          | yes      | Claude API key (hard-tier agent + MIT extraction) |
| `TAVILY_API_KEY`             | yes      | Tavily content extraction                        |
| `TOGETHER_API_KEY`           | opt.     | Together.ai LLM classifier (default backend)     |
| `GROQ_API_KEY`               | opt.     | Alternative LLM backend                          |
| `LLM_BACKEND`                | opt.     | `together` (default), `groq`, or `ollama`        |
| `CB_ORGANIZATIONS_PATH`      | opt.     | Path to Crunchbase `organizations.parquet`       |
| `PB_DEAL_PATH`               | opt.     | Path to PitchBook deal parquet                   |
| `PB_RELATION_PATH`           | opt.     | Path to PitchBook investor-relation parquet     |

---

## Design Notes

- **Domain is the primary key.** Companies are matched first by canonical domain, then by normalized name.
- **DB-first pipeline.** All GitHub repos are persisted before LLM classification, so no work is lost if the classifier stops.
- **Idempotent ingests.** Running any import script twice produces the same result (upserts, not inserts).
- **Two Pydantic schemas, one model.** Both easy and hard tiers emit `ScrapedCompany`; the base class handles the rest.
- **Instruction YAML as cache.** The hard-tier agent saves successful patterns as YAML so future runs can skip the agentic path.
- **No defaulted locations.** Unknown locations remain `NULL` rather than collapsing to a single city.
