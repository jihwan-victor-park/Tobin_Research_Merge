# Discovery Approach Comparison

**University vs Government Startup Discovery**

---

## Quick Comparison

| Aspect | University Accelerators | Government Programs |
|--------|------------------------|---------------------|
| **Total Programs** | 50+ universities | 20+ programs |
| **Annual Companies** | 5,000-10,000 | 4,650+ |
| **API Availability** | Rare (SkyDeck has Algolia) | Common (35% have APIs) |
| **Data Quality** | Variable | Excellent (standardized) |
| **Discovery Success** | 90% found, 27% with portfolios | 85% have public lists |
| **Scraping Difficulty** | Medium-Hard (many JS sites) | Easy (APIs) to Medium (web scraping) |
| **Best Source** | Berkeley SkyDeck (Algolia API) | SBIR.gov API |

---

## University Accelerators

### What We Discovered

**Scanned:** Top 20 US universities
**Found:** 18 accelerators (90%)
**With Portfolio Pages:** 5 (27.8%)

**High-Value Targets:**
1. **Stanford StartX** - ~1,000 companies, portfolio page
2. **Berkeley SkyDeck** - 356 companies, **Algolia API** ✅
3. **Illinois Entrepreneurship** - Portfolio page
4. **UW Innovation** - Portfolio page
5. **UCLA Ventures** - Portfolio page

### Extraction Method

**For accelerators with APIs (e.g., SkyDeck):**
```python
# Direct API access - FAST
from algoliasearch.search.client import SearchClientSync
client = SearchClientSync(app_id, api_key)
results = client.search_single_index(index_name, {"query": ""})
```

**For accelerators with portfolio pages:**
```python
# Selenium scraping - MEDIUM
from selenium import webdriver
driver = webdriver.Chrome()
driver.get(portfolio_url)
# Extract company cards/listings
```

**For accelerators without portfolios:**
```python
# Cross-reference approach
# Query Crunchbase for companies with "Berkeley SkyDeck" investor
query_parquet.py --investor "Berkeley SkyDeck"
```

### Expected Results

- **Best case (API):** 356 companies in 5 seconds (SkyDeck)
- **Good case (Portfolio page):** 50-200 companies in 30-60 seconds (Selenium)
- **Worst case (No portfolio):** Manual Google search or database query

---

## Government Programs

### What We Discovered

**Scanned:** 12 federal + 8 state programs
**With APIs:** 7 (35%)
**With Public Lists:** 17 (85%)

**High-Value Targets:**
1. **SBIR.gov API** - 200,000+ awards, covers 8 agencies ✅
2. **NSF Awards API** - I-Corps + innovation programs ✅
3. **NIH RePORTER API** - Biotech/healthtech focus ✅
4. **USASpending.gov API** - All federal spending ✅

### Extraction Method

**SBIR.gov API (BEST):**
```python
# Single API call gets thousands of companies
import requests
response = requests.get(
    'https://www.sbir.gov/api/awards.json',
    params={'year': 2024, 'phase': 2}
)
companies = response.json()
```

**NSF Awards API:**
```python
response = requests.get(
    'https://api.nsf.gov/services/v1/awards.json',
    params={'keyword': 'I-Corps'}
)
```

**NIH RePORTER API:**
```python
response = requests.post(
    'https://api.reporter.nih.gov/v2/projects/search',
    json={'criteria': {'activity_codes': ['R44']}}
)
```

### Expected Results

- **SBIR.gov:** 20,000+ companies since 2010 in ~10 API calls
- **NSF I-Corps:** 2,000+ teams in 1-2 API calls
- **NIH RePORTER:** 10,000+ awards in multiple calls

---

## Combined Strategy

### Phase 1: Easy Wins (APIs)

**Week 1:**
1. **Berkeley SkyDeck** - Algolia API → 356 companies
2. **SBIR.gov** - REST API → 20,000 companies
3. **NSF I-Corps** - REST API → 2,000 companies

**Result:** 22,000+ companies in Week 1

---

### Phase 2: Portfolio Scraping

