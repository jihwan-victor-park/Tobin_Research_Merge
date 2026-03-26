# Difficult-to-Scrape Accelerators & Incubators

This document catalogs startup accelerators and incubators that present significant scraping challenges, organized by difficulty tier.

**Last Updated:** 2026-02-06

---

## Overview Statistics

- **Total Cataloged:** 20 accelerators
- **No Batch/Cohort Data:** 16/20 (80%)
- **Heavy JavaScript Required:** 20/20 (100%)
- **Poor HTML Structure:** 15/20 (75%)
- **Minimal Metadata:** 12/20 (60%)
- **Authentication Required:** 2/20 (10%)

---

## Tier 1: No Batch Data + Heavy JavaScript 🔴

**Difficulty Level:** Very High
**Success Rate:** <30% without browser automation

### 1. StartX (Stanford)
- **URL:** https://startx.com/companies
- **Challenges:**
  - No batch/cohort dates visible anywhere on portfolio page
  - Only company logos and names displayed
  - 500+ companies in simple visual grid
  - No descriptions, founding dates, or funding status
- **Scraping Strategy:** Generic HTML parsing, manual cross-reference with announcements
- **Status:** ✅ Custom scraper implemented

### 2. 500 Global
- **URL:** https://500.co/companies
- **Challenges:**
  - Built with Next.js and React Server Components
  - Portfolio data loads dynamically via Builder.io components
  - No batch/cohort dates publicly visible
  - CompaniesTable component uses placeholder data that loads client-side
- **Scraping Strategy:** Requires headless browser (Selenium/Playwright), API reverse engineering
- **Status:** ⚠️ Generic scraper available but likely insufficient

### 3. Techstars
- **URL:** https://www.techstars.com/portfolio
- **Challenges:**
  - React + Material-UI framework
  - Extensive CSS-in-JS styling
  - Company data dynamically loaded after filtering
  - Complex filter system but actual data not in static HTML
- **Scraping Strategy:** Headless browser + wait for dynamic content, intercept API calls
- **Status:** ⚠️ Generic scraper available but likely insufficient

### 4. Plug and Play Tech Center
- **URL:** https://www.plugandplaytechcenter.com/companies/
- **Challenges:**
  - Page consists almost entirely of font configuration and CSS
  - No actual page structure or functional elements in initial load
  - Heavily obfuscated JavaScript rendering
- **Scraping Strategy:** Headless browser mandatory, long wait times for content
- **Status:** ⚠️ Generic scraper available but likely insufficient

### 5. Berkeley SkyDeck
- **URL:** https://skydeck.berkeley.edu/portfolio/
- **Challenges:**
  - Algolia search integration (JavaScript-based)
  - Batch dates hidden in dropdown filters, not on company cards
  - No visible cohort information in main display
  - Requires navigating complex filter system
- **Scraping Strategy:** Algolia API reverse engineering (similar to YC scraper approach)
- **Status:** ❌ Not implemented - potential for API-based scraper

---

## Tier 2: Authentication/Paywall Required 🔒

**Difficulty Level:** Very High (Requires Credentials)
**Success Rate:** 0% without valid account

### 6. On Deck (ODF)
- **URL:** https://www.beondeck.com/
- **Challenges:**
  - Built on Bubble.io platform (extensive client-side rendering)
  - Requires authentication (session UID tracking)
  - No comprehensive public portfolio list
  - Company data fetched via API calls, not static HTML
- **Scraping Strategy:** Account required, session management, API token extraction
- **Status:** ❌ Not feasible without member access

### 7. Neo Accelerator
- **URL:** https://neo.com/
- **Challenges:**
  - Built on Bubble.io platform
  - Session management suggests authentication needed
  - Portfolio data requires full page load
  - Framework setup only, actual data loaded separately
- **Scraping Strategy:** Similar to On Deck - account required
- **Status:** ❌ Not feasible without member access

---

## Tier 3: Dynamic Loading + Minimal Metadata ⚡

**Difficulty Level:** High
**Success Rate:** 40-60% with headless browser

### 8. MassChallenge
- **URL:** https://masschallenge.org/portfolio
- **Challenges:**
  - Webpack chunks with dynamic component loading
  - Elementor page builder
  - Multiple tracking systems creating noise (Hotjar, Google Analytics)
  - No clear portfolio structure in accessible HTML
