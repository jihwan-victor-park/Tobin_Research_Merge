# AI Startup Scraper — Claude Instructions

## Project Overview
Python-based web scraper that collects data on AI startups from multiple sources (YC, Product Hunt, Crunchbase, Wellfound, accelerators/incubators). Outputs to CSV at `data/ai_startups.csv`.

## Project Structure
- `main.py` — CLI entry point and orchestrator
- `config.py` — AI keywords, data fields, source URLs, rate limits
- `scrapers/` — One scraper module per source
- `utils/ai_detector.py` — Keyword-based AI classification
- `utils/data_manager.py` — CSV read/write, deduplication
- `scripts/` — One-off analysis and batch scraping scripts
- `data/` — Output directory

## Key Conventions
- Each scraper returns a list of dicts matching `DATA_FIELDS` in `config.py`
- AI detection uses keyword matching with a confidence score (0.0–1.0)
- Deduplication is keyed on `(startup_name, source)`
- Rate limiting: 2s between requests (`RATE_LIMIT` in config)
- Use standard `requests` + `BeautifulSoup` unless site requires JS (then Selenium/Playwright)

## Adding a New Scraper
1. Create `scrapers/<name>_scraper.py` following the existing pattern
2. Register it in `config.py` `SOURCES` dict
3. Wire it up in `main.py`

## Running
```bash
python main.py --all              # all sources
python main.py --sources yc       # specific source
python main.py --all --ai-only    # AI startups only
```

## Notes
- Always respect `robots.txt` and site ToS
- Prefer official APIs over scraping where available (e.g. Crunchbase API)
- Some scrapers use Algolia API directly (YC, SkyDeck) — faster and more reliable
