# Startup Intelligence Platform — Project State
_Last updated: April 6, 2026_

---

## What This Project Is

A website that auto-updates weekly with emerging startups scraped from hundreds of sources — university accelerators, VC portfolios, incubators, and bulk databases. Companies are tracked with descriptions, founding dates, AI usage classification, and enrichment data from Pitchbook, LinkedIn, and Crunchbase.

---

## Current Database State

| Source | Companies | Uses AI |
|---|---|---|
| Crunchbase (bulk) | ~723,000 | 8.8% |
| YC | 5,293 | 37.2% |
| Techstars | 5,095 | 36.0% |
| StartX (Stanford) | 1,313 | 10.6% |
| Harvard Innovation Labs | 814 | — |
| Entrepreneur First | 467 | 38.8% |
| Berkeley SkyDeck | 360 | 11.4% (name only, low confidence) |
| Seedcamp | 317 | 29.0% |
| Princeton Keller Center eLab | 225 | 8.4% |
| MIT delta v | 250 | 0% (names only) |

**Total: ~737,000+ companies in `data/startups.db` (SQLite)**

---

## Project Structure
ai_startup_scraper/
scrapers/
yc_scraper.py           — Algolia API, batch pagination W05-S26
techstars_scraper.py    — Typesense API, page-based pagination
mit_deltav_scraper.py   — Claude HTML extraction (haiku)
ef_scraper.py           — WordPress admin-ajax.php POST
seedcamp_scraper.py     — BeautifulSoup, single HTML page
startx_scraper.py       — Webflow/Finsweet, page param pagination
harvard_scraper.py      — BeautifulSoup, single HTML page
skydeck_scraper.py      — WordPress admin-ajax.php POST, single request
princeton_scraper.py    — Drupal CMS, BeautifulSoup, two-pass (listing + detail pages)
crunchbase_import.py    — Pandas parquet bulk import
crunchbase_investigate.py — investigation script
agent/
agent.py                — entry point, CLI wrapper
scout.py                — scout mode, max 6 tool calls
execute.py              — execute mode, max 3 tool calls
tools.py                — fetch_url (returns cleaned_text + links), read_instruction_library, save_companies
prompts.py              — SCOUT_PROMPT, EXECUTE_PROMPT
init.py
db/
db.py                   — SQLite connection, insert_company(), bulk_upsert()
docs/
instruction_library.md  — human-readable, 28 entries
instruction_library.json — machine-readable, agent reads this
scripts/
reeval_uses_ai.py       — re-evaluates uses_ai across all rows
logs/                     — agent run logs (timestamped JSON)
data/
startups.db             — SQLite database
organizations.parquet     — Crunchbase bulk (1.15GB)
organization_descriptions.parquet — Crunchbase descriptions (545MB)

---

## Agent Architecture

Two-mode agent using Claude Sonnet 4.6 via Anthropic API:

**Scout mode** (`python agent/agent.py "URL" scout`):
- Checks instruction library for known patterns
- Fetches URL and analyzes structure — fetch_url now returns links list alongside cleaned_text
- Follows links from the links list rather than guessing URL patterns
- Writes draft instruction entry (status: draft)
- Never scrapes data, never writes to DB
- Max 6 tool calls (raised from 4), logs to logs/
- On known sites: recognizes approved entry in 2 tool calls and stops early

**Execute mode** (`python agent/agent.py "URL" execute source_name`):
- Reads approved instruction from library
- Defers to named scraper script if one exists
- Max 3 tool calls
- Returns structured result

Tools available: `fetch_url`, `read_instruction_library`, `save_companies`

---

## Instruction Library (28 entries)

Key patterns documented:
- JS-rendered pages (React/Vue/Angular) — use DevTools to find underlying API
- Algolia API — credentials in URL params, paginate by batch/filter not page
- Typesense API — credentials in headers, page-based pagination
- WordPress admin-ajax.php — POST with action param, paginate by incrementing paged
- WordPress admin-ajax.php (single request) — some sites return full dataset in one POST; duplicate keys must be sent as list of tuples not dict
- Webflow/Finsweet — hashed page param, server-rendered HTML chunks
- BeautifulSoup single-page — all data in initial HTML payload
- Drupal CMS — server-rendered, paginated via &page=N, Views taxonomy filter IDs in URL, group-title h2 for cohort year, two-pass (listing + detail) for full descriptions
- Parquet bulk import — pandas with executemany batches of 10,000
- Skipped: a16z (Vue/WordPress, low ROI), F6S (lists programs not companies), Station F (no public directory), Cornell eLab (bot protection), UChicago Polsky NVC (AJAX-loaded tabs, only 26 companies in static HTML)

---

## AI Detection

Keyword regex with word-boundary matching (`\b`) and `re.IGNORECASE`.

Current keyword list includes: ai, artificial intelligence, machine learning, large language model, llm, generative ai, gpt, neural network, deep learning, nlp, natural language processing, computer vision, data science, autonomous, generative, robotics, predictive, recommendation engine, artificial intelligence and machine learning.

After keyword fix (April 2026): 17,146 rows updated via `scripts/reeval_uses_ai.py`.

Key lessons:
- Always spot-check AI% against known companies after any keyword change
- Sources with name-only data (MIT delta v, SkyDeck) will undercount AI% — descriptions needed for reliable detection

---

## Key Technical Decisions

- **No local models** — M4 MacBook Air 16GB throttles under sustained load; API-based agents throughout
- **SQLite** — adequate for 750k+ rows, will migrate to Postgres at deployment
- **No Claude for field normalization** — direct Python mapping for structured fields, Claude only for genuine language understanding tasks
- **Guided autonomy** — agent handles known patterns automatically, flags novel structures for human instruction-writing
- **Instruction library is the agent's brain** — every problem solved becomes a reusable pattern
- **fetch_url returns links** — scout uses links list to follow hrefs rather than guessing URL patterns; prevents wasted tool calls on 404s

---

## What's Next

**Immediate:**
- Continue scouting university accelerators (Founders Factory, Rockstart, or similar)

**Soon:**
- Enrichment pass — use Crunchbase data to fill gaps in scraped sources (especially MIT delta v and SkyDeck which have names/URLs only)
- Deduplication across sources — same company appearing in multiple sources
- QC agent — flags missing fields, duplicates, anomalies
- Weekly automation pipeline (cron or Airflow)

**Later:**
- Frontend website
- Tavily API evaluation for scout agent fetch_url enhancement (collaborator already using it)

---

## Collaborator

Working with a fellow researcher. Planning/architecture in Claude.ai, coding in Claude Code (VS Code). These are separate contexts — Claude Code doesn't know conversation history.

---

## Environment

- Machine: M4 MacBook Air 16GB
- Python via miniconda (base env)
- Project at: `~/ai_startup_scraper/`
- API key: set via `export ANTHROPIC_API_KEY=...` in terminal
- Models in use: claude-sonnet-4-6 (agent), claude-haiku-4-5-20251001 (extraction tasks)
## automation


Easy Scrapes
 - make the easy scrapers
 - 25 easiest scrapers, hard-code
 - 
Hard Scrapes
 - Tavily, tools, attempts:
 - We have to figure out if we can fix/work
 - Figure out

Weekly Updates - problematic
 - 

 Database structuring: think about the columns, what to include
 Enriching later