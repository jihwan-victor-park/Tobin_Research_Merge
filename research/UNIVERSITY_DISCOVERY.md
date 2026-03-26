# University Accelerator Discovery Guide

**Created:** 2026-02-16
**Purpose:** Systematically discover university accelerators and their portfolio pages

---

## Overview

Instead of manually searching for university accelerators, we use an automated discovery process:

1. **Start with known universities** (Top 50 US universities)
2. **Try URL patterns** (innovation.stanford.edu, ventures.mit.edu, etc.)
3. **Look for portfolio pages** (/portfolio, /companies, /startups)
4. **Generate search queries** for manual investigation of difficult cases

---

## Discovery Methods

### Method 1: Known Accelerators

We already know about these:
- **Berkeley SkyDeck** - Has Algolia API ✅
- **Stanford StartX** - Portfolio page available
- **MIT Sandbox** - Known program
- **Columbia Startup Lab**
- **Penn Wharton Entrepreneurship**

### Method 2: URL Pattern Detection

Common patterns for university accelerators:
```
https://innovation.{university}.edu
https://ventures.{university}.edu
https://startup.{university}.edu
https://accelerator.{university}.edu
https://entrepreneurship.{university}.edu
https://www.{university}.edu/innovation
https://www.{university}.edu/ventures
```

### Method 3: Portfolio Page Detection

Once accelerator site found, look for:
```
/portfolio
/companies
/startups
/ventures
/our-companies
/portfolio-companies
/alumni
```

### Method 4: Google Search (Manual)

For hard-to-find accelerators, use queries like:
```
"{University Name} startup accelerator"
"{University Name} innovation lab portfolio"
"{University Name} venture fund companies"
```

---

## Usage

### Quick Test (Top 20 Universities)

```bash
# Discover accelerators for top 20 universities
python scripts/discover_university_accelerators_enhanced.py
```

**Output:**
- `data/university_accelerators_discovered.csv` - All results
- `data/university_accelerators_discovered_with_portfolios.csv` - High-value targets

### Full Scan (All 50 Universities)

Edit the script and remove `limit=20`:
```python
df = discovery.discover_all(TOP_US_UNIVERSITIES)  # No limit
```

### Add More Universities

Edit [data/us_universities_top100.py](data/us_universities_top100.py):
```python
TOP_US_UNIVERSITIES.append({
    'name': 'University of New Example',
    'short': 'une',
    'domain': 'une.edu',
    'state': 'CA'
})
```

---

## Expected Results

### Tier 1: Easy Discoveries (URL Patterns Work)

Universities with standard structure:
- Stanford → ventures.stanford.edu or startx.com
- MIT → innovation.mit.edu
- Berkeley → skydeck.berkeley.edu
- Carnegie Mellon → cmu.edu/swartz-center-entrepreneurship

**Success Rate:** ~30-40% via URL patterns

### Tier 2: Requires Portfolio Search

Accelerator found, but portfolio page needs manual check:
- Have innovation/entrepreneurship page
- No obvious /portfolio URL
- May list companies in blog/news section

**Success Rate:** ~20-30% need manual portfolio investigation

### Tier 3: Requires Manual Google Search

No obvious URL pattern:
- Custom domains (like StartX for Stanford)
- Programs embedded in business schools
- Multiple small programs (no central hub)
- Programs may not exist

**Success Rate:** ~30-40% require manual investigation

---

## High-Value Targets

Universities most likely to have **portfolio pages with company data**:

### Confirmed Portfolio Pages
1. **Berkeley SkyDeck** - 356 companies, Algolia API ✅
2. **Stanford StartX** - ~1,000 companies, likely has API
3. **Columbia** - Has startup lab listings
4. **Penn Wharton** - Tracks portfolio companies

### Likely to Have Portfolios
- MIT (multiple programs - Sandbox, Engine, delta v)
- Harvard (Innovation Labs)
- Georgia Tech (CREATE-X)
- University of Michigan (Zell Lurie Institute)
- Northwestern (The Garage)
- UT Austin (Longhorn Startup)
- Carnegie Mellon (Swartz Center)

---

## Discovery Pipeline

### Step 1: Run Automated Discovery
```bash
python scripts/discover_university_accelerators_enhanced.py
```

**Output:** CSV with all discoveries

### Step 2: Review Results

**High-value targets** (with portfolio pages):
→ Build scrapers immediately

**Found but no portfolio**:
→ Manual check for company listings

**Not found**:
→ Use Google queries provided in CSV

### Step 3: Manual Investigation

For universities where automation failed:
1. Google: "{University} startup accelerator"
2. Check university's entrepreneurship/innovation center
3. Look for venture/investment arms
4. Check if they list companies on Crunchbase as investor

### Step 4: Build Scrapers