- **Scraping Strategy:** Headless browser, disable tracking, wait for Webpack chunks

### 9. Founder Institute
- **URL:** https://fi.co/graduates
- **Challenges:**
  - Alpine.js for client-side filtering
  - No batch dates on company cards
  - Google Tag Manager obscures actual data
  - Region-based filtering but temporal data absent
- **Scraping Strategy:** Headless browser, extract from Alpine.js data attributes

### 10. Capital Factory
- **URL:** https://capitalfactory.com/portfolio/
- **Challenges:**
  - 500+ companies in portfolio
  - 70+ industry category filters
  - Dynamic loading as user scrolls
  - Minimal metadata on company cards (no batch dates)
- **Scraping Strategy:** Scroll-triggered loading, multiple page requests

### 11. gener8tor
- **URL:** https://www.gener8tor.com/portfolio
- **Challenges:**
  - Vue.js framework
  - Data dynamically loaded from Airtable
  - No prominent batch/cohort dates in UI
  - Companies sorted by funding amount, not temporal data
- **Scraping Strategy:** Airtable API reverse engineering, Vue component inspection

### 12. DreamIt Ventures
- **URL:** https://www.dreamit.com/portfolio
- **Challenges:**
  - Built on Squarespace platform
  - No batch/cohort dates visible
  - Companies organized only by sector (Healthtech/Securetech)
  - Minimal metadata - primarily visual galleries
- **Scraping Strategy:** Squarespace JSON data extraction, sector-by-sector scraping

### 13. Village Global
- **URL:** https://www.villageglobal.com/portfolio
- **Challenges:**
  - jQuery with dynamic sliders
  - No batch/cohort dates visible
  - Minimal metadata per company
  - Disclaimer: highlighted companies ≠ full portfolio
- **Scraping Strategy:** Limited - only partial portfolio available, jQuery slider navigation

---

## Tier 4: Pagination + Poor Structure 📄

**Difficulty Level:** Medium-High
**Success Rate:** 60-80% with pagination handling

### 14. Startupbootcamp
- **URL:** https://startupbootcamp.org/startups/portfolio-companies
- **Challenges:**
  - jQuery carousel implementation
  - Year filter exists but not visible on company cards
  - Pagination limits data access
  - Need to navigate through multiple pages
- **Scraping Strategy:** Pagination loop, extract year from hidden attributes

### 15. Seedcamp
- **URL:** https://seedcamp.com/our-companies/
- **Challenges:**
  - WordPress + AJAX for dynamic loading
  - 550+ companies to process
  - Investment year visible but not actual cohort data
  - Client-side filtering
- **Scraping Strategy:** AJAX endpoint identification, WordPress REST API access

### 16. SOSV
- **URL:** https://sosv.com/portfolio/
- **Challenges:**
  - FacetWP for filtering
  - Gravity Forms integration
  - No batch/cohort dates visible in HTML/CSS
  - Client-side processing required
- **Scraping Strategy:** FacetWP API endpoints, form data extraction

### 17. BEENEXT
- **URL:** https://www.beenext.com/portfolio/
- **Challenges:**
  - Divi theme + WP Rocket optimization
  - Funding years only (not cohorts)
  - Rocket lazy-loading obscures content initially
  - Interactive filtering mechanisms
- **Scraping Strategy:** Disable lazy-loading, wait for full content load

---

## Tier 5: Complex Frameworks 🛠️

**Difficulty Level:** High
**Success Rate:** 40-70% depending on framework knowledge

### 18. Antler
- **URL:** https://www.antler.co/portfolio
- **Challenges:**
  - GSAP animations complicate rendering
  - Swiper.js for sliding content
  - 1,400+ companies in database
  - Cohort dates on SEPARATE page (/cohort-start-dates)
- **Scraping Strategy:** Two-stage scraping - portfolio + cohort dates page, cross-reference

### 19. Entrepreneur First (EF)
- **URL:** https://www.joinef.com/portfolio/
- **Challenges:**
  - Organized by founding year, not cohort
  - "Load more" pagination hides companies
  - Heavy JavaScript with custom filtering
  - No batch information on company cards
- **Scraping Strategy:** Click "load more" repeatedly, extract founding year as proxy

