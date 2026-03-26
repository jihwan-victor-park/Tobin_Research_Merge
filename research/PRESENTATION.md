
---

## The Data

**593 companies** across **8 university accelerator programs**

| Program | University | Companies |
|---------|-----------|-----------|
| StartX | Stanford | 100 |
| SkyDeck | UC Berkeley | 100 |
| iLab | Harvard | 98 |
| Entrepreneurship | UIUC | 98 |
| Startup Showcase | Duke | 98 |
| The Garage | Northwestern | 60 |
| Polsky Center | UChicago | 27 |
| Entrepreneurship | Northeastern | 12 |

**88 companies (15%) flagged as AI-related**

---

## The Pipeline

**Step 1 — Scrape** (`scripts/scrape_universities.py`)
- Static HTML scrapers for each accelerator's portfolio page
- Some use CSS classes (Harvard iLab: `.venture-card`), some use heading tags (h3/h4), one uses an Algolia search API (SkyDeck)
- Investigated 72 universities — only 8 have scrapable public pages

**Step 2 — Cohort pages** (`scripts/scrape_universities_track2.py`)
- Some universities don't have portfolio pages but publish annual showcase/cohort lists
- Duke Startup Showcase: scrapes 2024, 2025, 2026 cohort pages

**Step 3 — Enrich** (`scripts/enrich_universities_parquet.py`)
- Matches company names against Crunchbase (3.8M companies) and PitchBook (198K) by name
- Adds: description, website, funding raised, categories, founded year, location
- **292 matched in Crunchbase, 40 in PitchBook** — 56% enrichment rate



---

## Coverage After Enrichment

| Field | Count | % |
|-------|-------|---|
| Has description | 454 | 77% |
| Has website | 369 | 62% |
| Has funding $ | 146 | 25% |

---

## What Didn't Work (and Why)

- **MIT, CMU, Yale** — no public company listing pages
- **Georgia Tech, Columbia** — JS-rendered or login-required
- **Michigan** — returns 403
- Most universities list portfolio companies as alumni directories, not accelerator cohorts — excluded those

---

## Next Steps

1. **Merge with main database** — deduplicate against `data/ai_startups.csv` (187 existing companies)

2. **Improve AI detection** — keyword matching misses companies that use AI but don't say so (e.g. Anduril). Could use LLM classification on descriptions.

3. **More universities** — Georgia Tech CREATE-X, MIT delta v, and Columbia all have data but require either a login bypass investigation or JS rendering (Playwright/Selenium)

4. **Funding data gap** — 75% of companies have no funding figure. Could fill with LinkedIn, Crunchbase API, or PitchBook direct lookup.

5. **Automate / schedule** — run scrapers on a cron job quarterly to catch new cohorts as they're published

6. **Investor mapping** — identify which VCs are most active across these accelerator portfolios





5 websites to navigate - then come together:
 - Learning how to use agents
 - Learn how to code again w/ Claude
 - Use OpenModels
 - Scraping Websites, Enriching, and then Organizing

 NanoClaw or similar agent structured
 - Agentic AI uses
 - Scale - Agent - Workflow - MPC
 - Quality Control Agent
 - Track hard websites, put them into instruction files, for the Agent to deal with
 - Harmonize the datasets 
 - Use local Model, especially for learning
 - Very simple task 

 - 