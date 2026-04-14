# Instruction Library

A growing reference of issues encountered during scraping and their fixes.
Updated as new problems are discovered.

---

## Entry 001
**Site:** Y Combinator (ycombinator.com/companies)
**Issue:** `requests` returns only 39 characters of usable content
**Root Cause:** Page is JavaScript-rendered (React). `requests` fetches the static HTML shell only — no company data is present in it.
**Fix:** Use the site's underlying API directly instead of scraping HTML. YC's search is powered by Algolia and returns clean JSON with all company data. No browser rendering needed.
**Reusable Pattern:** Yes — any site built on React/Vue/Angular will have this problem. Always check if the site has an underlying API (check Network tab in browser DevTools) before attempting HTML scraping.

---

## Entry 002
**Site:** Y Combinator (ycombinator.com/companies)
**Issue:** Algolia API returning 403 Forbidden
**Root Cause:** Hardcoded API keys were outdated. Public-facing API keys rotate or expire. Keys found in tutorials or old code may be stale.
**Fix:** Always pull live keys from browser DevTools Network tab — filter by the service name (e.g. "algolia"), inspect request headers directly to get current values.
**Reusable Pattern:** Yes — applies to any site using a third-party search or data API (Algolia, Elasticsearch, etc.)

---

## Entry 003
**Site:** Y Combinator (ycombinator.com/companies)
**Issue:** Algolia credentials not found in request headers
**Root Cause:** YC passes Algolia credentials as URL query parameters
   rather than request headers. Filtering by "algolia" in DevTools
   Network tab and checking the full request URL reveals them.
**Fix:** Copy the full URL from the Network tab request — credentials
   are embedded as `x-algolia-application-id` and `x-algolia-api-key`
   query parameters. Pass them as query params in requests, not headers.
**Reusable Pattern:** Yes — some services embed API keys in the URL
   rather than headers. Always check the full request URL, not just
   the headers panel.

---

## Entry 004
**Site:** Y Combinator (ycombinator.com/companies)
**Issue:** 81.7% of companies falsely flagged as `uses_ai`
**Root Cause:** Keyword matching used simple substring search, so short
   terms like `'ml'` matched words like 'marketplace' and 'model'.
**Fix:** Use `re.search(r'\b' + keyword + r'\b', text, re.IGNORECASE)`
   for word-boundary matching. Also tighten the keyword list to specific
   unambiguous terms: 'artificial intelligence', 'machine learning',
   'large language model', 'llm', 'generative ai', 'gpt', 'neural network',
   'deep learning', 'nlp', 'natural language processing', 'computer vision'.
**Reusable Pattern:** Yes — always use word-boundary matching for short
   keywords. Never use bare substring search for classification tasks.

---

## Entry 005
**Site:** Y Combinator (ycombinator.com/companies)
**Issue:** Algolia API capped at 1,000 results — YC has 4,000+ companies
**Root Cause:** Algolia enforces a hard 1,000 hit limit per query regardless
   of pagination. Incrementing page number returns empty after page 0.
**Fix:** Paginate by filter instead of by page number. Query each YC batch
   separately (W05 through current batch) using Algolia's filter param:
   `filters=batch%3A%22W24%22`. Deduplicate results by company name.
   Retrieved 5,365 unique companies this way.
**Reusable Pattern:** Yes — any Algolia-powered site will have this cap.
   Find a filterable field with manageable cardinality and loop through
   its values instead of paginating directly.

---

## Entry 006
**Site:** Y Combinator (ycombinator.com/companies)
**Issue:** `founded_year` showing wrong values (e.g. all companies showing 2012)
**Root Cause:** `launched_at` Unix timestamp is when the YC profile was
   created, not when the company was founded. No clean `year_founded`
   field exists in the Algolia hit.
**Fix:** Extract founding year from `long_description` using regex to find
   4-digit years mentioned in the text. Companies frequently state their
   founding year in their description. Set to `null` if no reliable source
   found — a null is honest, a wrong date corrupts the dataset.
**Reusable Pattern:** Yes — never assume a timestamp field means founding
   date. Always verify against a known company (e.g. Airbnb, founded 2008).
   Prefer null over a plausible-but-wrong value.

---

## Entry 007
**Site:** All sources (general database pattern)
**Issue:** 72 companies silently dropped on insert — 5,365 fetched but
   only 5,293 in DB