### 20. Pioneer Fund
- **URL:** https://www.pioneerfund.vc/portfolio
- **Challenges:**
  - React + Vite framework
  - Data from Airtable (supports up to 100,000 records)
  - No batch/cohort dates in configuration
  - Dynamic content rendering
- **Scraping Strategy:** Airtable API reverse engineering, React component inspection

---

## Easiest of the "Hard" ⭐

These are still difficult but more approachable:

1. **Seedcamp** - Has investment years (not cohorts, but temporal data exists)
2. **Antler** - Cohort dates available on separate page (/cohort-start-dates)
3. **Berkeley SkyDeck** - Batch data exists in filter dropdowns (extractable)
4. **Startupbootcamp** - Year filters work, just need pagination handling

---

## Hardest of the "Hard" ⛔

Virtually impossible without specialized tools or credentials:

1. **On Deck** - Requires authentication, no public portfolio
2. **Neo** - Bubble.io + auth requirements
3. **Plug and Play** - Completely obfuscated JavaScript
4. **500 Global** - Heavy React + Builder.io, no temporal metadata

---

## Framework Breakdown

| Framework | Count | Examples |
|-----------|-------|----------|
| React/Next.js | 5 | Techstars, 500 Global, Pioneer Fund |
| WordPress + Heavy JS | 4 | Seedcamp, SOSV, BEENEXT |
| Bubble.io | 2 | Neo, On Deck |
| Vue.js | 1 | gener8tor |
| Custom/Mixed | 8 | Antler (GSAP), Berkeley (Algolia), etc. |

---

## Key Insights

### Why These Are Difficult

1. **Client-Side Rendering (CSR)**
   - Data not in initial HTML response
   - Requires JavaScript execution to access content
   - Traditional HTTP requests insufficient

2. **No Temporal Metadata**
   - 80% lack batch/cohort/year information
   - Makes filtering for specific time periods impossible
   - Requires cross-referencing with external sources

3. **Dynamic Loading**
   - Infinite scroll patterns
   - "Load more" pagination
   - Content appears after user interaction

4. **Anti-Bot Measures**
   - Rate limiting
   - Cloudflare protection (not explicitly confirmed but likely)
   - Session tracking and fingerprinting

### Success Patterns

**What Works:**
- ✅ Headless browsers (Selenium, Playwright, Puppeteer)
- ✅ API reverse engineering (Algolia, Airtable)
- ✅ Multiple-stage scraping (portfolio → detail pages)
- ✅ Patience with rate limiting

**What Doesn't Work:**
- ❌ Simple HTTP requests with BeautifulSoup
- ❌ Generic scrapers without JavaScript rendering
- ❌ Single-pass scraping
- ❌ Ignoring robots.txt and rate limits

---

## Recommended Next Steps

### For Implementation Priority

1. **High Value, Medium Difficulty:**
   - Seedcamp (has investment years)
   - Antler (cohort dates on separate page)
   - Berkeley SkyDeck (Algolia API like YC)

2. **Medium Value, High Difficulty:**
   - Techstars (prestigious but very JavaScript-heavy)
   - 500 Global (large portfolio, complex stack)

3. **Low Priority (Too Difficult):**
   - On Deck (auth required)
   - Neo (auth required)
   - Plug and Play (heavily obfuscated)

### Tool Recommendations

**For JavaScript-Heavy Sites:**
- Selenium with Chrome/Firefox driver
- Playwright (better than Selenium for modern SPAs)
- Puppeteer (if comfortable with Node.js)

**For API Reverse Engineering:**
- Browser DevTools Network tab
- mitmproxy for HTTPS interception
- Postman for API testing

**For Airtable-Based Sites:**
- Look for Airtable API keys in JavaScript bundles
- Check for `airtable.com` requests in Network tab
- Use official Airtable API with discovered base IDs

---

## Related Documents

- [SCRAPING_STRATEGIES.md](SCRAPING_STRATEGIES.md) - Detailed scraping techniques by tier
- [scrapers/startx_scraper.py](scrapers/startx_scraper.py) - Example implementation for Tier 1

---

## Maintenance Notes

This list should be updated periodically as:
- Accelerators update their websites
- New frameworks are adopted
- API endpoints change
- Authentication requirements change

**Recommended Review Frequency:** Quarterly


##pitchbook, crunchbase, Linkedin 