For each discovered portfolio:
1. Inspect page structure
2. Check for API (like SkyDeck's Algolia)
3. Build Selenium scraper if needed
4. Extract company names
5. Enrich with Parquet database

---

## Expected Coverage

### Universities with Active Accelerators

**Tier 1 (Top 10):** ~90% have some form of accelerator
**Tier 2 (11-30):** ~70% have accelerators
**Tier 3 (31-50):** ~50% have formal accelerators

### Portfolio Data Availability

Of universities with accelerators:
- **~40%** have public portfolio pages
- **~30%** list some companies but not comprehensive
- **~30%** don't publicly list portfolio

### Total Addressable Companies

Estimated based on known programs:
- **SkyDeck (Berkeley):** 356 companies
- **StartX (Stanford):** ~1,000 companies
- **MIT programs (combined):** ~500 companies
- **Other top 10:** ~200-500 each

**Total Potential:** 5,000-10,000 companies from top 20 universities

---

## Alternative Data Sources

If portfolio pages not available:

### Option 1: Crunchbase Query
```python
# Find all companies invested in by university accelerator
python scripts/query_parquet.py --investor "Berkeley SkyDeck"
```

### Option 2: LinkedIn Search
- Search for "{University} Accelerator" in company affiliations
- Filter employees by startup experience
- Cross-reference with our database

### Option 3: University PR/News
- Many universities announce cohorts in news
- Scrape press releases
- Extract company names → Enrich

---

## Confirmed Scrapable Sources (March 2026)

After systematic investigation of 72 universities with innovation programs, only **7 produce
scrapable company data**. The rest either use JS-rendered pages, require login, return 404s,
or auto-detected `/portfolio` URLs that resolve to general pages (false positives).

| University | Program | Companies | Script |
|------------|---------|-----------|--------|
| Stanford | StartX | ~100+ | `scrape_universities.py` |
| UC Berkeley | SkyDeck (Algolia API) | 350+ | `scrape_universities.py` |
| UIUC | Entrepreneurship | 100+ | `scrape_universities.py` |
| UChicago | Polsky/NVC | 27 | `scrape_universities.py` |
| Northeastern | Entrepreneurship | 12+ | `scrape_universities.py` |
| **Harvard** | iLab (`.venture-card` class) | 100+ | `scrape_universities.py` |
| **Northwestern** | The Garage (h3 headings) | 60+ | `scrape_universities.py` |

**Total: 498 companies** in `data/university_portfolio_companies.csv`

## Why Others Didn't Work

| University | Issue |
|------------|-------|
| Georgia Tech VentureLab | Requires GT login |
| MIT (delta v / Sandbox) | No public company listing page |
| CMU Swartz Center | No public company listing |
| Yale Ventures | 404 on all company page URLs |
| Columbia Startup Directory | JavaScript-rendered, no static data |
| Duke Entrepreneurship | No company listing found |
| Michigan Zell Lurie | Returns 403 |
| Harvard Innovation Labs (login) | Member directory requires login |
| Other 24 "confirmed" /portfolio URLs | Auto-detected URLs that resolve to general pages |

## To Scrape

```bash
python scripts/scrape_universities.py
```

Output saved to `data/university_portfolio_companies.csv`.

## Track 2: Cohort Announcements & Alumni Directories (March 2026)

These universities don't have portfolio pages but DO expose company data via
news pages, showcase archives, or alumni startup directories.

| University | Source | Companies | Script |
|------------|--------|-----------|--------|
| **Cornell** | BigRedAI directory (`bigredai.org/startups`) | 889 | `scrape_universities_track2.py` |
| **Duke** | Startup Showcase (2024/2025/2026) | 98 | `scrape_universities_track2.py` |
| **Cornell** | eship High-Profile Alumni | 93 | `scrape_universities_track2.py` |

**Total: 1,080 companies** in `data/university_cohort_companies.csv` (30% AI-related)

Cornell BigRedAI is especially rich — 889 companies with descriptions, funding stage,
tags, and location — all in static HTML.

### Track 2 candidates that didn't pan out

| University | Issue |
|------------|-------|
| MIT delta v cohort pages | JS-rendered despite returning 200 |
| Penn VentureLab | No public company listing found |
| Brown B-Lab | No static company listing |
| Georgia Tech CREATE-X | Cohort pages require login or JS |
| Yale Ventures | No company listing pages found |

```bash
python scripts/scrape_universities_track2.py
```

## Track 3: Parquet Enrichment (March 2026)

Cross-referenced all 1,560 unique university companies against Crunchbase (3.8M) and
PitchBook VC NA (198K) using batch name matching.

**Results:**

| Metric | Count | % |
|--------|-------|---|
| Total companies | 1,560 | — |
| Matched in Crunchbase | 1,091 | 70% |
| Matched in PitchBook (remainder) | 81 | 5% |
| **Total enriched** | **1,172** | **75%** |
| With website | 1,254 | 80% |
| With description | 1,407 | 90% |
| With funding $ | 757 | 49% |

Output: `data/university_companies_enriched.csv`

```bash
python scripts/enrich_universities_parquet.py
```

Note: Investor fields in both Parquet files contain counts only, not investor names.
University program names cannot be used as investor search terms.

## Next Steps

1. **De-duplicate** - Merge `university_companies_enriched.csv` with `data/ai_startups.csv`
2. **Re-check blocked sources** - GT, Columbia, Yale may change public pages over time
3. **Other universities** - Check remaining 48 universities from HITS list individually
