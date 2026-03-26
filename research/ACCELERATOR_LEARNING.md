# Accelerator Investigation Report

**Investigation Date:** 2026-02-16
**Accelerators Analyzed:** 5

---

## Y Combinator

**URL:** https://www.ycombinator.com/companies
**Total Companies:** 4,000+
**Scraping Method:** Algolia API
**Structure:** API-based
**Difficulty:** Easy
**Batch Data:** ✅ Yes

### Available Data Fields

- Company name
- One-liner description
- Long description
- Website URL
- Batch (W24, S23, etc.)
- Founded date
- Team size
- Location (city, region, country)
- Industries/tags
- Founders (names)
- Social links (LinkedIn, Twitter, Facebook)
- Status (Active, Acquired, Public, Dead)
- Top company flag
- Is hiring flag

### API Details

```json
{
  "endpoint": "https://45bwzj1sgc-dsn.algolia.net/1/indexes/*/queries",
  "app_id": "45BWZJ1SGC",
  "index": "YCCompany_production",
  "authentication": "Public API key",
  "pagination": "Yes (100 per page)",
  "rate_limit": "Generous"
}
```

### Notes

- Most complete data of any accelerator
- Public API makes scraping trivial
- Batch data clearly labeled (W24, S23, etc.)
- All companies included (not selective)
- Updated frequently

---

## Techstars

**URL:** https://www.techstars.com/portfolio
**Total Companies:** 3,600+
**Scraping Method:** JavaScript + React
**Structure:** Dynamic filtering
**Difficulty:** Medium
**Batch Data:** ✅ Yes

### Available Data Fields

- Company name
- Description (brief)
- Logo
- Location
- Program/vertical
- Year
- Status (Active, Exit, IPO)
- Valuation tier ($1B+)
- Website URL

### Filters Available

- Vertical Networks (17 categories)
- Regions (Global, Americas, Europe, etc.)
- Accelerator Years (2007-2024)
- Status ($1B+ companies, Exits, In program)
- B Corp certification

### Notes

- Data loads based on filter selections
- No single "get all" endpoint visible
- Requires Selenium or similar for scraping
- Portfolio stats: $31B funding, 10,800+ founders
- Batch/cohort data available by year

---

## 500 Global

**URL:** https://500.co/companies
**Total Companies:** 2,900+
**Scraping Method:** Builder.io CMS + React Table
**Structure:** Dynamic table component
**Difficulty:** Medium
**Batch Data:** ❌ No

### Available Data Fields

- Company name
- Logo
- Industry
- Sub-industry
- Country/headquarters
- Status (Current, Acquired, IPO, Defunct)
- Sector
- Region
- Investment vehicle/fund

### Notes

- Large portfolio but less detail per company
- Geographic diversity emphasized
- Status tracking (exits, IPOs)
- Industry categorization available
- No clear batch/vintage data

---

## Antler

**URL:** https://www.antler.co/portfolio
**Total Companies:** 1,400+
**Scraping Method:** Static HTML + Filtering
**Structure:** Grid with filters
**Difficulty:** Easy-Medium
**Batch Data:** ✅ Yes

### Available Data Fields

- Company name
- Logo
- Description (one sentence)
- Location
- Industry/sector
- Investment year
- Website URL
- Founder diversity metrics

### Filters Available

```json
{
  "Location": "24 options (Australia, Brazil, Denmark, Singapore, etc.)",
  "Sector": [
    "Real Estate/PropTech",
    "B2B Software",
    "FinTech",
    "Health/BioTech",
    "Energy/ClimateTech",
    "ConsumerTech",
    "Industrials"
  ],
  "Year": "2017-2026",
  "Search": "Text search by company name"
}
```

### Notes

- Clean, well-organized interface
- Year/cohort data available
- Good description coverage
- Filterable by multiple dimensions
- Relatively easy to scrape

---

## Plug and Play

**URL:** https://www.plugandplaytechcenter.com/portfolio/
**Total Companies:** 1,200+
**Scraping Method:** Multi-page vertical structure
**Structure:** Category-based pages
**Difficulty:** Hard
**Batch Data:** ❌ No

### Available Data Fields

- Company name
- Logo
- Category/vertical
- Description (varies)
- Website URL (not always visible)
- Location (sometimes)

### Notes

- Most complex structure to scrape
- Requires multi-page navigation
- Data quality varies by vertical
- No standardized format
- Would need custom scraper per vertical

### Challenges

- Each vertical has different layout
- No centralized portfolio view
- Must scrape multiple pages
- Inconsistent data structure
- Some verticals behind forms
- No batch/cohort information
- Rate limiting possible

---

## Quick Comparison

| Accelerator | Companies | Difficulty | Batch Data | Method |
|-------------|-----------|------------|------------|--------|
| Y Combinator | 4,000+ | Easy | ✅ | Algolia API |
| Techstars | 3,600+ | Medium | ✅ | JavaScript + React |
| 500 Global | 2,900+ | Medium | ❌ | Builder.io CMS + React Table |
| Antler | 1,400+ | Easy-Medium | ✅ | Static HTML + Filtering |
| Plug and Play | 1,200+ | Hard | ❌ | Multi-page vertical structure |


---

## Recommendations

### Priority Order for Scraping

**1. Start with Y Combinator** 🥇
- Easiest to scrape (public API)
- Most complete data (14 fields)
- Clear batch data
- 4,000+ companies
- **Status:** ✅ Already scraped

**2. Add Techstars** 🥈
- Good learning opportunity (Selenium)
- Has year/cohort data
- 3,600+ companies
- **Action:** Build Selenium scraper

**3. Try Antler** 🥉
- Easier than Techstars
- Has year data
- 1,400+ companies
- **Action:** Try HTML scraping first

**4. Skip Others for Now**
- 500 Global: No batch data
- Plug and Play: Too complex

### Next Steps

**This Week:**
1. ✅ Y Combinator - done
2. ✅ SkyDeck - done
3. 📋 Build Antler scraper

**Next Week:**
1. 📋 Build Techstars scraper (learn Selenium)
2. 📋 Test on 2-3 more accelerators

**Goal:** 10,000+ companies with batch data by end of month