**Root Cause:** UNIQUE(name, source) constraint correctly catches
   companies appearing in multiple YC batches with the same name.
   Upsert overwrites with the last write — no data is truly lost but
   the count discrepancy can be confusing.
**Fix:** This is expected and acceptable behavior. Document the
   discrepancy in run summaries so it doesn't look like a bug. If
   preserving all batch appearances matters later, add a separate
   `company_batches` junction table.
**Reusable Pattern:** Yes — always reconcile fetched count vs inserted
   count after any bulk upsert. A silent drop is not always a bug but
   should always be understood.

---

## Entry 009
**Site:** Techstars (techstars.com/portfolio)
**Status:** Working
**Result:** 5,097 companies fetched, 5,095 upserted
**Notes:** 30.1% flagged as uses_ai — higher than YC because Techstars
   has explicit industry_vertical tags including "Artificial intelligence
   and machine learning" which keyword matching catches reliably.
   Extra fields (crunchbase_url, linkedin_url, twitter_url, worldregion)
   stored in extra JSON column.
**Pattern confirmed:** Typesense API, header auth, page-based pagination,
   250 per page max.

---

## Entry 010
**Site:** a16z (a16z.com/portfolio)
**Status:** Skipped — low ROI
**Root Cause:** Despite appearing server-rendered, the portfolio page is
   a Vue.js app embedded in WordPress. No clean API found in Network tab.
   Company data likely embedded as a JavaScript variable in the initial
   HTML payload — requires JS parsing or headless browser to extract.
**Fix:** Not worth pursuing at this stage. Revisit later with Playwright
   when JS-rendered sites become a priority.
**Reusable Pattern:** Yes — when DevTools shows Vue/React component syntax
   (`:src`, `:alt`, `item.company.name`) in the Elements tab, the page is
   a JS-rendered app. If no Fetch/XHR API calls fire on load or interaction,
   the data is either embedded in the HTML as a JS variable or requires
   a headless browser. Flag these as high-effort and deprioritize unless
   the source is uniquely valuable.
**ROI Decision:** Skip JS-embedded sites in favor of sources with clean
   APIs or simple server-rendered HTML. University accelerator pages
   offer more companies collectively with far less scraping complexity.

---

## Entry 011
**Site:** MIT delta v (entrepreneurship.mit.edu/accelerator/past-teams/)
**Status:** Working
**Approach:** requests + Claude HTML extraction (claude-haiku-4-5-20251001)
**Result:** 250 companies extracted, $0.0097 per run
**Why Claude here:** Page is WordPress server-rendered with companies
   listed as plain bullet points under year headings. Structure is
   consistent enough for BeautifulSoup but using Claude to read raw
   HTML is cleaner and handles year-cohort grouping automatically.
**Fields available:** name, batch_year only. No descriptions, websites,
   or founding dates on this page — names only.
**Reusable Pattern:** Yes — small university accelerator pages typically
   list names only. Claude extraction is appropriate here. For descriptions
   and websites, a second enrichment pass visiting each company's
   individual page is required.

---

## Entry 012
**Issue:** Claude response truncated — max_tokens too low
**Root Cause:** Default max_tokens=4096 was insufficient for extracting
   250 companies as JSON. Response cut off mid-array.
