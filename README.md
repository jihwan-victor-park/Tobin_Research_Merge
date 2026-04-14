# AI Startup Intelligence Platform

A database of startups scraped from accelerators, VC firms, and incubators. Built to track and classify AI companies across the global startup ecosystem.

**Current status:** 736,897 companies across 8 sources — 68,217 flagged as AI (9.3%).

---

## Database

SQLite at `data/startups.db`. Schema:

| Field | Type | Notes |
|---|---|---|
| `name` | text | Company name |
| `description` | text | One-liner or short description |
| `founded_year` | integer | Extracted from description where available |
| `batch` | text | Cohort/lab identifier (e.g. `W24`, `student-i-lab`) |
| `website` | text | |
| `uses_ai` | boolean | Keyword-matched against description and tags |
| `tags` | text | JSON array of industry tags |
| `industries` | text | JSON array of program/industry categories |
| `location` | text | |
| `source` | text | e.g. `yc`, `techstars`, `harvard_innovationlabs` |
| `extra` | text | JSON object for source-specific fields (LinkedIn, Crunchbase URLs, lab affiliation, etc.) |

Deduplication is keyed on `(name, source)`.

---

## Sources

| Source | Companies | Approach | AI% | Notes |
|---|---|---|---|---|
| Crunchbase | 723,391 | Parquet bulk import | 8.8% | Filtered to operating/IPO companies founded ≥ 2015 |
| Y Combinator | 5,293 | Algolia API, paginated by batch | 37.2% | |
| Techstars | 5,095 | Typesense API, page-based pagination | 36.0% | |
| StartX | 1,270 | BeautifulSoup, Webflow/Finsweet pagination | 10.7% | |
| Harvard Innovation Labs | 814 | BeautifulSoup, path-based pagination `/pN` | 20.5% | |
| Entrepreneur First | 467 | WordPress admin-ajax.php POST | 38.8% | |
| Seedcamp | 317 | BeautifulSoup, single HTML payload | 29.0% | |
| MIT delta v | 250 | Claude Haiku HTML extraction | 0.0%* | |

*MIT delta v has names only — no descriptions, so AI detection requires an enrichment pass.

---

## Project Structure

```
ai_startup_scraper/
├── scrapers/
│   ├── yc_scraper.py            # Y Combinator via Algolia API (paginated by batch)
│   ├── techstars_scraper.py     # Techstars via Typesense API
│   ├── mit_deltav_scraper.py    # MIT delta v via Claude Haiku HTML extraction
│   ├── ef_scraper.py            # Entrepreneur First via WordPress AJAX
│   ├── seedcamp_scraper.py      # Seedcamp via BeautifulSoup (single payload)
│   ├── startx_scraper.py        # StartX via Webflow/Finsweet pagination
│   └── harvard_scraper.py       # Harvard Innovation Labs via BeautifulSoup (/pN pagination)
├── agent/
│   ├── agent.py                 # Agent entry point — scout and execute modes
│   ├── scout.py                 # Scout mode: investigate a URL, produce draft instruction
│   ├── execute.py               # Execute mode: build and run a scraper from an instruction
│   ├── prompts.py               # System prompts for each mode
│   └── tools.py                 # Tool definitions available to the agent
├── db/
│   └── db.py                    # SQLite connection, init_db(), insert_company(), bulk_upsert(), get_stats()
├── scripts/
│   └── reeval_uses_ai.py        # Retrospectively re-evaluate uses_ai for all rows after keyword changes
├── data/
│   └── startups.db              # SQLite database
├── docs/
│   ├── instruction_library.md   # Human-readable patterns and fixes per site structure
│   └── instruction_library.json # Machine-readable version consumed by the agent
└── logs/                        # Scout and execute run logs (JSON)
```

---

## Running

```bash
# Run any scraper directly
python scrapers/yc_scraper.py
python scrapers/techstars_scraper.py
python scrapers/seedcamp_scraper.py
python scrapers/startx_scraper.py
python scrapers/harvard_scraper.py
python scrapers/ef_scraper.py

# MIT delta v requires an Anthropic API key
export ANTHROPIC_API_KEY=your_key_here
python scrapers/mit_deltav_scraper.py

# Re-evaluate uses_ai across all rows (run after any keyword change)
python scripts/reeval_uses_ai.py
```

Each scraper fetches its source, normalizes fields, and upserts into `data/startups.db`. Re-running is safe — existing records are updated, not duplicated.

**Querying the database:** Open `data/startups.db` with [TablePlus](https://tableplus.com) or [DB Browser for SQLite](https://sqlitebrowser.org).

---

## Agent

The `agent/` directory contains a two-mode scraping agent:

- **Scout mode** — given a URL, investigates the site structure and produces a draft instruction entry (read-only, max 4 tool calls). Outputs to `logs/` and prints a draft for `docs/instruction_library.json`.
- **Execute mode** — given an approved instruction entry, builds and runs a scraper.

The agent reads `docs/instruction_library.json` before scouting to avoid re-investigating known sites. New sources go through scout → human review → execute.

---

## Adding a New Scraper

1. Run scout mode on the target URL (or investigate manually with DevTools)
2. Add an entry to `docs/instruction_library.json` with `"status": "approved"`
3. Create `scrapers/<name>_scraper.py` following the existing pattern
4. Call `insert_company(conn, company)` from `db/db.py` for each record
5. Add a run result entry to `docs/instruction_library.md`

The instruction library documents every site structure encountered — check it before building a new scraper. Common patterns are in entries 001–027.

---

## AI Detection

Keyword matching with word-boundary regex (`\b`) against `description`, `tags`, and source-specific text fields:

```
artificial intelligence, machine learning, large language model, llm,
generative ai, generative, gpt, neural network, deep learning, nlp,
natural language processing, computer vision, data science, autonomous,
robotics, predictive, recommendation engine, ai
```

`uses_ai` is best-effort — short descriptions undercount. After any keyword change, run `scripts/reeval_uses_ai.py` to update all existing rows.

---

## Roadmap

- [x] Crunchbase bulk data import (723k companies)
- [x] AI agent scaffold (scout + execute modes)
- [x] Instruction library (27 entries covering patterns, fixes, and site-specific notes)
- [ ] Enrichment pass (Crunchbase / LinkedIn APIs for missing descriptions and websites)
- [ ] Weekly automation pipeline
- [ ] Public-facing website