**Week 2:**
1. **Stanford StartX** - Build Selenium scraper
2. **Illinois, UW, UCLA** - Portfolio page scrapers
3. **MIT, Harvard, CMU** - Manual investigation

**Result:** +2,000-5,000 companies

---

### Phase 3: Cross-Reference

**Week 3:**
1. **Enrich all companies** with Crunchbase/PitchBook
2. **Expected enrichment:** 50-80%
3. **Gain:** Descriptions, websites, funding, LinkedIn

**Result:** Comprehensive profiles for 20,000+ companies

---

### Phase 4: Expansion

**Week 4:**
1. Add remaining 30 universities (full scan of 50)
2. Add state government programs
3. Build NIH RePORTER extraction

**Result:** 30,000+ total companies

---

## Recommended Priority Order

### 🥇 Tier 1: Immediate (APIs Available)

1. ✅ **SBIR.gov API** - 20,000 companies, excellent data
2. ✅ **Berkeley SkyDeck** - 356 companies, Algolia API
3. ✅ **NSF I-Corps** - 2,000 companies, NSF API

**Why:** Fast, reliable, high volume

---

### 🥈 Tier 2: High Value (Portfolio Pages)

1. **Stanford StartX** - ~1,000 companies
2. **Illinois/UW/UCLA** - 200-500 each
3. **MIT programs** - Combined 500+

**Why:** Good volume, scrapeable, prestigious programs

---

### 🥉 Tier 3: Manual Investigation

1. **Harvard, Yale, Princeton** - No obvious portfolio pages
2. **State programs** - Various levels of documentation
3. **Smaller universities** - Lower volume

**Why:** Time-intensive, lower volume, but completes coverage

---

## Files Created

### University Discovery
- `data/us_universities_top100.py` - University list
- `scripts/discover_university_accelerators.py` - Basic discovery
- `scripts/discover_university_accelerators_enhanced.py` - Enhanced discovery
- `UNIVERSITY_DISCOVERY.md` - Guide

### Government Discovery
- `data/government_programs.py` - Program list
- `scripts/discover_government_programs.py` - Discovery script
- `GOVERNMENT_DISCOVERY.md` - Guide

### Comparison
- `DISCOVERY_COMPARISON.md` - This file

---

## Success Metrics

### University Discovery Test (Top 20)
- ✅ 90% discovery rate (18/20 found)
- ✅ 27.8% with portfolio pages (5/18)
- ✅ 356 companies from SkyDeck in 5 seconds

### Government Discovery Test (20 programs)
- ✅ 85% have public lists (17/20)
- ✅ 35% have APIs (7/20)
- ✅ 4,650 companies funded annually
- ✅ 200,000+ historical awards available

---

## Next Actions

### This Week
1. ✅ University discovery - Complete
2. ✅ Government discovery - Complete
3. 📋 Build SBIR.gov extractor
4. 📋 Extract 20,000 SBIR companies
5. 📋 Cross-reference with Parquet database

### Next Week
1. Build Stanford StartX scraper
2. Build UCLA/UW/Illinois scrapers
3. Extract NSF I-Corps companies
4. Unify all sources into single database

### This Month
1. Scan all 50 universities (remove limit=20)
2. Add NIH RePORTER extraction
3. Add state program scrapers
4. Target: 30,000+ companies total

---

## Key Insight

**The cross-referencing approach works best:**

1. **Scrape/Extract** company NAMES from easy sources (APIs, simple lists)
2. **Enrich** with Crunchbase/PitchBook for full data
3. **Result:** Better data than original source

**Example:**
- SBIR.gov gives: Company name, location, government funding
- Crunchbase adds: Description, website, private funding, team
- **Combined:** Complete startup profile

**This means:**
- Don't waste time scraping complex websites for full data
- Just get names, let database enrichment do the rest
- Focus on sources with **volume** and **easy extraction**

---

**Ready to scale:**
```bash
# Universities
python scripts/discover_university_accelerators_enhanced.py

# Government
python scripts/discover_government_programs.py

# Next: Build extractors for top sources
```