**Fix:** Set max_tokens=8192 (Haiku's maximum) for any extraction task
   where output size is unknown or potentially large.
**Reusable Pattern:** Yes — always set max_tokens to model maximum for
   bulk extraction tasks. Truncated JSON silently drops companies at
   the end of the list with no error thrown.

---

## Entry 013
**Site:** Entrepreneur First (joinef.com/portfolio)
**Status:** Working
**Approach:** WordPress admin-ajax.php POST with action=filter, paginated
   by incrementing paged parameter in the query JSON body
**Result:** 467 companies fetched and upserted, zero dropped
**Auth:** None required — public endpoint. Requires realistic User-Agent header.
**Pagination:** POST with paged=1,2,3... until content field is empty
**Fields available:** name, description, founded_year, location, industry tags
**Missing:** website not present in listing view — would require visiting
   each company's individual page to retrieve
**Reusable Pattern:** Yes — WordPress sites commonly use admin-ajax.php
   for dynamic content loading. Action parameter determines what's returned.
   Inspect the Payload tab in DevTools to find the action name and query structure.

---

## Entry 014
**Issue:** EF companies showing only 0.9% AI despite being a deep-tech accelerator
**Root Cause:** EF uses longer industry tag phrases like "Artificial intelligence
   and machine learning" and "Data science" that don't match our keyword list.
   Word-boundary regex works correctly but keywords must match actual tag values.
**Fix:** Expand keyword list to include longer phrases and common variants:
   add 'data science', 'artificial intelligence and machine learning',
   'computer vision', 'robotics', 'autonomous', 'generative'
**Reusable Pattern:** Yes — each source uses different terminology for AI.
   After adding any new source, spot-check AI% against known AI-heavy companies.
   If rate seems wrong, inspect the actual tag/description values and update keywords.

---

## Entry 015
**Issue:** uses_ai detection still undercounting for EF after keyword expansion
**Root Cause:** Two structural limitations:
   1. EF uses the exact phrase "Artificial intelligence and machine learning"
      as a tag — not caught unless added verbatim to keyword list
   2. EF company descriptions are very short one-liners. Companies like
      Hadean (spatial computing) use no AI keywords in their brief description
      even if they are clearly AI-adjacent.
**Fix (partial):** Add "artificial intelligence and machine learning" verbatim
   to keyword list to catch the explicit tag matches.
**Real Fix:** Enrichment pass using Crunchbase/LinkedIn APIs will provide
   fuller descriptions, enabling more accurate classification at that stage.
   uses_ai should be treated as a best-effort field until enrichment runs.
**Reusable Pattern:** Yes — short listing descriptions will always undercount
   AI usage. Flag uses_ai as low-confidence for sources with one-liner
   descriptions. Enrichment is the correct fix, not increasingly complex keywords.

---

## Entry 016
**Issue:** Anthropic API returning 529 Overloaded error
**Root Cause:** Anthropic server-side capacity issue, not a code problem.
   Transient — usually resolves within seconds to minutes.
**Fix:** Retry with exponential backoff. Wait 10 seconds, retry up to 3 times.
**Reusable Pattern:** Yes — always wrap API calls in retry logic for
   production pipelines. Never let a transient 529 fail a long scraping run.

---

## Entry 017
**Site:** Seedcamp (seedcamp.com/companies/)
**Status:** Working
**Approach:** BeautifulSoup on server-rendered WordPress page
**Result:** TBD
**Notes:** Portfolio at /companies/ (not /portfolio — 404). Single ~441KB
   HTML payload loads all 550+ companies — no pagination needed. Each
   company is in div.company__item. CSS classes on the div include sector
   tags (ai, climate, fintech, etc.) used for client-side filtering — useful
   for supplementing AI detection.
**Fields available:** name, description, website, year_of_investment,
   sector_tags (from CSS classes)
**Missing:** location, founded_year, batch, employee_count, funding_amount
**Selectors:**
   - Name: span.company__item__name
   - Year: h6.company__item__year
   - Description: div.company__item__description__content
   - Website: a.company__item__link[href]
   - Sector tags: CSS classes on div.company__item (e.g. 'ai', 'climate')
**Reusable Pattern:** Yes — client-side filter sites often embed all data
   in the initial HTML payload with CSS classes as category labels. No API
   call needed — parse the classes directly as tags.

---

## Entry 018
**Site:** Seedcamp (seedcamp.com/companies/)
**Status:** Working
**Approach:** BeautifulSoup — server-rendered WordPress, single HTML payload
**Result:** 317 companies fetched and upserted, zero dropped
**AI detection:** 27.8% — Seedcamp uses a CSS class `ai` on company divs
   as a ground-truth category tag, catching AI companies that don't have
   keywords in their short description. More reliable than keyword matching alone.
**Discrepancy:** Scout estimated 550+ companies from raw text — actual
   structured parse returned 317. Featured tile--company blocks at top use
   different markup and were likely inflating the scout's estimate. The 317
   from structured parsing is the reliable number.
**Note:** Some companies may be hidden behind login or not yet listed.
   Worth re-checking periodically.
**Discovered by:** Scout agent — first autonomous source discovery
**Reusable Pattern:** When a site uses CSS classes for category filtering
   (e.g. class="ai" or class="fintech"), these are more reliable for
   uses_ai detection than keyword matching. Always check for category
   CSS classes before relying on text keywords.

---

## Entry 019
**Source:** Crunchbase bulk data export (parquet files)
**Status:** Working
**Approach:** Pandas parquet import with bulk_upsert() — not a scraper
**Files:** organizations.parquet (1.15GB), organization_descriptions.parquet (545MB)
**Filters applied:**
  - roles contains 'company'
  - status in ['operating', 'ipo']
  - founded_on year >= 2015
  - name not null
  - short_description OR total_funding_usd not null
**Result:** 744,484 rows after filtering, 723,391 upserted (duplicates
   resolved by UNIQUE name+source constraint), 6.6% flagged as AI
**Fields available:** name, short_description, long_description (joined),
   founded_year, website, category_list, category_groups_list,
   employee_count, total_funding_usd, linkedin_url, twitter_url, status
**Join:** organization_descriptions joined on uuid, 53% match rate
**Performance:** 79.7 seconds for 744k rows using bulk executemany
   in batches of 10,000
**Reusable Pattern:** For bulk file imports, always use executemany
   over row-by-row inserts. 10,000 row batches is a good default.
   Always filter before importing — raw Crunchbase has 3.8M rows,
   filtering to 744k saves significant time and storage.

---

## Entry 020
**Issue:** AI percentage seemingly low at 6.6% for Crunchbase
**Root Cause:** Not actually a bug — Crunchbase covers all industries
   broadly. 6.6% AI across 723k startups spanning fintech, healthcare,
   climate, consumer, logistics etc. is realistic. Accelerator sources
   (YC 22.8%, Techstars 30.1%) are high because they actively select
   for tech companies — not representative of the broader ecosystem.
**Reusable Pattern:** Always calibrate AI% expectations against the
   source type. Curated tech accelerators will always show higher AI%
   than broad startup databases. Neither is wrong — they reflect
   different populations.

---

## Entry 022
**Site:** StartX (web.startx.com/community)
**Status:** Approved
**Backend:** Webflow CMS with Finsweet list pagination
**Approach:** BeautifulSoup + requests, paginated GET
**URL:** https://web.startx.com/community (not startx.com/companies — that's an Angular SPA, 404s on API probes)
**Pagination:** GET ?6a151520_page=N, increment until response contains no div.comn-list-item elements
**Selectors:**
   - Container : div.comn-list-item
   - Name      : [fs-list-field='title']
   - Description: p[fs-list-field='description']
   - Batch/Session: [fs-list-field='session']
   - Industry  : all [fs-list-field='industry'] values (may be multiple)
   - Year      : [fs-list-field='year']
   - Website   : first a.comn-list-link[href]
**Notes:** startx.com/companies is a separate Angular SPA — scout was
   correct to flag it. Actual portfolio lives on web.startx.com, a
   separate Webflow site. Finsweet CMS List pagination uses a hashed
   query param (6a151520_page) — value is stable and doesn't need to
   be discovered dynamically. All data is server-rendered in the HTML
   chunk returned per page request.
**Reusable Pattern:** When the primary domain is a JS SPA, check for a
   separate subdomain (web., app., etc.) hosting the same content on a
   simpler stack. Finsweet CMS List pagination uses a hashed page param —
   find it in the Network tab and it can be incremented directly.

---

## Entry 023
**Site:** StartX (web.startx.com/community)
**Status:** Approved — discovered via manual DevTools investigation after scout flagged
**Backend:** Webflow CMS with Finsweet list pagination
**Scout behavior:** Correctly flagged startx.com as Angular SPA with no accessible API.
   Manual DevTools investigation revealed data lives on separate subdomain web.startx.com
   as a Webflow site with server-rendered HTML chunks.
**Pagination:** GET ?6a151520_page=N — Finsweet hashed pagination param, increment until
   no comn-list-item divs returned
**Fields:** name, description, session/batch, industry tags, year, website
**Reusable Pattern:** When scout flags a JS SPA, check for subdomains — the actual
   data may live on a separate server-rendered subdomain. Also: Finsweet CMS attributes
   (fs-list-field, fs-list-value) are reliable CSS selectors for Webflow sites.

---

## Entry 024
**Site:** StartX (web.startx.com/community)
**Status:** Working
**Result:** 1,313 companies fetched and upserted, zero dropped
**Pagination:** 54 pages at 25 companies each, stopped at page 54
**Fields:** name, description, batch (session), tags (industry),
   founded_year (cohort year — not actual founding date), website
**AI detection issue:** Initial run showed 1.2% — too low. 'AI' keyword
   not matching due to missing standalone term in keyword list (re.IGNORECASE
   was already correct). Fixed by adding 'ai' explicitly to AI_KEYWORDS.
**Result after fix:** 10.6% (139/1,313)
**Reusable Pattern:** Always test AI detection against obvious cases in
   sample output before accepting results. Short keywords like 'AI' are
   especially sensitive — re.IGNORECASE handles case but the term must
   actually be in the keyword list as a standalone entry.

---

## Entry 029
**Site:** Oxford Foundry (oxfordfoundry.ox.ac.uk/portfolio)
**Status:** Skipped — low ROI
**Findings:** URL redirects to sbs.ox.ac.uk (Oxford Saïd Business School). Page shows only 4 cohorts (2018–2021) with companies on separate subpages. Program appears to have wound down — ~40–50 companies total across all cohorts.
**Reusable Pattern:** Always verify in browser before building a scraper. University accelerator programs sometimes wind down — check if the program is still active before investing time.

---

## Entry 028
**Site:** Antler (antler.co/portfolio)
**Status:** Approved — scraper at `scrapers/antler_scraper.py`
**Backend:** Webflow CMS with Finsweet cmslist (GET-based static pagination)
**Approach:** BeautifulSoup — no JavaScript required
**How pagination works:** Static GET param `?0b933bfd_page=N` starting from page 1. The hash key is Webflow-generated and could change — detect it dynamically from the `a.w-pagination-next[href]` link on each page rather than hardcoding. Stop when no next-page link is present. ~52 cards per page.
**Selectors:** Card container `div.portco_card` (inside `div.portco_cms_wrap`). Name: `p[fs-cmsfilter-field="name"]`. Description: `p[fs-cmsfilter-field="description"]`. Tags: `div.tag_small_wrap` elements — distinguish by their `fs-cmsfilter-field`: `"sector"` → sector, `"year"` → year, anything else → location. Website: `a.clickable_link[href]`.
**Correction from previous assessment:** Earlier scouting flagged this as requiring Playwright (cmsload/cmsfilter pattern). The live portfolio page actually uses Finsweet cmslist with interceptable GET pagination — BeautifulSoup works fine.
**Reusable Pattern:** Webflow/Finsweet sites are not uniformly scrapeable via GET requests. Check which Finsweet attributes are present before assuming Playwright is needed:
   - `@finsweet/attributes-cmslist` → exposes `?hash_page=N` GET pagination (StartX, Antler — works with requests)
   - `@finsweet/attributes-cmsload` + `cmsfilter` → internal loading, no accessible URL (requires Playwright)

---

## Entry 027
**Pattern:** Pagination investigation — always try both styles before giving up
**Context:** General scraping pattern, not site-specific
**Issue:** `?page=2` returns identical content to page 1 → incorrectly concluding pagination is API-only
**Fix:** When query-param pagination appears to have no effect, also try path-based variants before concluding a site requires API-level access:
   - Query params: `?page=2`, `?p=2`, `?offset=100`
   - Path-based: `/p2`, `/page/2`, `/page-2`
**Example:** Harvard Innovation Labs uses `/ventures/p2` — scout tried `?page=2`, got identical results, and incorrectly concluded URL pagination had no effect.
**Reusable Pattern:** Path-based pagination is common on WordPress, Drupal, and custom university CMS builds. Always try both styles before escalating to API investigation.

---

## Entry 026
**Site:** Harvard Innovation Labs (innovationlabs.harvard.edu/ventures)
**Status:** Working
**Approach:** BeautifulSoup — server-rendered, path-based pagination at /ventures/p2, /ventures/p3
**Result:** 814 companies fetched and upserted, zero dropped
**Pagination gotcha:** Scout tried `?page=2` — returns same first page. Real pattern is
   path-based `/pN` suffix, not a query param. Always verify by watching URL change in
   browser as you navigate pages.
**Algolia false positive:** Algolia meta tag present but DevTools confirms zero XHR calls.
   Server renders the Algolia results directly — single fetch per page is sufficient.
   No credentials needed.
**Lab affiliation:** Cards carry a second CSS class indicating the program
   (student-i-lab, launch-lab, pagliuca-harvard-life-lab, no-lab-affiliation).
   Stored as batch and in extra.lab.
**Fields available:** name, description, lab_affiliation
**Missing:** website, founded_year, location, industry tags — not in listing view
**AI detection:** 20.5% (167/814) via keyword regex on description
**Reusable Pattern:** When company count in initial HTML doesn't match site's stated
   total, check for path-based pagination (/p2, /p3) not just query param (?page=2).
   When Algolia is detected but no XHR fires, the server is doing the Algolia call —
   treat the page as plain server-rendered HTML and paginate normally.

---

## Entry 025
**Issue:** 'ai' missing from keyword list — 17,146 rows incorrectly
   flagged as uses_ai=false across all sources
**Root Cause:** Keyword list had 'artificial intelligence' but not the
   standalone abbreviation 'ai'. Word-boundary regex with re.IGNORECASE
   correctly handles case, but the keyword itself was absent.
**Fix:** Added 'ai' to global keyword list in all scrapers. Wrote
   scripts/reeval_uses_ai.py to retrospectively update all existing rows.
**Impact by source:**
   - crunchbase: 6.6% → 8.8% (+15,920 rows)
   - yc: 22.8% → 37.2% (+760 rows)
   - techstars: 30.1% → 36.0% (+301 rows)
   - entrepreneur_first: 4.3% → 38.8% (+161 rows)
   - seedcamp: 27.8% → 29.0% (+4 rows)
**Validation:** Spot-checked YC apparent false positives — all confirmed
   correct via tags (Artificial Intelligence, Computer Vision,
   AI-Enhanced Learning etc.) even when one-liner descriptions don't
   mention AI. SQL spot-check must include tags column, not just description.
**Reusable Pattern:** After any keyword change, always run reeval script
   against full dataset. Always spot-check both directions — false
   positives AND false negatives — before accepting new AI percentages.
   When verifying uses_ai, check tags field as well as description — tags
   are often the signal source for companies with short descriptions.

---

## Entry princeton_keller
**Site:** Princeton Keller Center eLab (kellercenter.princeton.edu)
**Status:** Approved
**Backend:** Drupal CMS — fully server-rendered HTML, no API
**Approach:** BeautifulSoup, two-pass (listing pages + detail pages)
**Listing URL:** `https://kellercenter.princeton.edu/people/teams-startups-filtered?program-filter%5B18%5D=18`
**Pagination:** `&page=0` through `&page=8` — 9 pages total. Page 0 is the base URL (no param needed).
**Pass 1 — listing pages:** Each `div.views-row` contains: name (title link), short description, program track (eLab Accelerator / eLab Incubator), cohort year, and a slug linking to the detail page at `/people/startups-teams/{slug}`.
**Pass 2 — detail pages:** Fetch each detail URL to get the full description from `div.field--name-body` or `div.field-name-body`. Much longer than the listing snippet — use this for `description` and AI detection.
**Field mapping:** name → name, full description → description, cohort year → batch, program track → extra.program_track
**Fields available:** name, description (full), batch (cohort year), program_track
**Missing:** website (not present anywhere on site), founded_year, location
**AI detection:** keyword_regex on full description — reliable since descriptions are substantive
**Rate limit:** 1.5s between requests — university server, be polite
**Reusable Pattern:** Drupal Views pages use `div.views-row` as the card container. Field selectors follow `views-field-{field-name}` and `field--name-{field-name}` patterns. When short listing descriptions exist alongside detail pages, always do a second pass for full descriptions — AI detection accuracy depends on it.

---

## Entry columbia
**Site:** Columbia Entrepreneurship Startup Directory (startups.columbia.edu)
**Status:** Approved
**Backend:** REST API — no auth required
**Approach:** Paginated GET requests
**Scraper:** `scrapers/columbia_scraper.py`
**Endpoint:** `GET /api/organizations?role=company&page_idx=N&sort=latest_update`
**Pagination:** `page_idx` is 1-indexed; fetch page 1 first to read `meta.page_count`, then loop 2..page_count. Stop early if `organizations` is empty.
**Response shape:** `{"meta": {"page": 1, "page_count": 311, "total": 6202}, "organizations": [...]}`
**Fields available:** name, homepage_url (website), founded_on (year extracted), total_funding_usd, last_funding_event (series, money_raised_usd, announced_on)
**Missing:** description, batch/cohort, location — not available from this endpoint
**AI detection:** keyword regex on company name only (no description available — low confidence)
**Scout note:** Site is a fully JS-rendered SPA returning a 940-byte HTML shell on all routes — no content visible via static fetch. API discovered via DevTools Network tab. Session cookies present in browser requests but not enforced server-side — no auth required.

---

## Pattern: SPA with hidden REST API

Sites that return a tiny HTML shell (under 2KB) with no links or content are fully JS-rendered SPAs. The scout cannot extract data via static fetch. However, many SPAs load their data from a clean REST or GraphQL API that requires no authentication. To find it:
1. Open the site in Chrome DevTools → Network tab → filter by Fetch/XHR
2. Reload the page and look for API calls (often /api/*, /graphql, or third-party services like Airtable)
3. Copy the request URL and test it directly — if it returns JSON without auth, it's scrapeable
4. Check if pagination is via page_idx, page, offset, or cursor params

Example: startups.columbia.edu returns 940 bytes of HTML but has a clean API at /api/organizations?role=company&page_idx=N

---

## Entry rice_owlspark
**Site:** Rice Alliance OwlSpark (alliance.rice.edu/owlspark/ventures)
**Status:** Approved
**Backend:** Static HTML — single page, no API, no pagination
**Approach:** BeautifulSoup
**Scraper:** `scrapers/rice_owlspark_scraper.py`
**Notes:** All cohort companies in one HTML payload inside a CSS accordion widget. Each accordion item contains a `span.item-title` header (e.g. "Class 13 | May 15 - August 1, 2025") and a `div.accordion-panel > ul > li` list of companies. Name is in a `<strong>` tag; description is the full `li` text. Cohort year extracted from the 4-digit year in the date range. Older classes (pre-2023) have only names — links or plain text, no descriptions. Some cohort headers list two class numbers (e.g. "Class 11, Class 2") — stored as-is in the batch field.
**Fields available:** name, description (newer classes only), batch, cohort_year
**Missing:** website, founded_year, location

---

## Entry founders_factory
**Site:** Founders Factory (foundersfactory.com/portfolio)
**Status:** Skipped — requires Playwright
**Findings:** JS-rendered portfolio with a Load More button. Only ~30 of 450+ companies are visible in the initial HTML payload. No Algolia, Typesense, WordPress REST API, or `__NEXT_DATA__` JSON blob detected. All pagination and filtering is client-side with no observable API endpoint. Would require Playwright headless browser to scrape fully. Skipped as low ROI given the engineering overhead.
**Fields available:** name, description, sector
**Missing:** website, founded_year, batch, location

---

## Entry skydeck
**Site:** Berkeley SkyDeck (skydeck.berkeley.edu)
**Status:** Approved
**Backend:** WordPress admin-ajax.php with action=company_filtration_query
**Approach:** Single POST request — returns all 800+ companies in one JSON response, no pagination
**Endpoint:** `https://skydeck.berkeley.edu/wp-admin/admin-ajax.php`
**Auth:** None — public endpoint. Requires `X-Requested-With: XMLHttpRequest` header.
**POST payload (list of tuples — NOT a dict):**
   - `("action", "company_filtration_query")`
   - `("meta[0][]", "main_industry")`, `("meta[0][]", "all")`
   - `("meta[1][]", "classes")`, `("meta[1][]", "all")`
   - `("meta[2][]", "industry")`, `("meta[2][]", "all")`
   - `("search", "")`
**Response shape:** `{"posts": [{"title": "...", "url": "...", "class": "Batch N"}, ...]}`
**Field mapping:** title → name, url → website, class → batch
**Fields available:** name, website, batch
**Missing:** description, founded_year, location — not available from this endpoint
**AI detection:** keyword_regex on company name only (no description available — low confidence)
**Key gotcha:** POST params include duplicate keys (meta[0][], meta[1][], meta[2][]).
   Python dicts cannot represent duplicate keys — must use `data=[(key, val), ...]`
   (list of tuples) with requests. Using a dict will silently drop all but the last
   value for each key, breaking the filter query.
**Reusable Pattern:** When a WordPress AJAX endpoint uses duplicate-key POST params,
   always send as a list of tuples to requests. Check the Payload tab in DevTools —
   if you see repeated keys like `meta[0][]` appearing twice, a dict will not work.

---
