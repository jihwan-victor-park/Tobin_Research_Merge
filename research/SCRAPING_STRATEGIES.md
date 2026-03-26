# Scraping Strategies for Difficult Accelerator Portfolios

Comprehensive guide to scraping startup accelerator and incubator portfolios organized by difficulty tier.

**Last Updated:** 2026-02-06

---

## Table of Contents

1. [General Principles](#general-principles)
2. [Tools & Technologies](#tools--technologies)
3. [Tier-Specific Strategies](#tier-specific-strategies)
4. [Code Examples](#code-examples)
5. [Common Pitfalls](#common-pitfalls)
6. [Legal & Ethical Considerations](#legal--ethical-considerations)

---

## General Principles

### The Scraping Hierarchy

Always attempt methods in this order (easiest to hardest):

1. **Public API** - Check for official API documentation
2. **Static HTML** - Simple HTTP requests with BeautifulSoup
3. **Dynamic Content** - Headless browser automation
4. **API Reverse Engineering** - Intercept and replicate internal APIs
5. **Airtable/Database Access** - Find exposed API keys
6. **Manual Data Entry** - Last resort for auth-protected sites

### Universal Best Practices

```python
# Always include these in your scrapers:

1. Rate Limiting
   - time.sleep() between requests (2-5 seconds)
   - Respect robots.txt
   - Use exponential backoff for errors

2. User-Agent Headers
   - Mimic real browsers
   - Rotate user agents if scraping large volumes

3. Error Handling
   - Try/except blocks around all network calls
   - Log failures for later retry
   - Save partial results frequently

4. Data Validation
   - Check for duplicate entries
   - Validate required fields before saving
   - Handle missing data gracefully

5. Respectful Scraping
   - Don't overwhelm servers
   - Scrape during off-peak hours
   - Cache results to avoid re-scraping
```

---

## Tools & Technologies

### Basic Scraping (Static HTML)

```python
# Requirements
pip install requests beautifulsoup4 lxml

# Basic pattern
import requests
from bs4 import BeautifulSoup

response = requests.get(url, headers=HEADERS, timeout=30)
soup = BeautifulSoup(response.content, 'html.parser')
```

**Use for:** Simple portfolio pages with server-side rendering

### Headless Browsers (Dynamic Content)

#### Selenium
```python
# Requirements
pip install selenium webdriver-manager

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Setup
options = webdriver.ChromeOptions()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('user-agent=Mozilla/5.0...')

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)

# Wait for dynamic content
wait = WebDriverWait(driver, 10)
element = wait.until(
    EC.presence_of_element_located((By.CLASS_NAME, "company-card"))
)
```

**Use for:** React, Vue.js, Angular sites

#### Playwright (Recommended for Modern SPAs)
```python
# Requirements
pip install playwright
playwright install

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url)

    # Wait for network idle (better than fixed time)
    page.wait_for_load_state('networkidle')

    # Extract data
    companies = page.query_selector_all('.company-card')

    browser.close()
```

**Use for:** Heavy JavaScript, Next.js, React sites

### API Tools

#### Requests (REST APIs)
```python
# For discovered APIs
import requests

headers = {
    'Authorization': 'Bearer TOKEN',
    'Content-Type': 'application/json'
}

response = requests.get(
    'https://api.example.com/portfolio',
    headers=headers,
    params={'batch': 'W24'}
)

data = response.json()
```

#### Algolia Search Client (Like YC)
```python
# Requirements
pip install algoliasearch

from algoliasearch.search.client import SearchClientSync

client = SearchClientSync(app_id, api_key)
results = client.search_single_index(
    index_name='companies',
    search_params={'query': '', 'hitsPerPage': 100}
)
```

**Use for:** Berkeley SkyDeck, any site using Algolia

#### Airtable API
```python
# Requirements
pip install pyairtable

from pyairtable import Api

api = Api('YOUR_API_KEY')
table = api.table('BASE_ID', 'TABLE_NAME')

# Fetch all records
records = table.all()
```

**Use for:** gener8tor, Pioneer Fund

---

## Tier-Specific Strategies

### Tier 1: No Batch Data + Heavy JavaScript 🔴

**Challenge:** Client-side rendering + zero temporal metadata

#### Strategy A: Headless Browser + External Cross-Reference

```python
"""
For sites like StartX, 500 Global, Techstars
"""
from playwright.sync_api import sync_playwright
import time

def scrape_tier1_accelerator(url, accelerator_name):
    companies = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Navigate and wait
        page.goto(url)
        page.wait_for_load_state('networkidle')

        # Scroll to trigger lazy loading
        for _ in range(10):
            page.evaluate('window.scrollBy(0, 1000)')
            time.sleep(0.5)

        # Extract companies
        company_elements = page.query_selector_all('.company, .portfolio-item, [class*="company"]')

        for elem in company_elements:
            try:
                name = elem.query_selector('h3, h4, .name').inner_text()
                logo = elem.query_selector('img').get_attribute('src')
                link = elem.query_selector('a').get_attribute('href')

                companies.append({
                    'name': name,
                    'logo': logo,
                    'website': link,
                    'source': accelerator_name
                })
            except:
                continue

        browser.close()

    return companies

# Usage
companies = scrape_tier1_accelerator(
    'https://startx.com/companies',
    'StartX'
)
```

#### Strategy B: API Reverse Engineering

```python
"""
Intercept network requests to find hidden APIs
"""
from playwright.sync_api import sync_playwright
import json

def intercept_api_calls(url):
    api_data = []

    def handle_response(response):
        # Capture JSON responses
        if 'application/json' in response.headers.get('content-type', ''):
            try:
                data = response.json()
                api_data.append({
                    'url': response.url,
                    'data': data
                })
            except:
                pass

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # Listen to all responses
        page.on('response', handle_response)

        page.goto(url)
        page.wait_for_timeout(5000)  # Wait for API calls

        browser.close()

    return api_data

# Analyze captured data
api_calls = intercept_api_calls('https://500.co/companies')
for call in api_calls:
    print(f"API: {call['url']}")
    print(f"Data structure: {call['data'].keys()}")
```

**Batch Data Workaround:**
Since these sites don't expose batch data, cross-reference scraped companies with:
1. TechCrunch/VentureBeat articles mentioning "[Accelerator] Winter 2025 batch"
2. LinkedIn company pages with "StartX 2025" in description
3. Crunchbase filtering by founding year + accelerator affiliation

---

### Tier 2: Authentication Required 🔒

**Challenge:** Need valid credentials to access portfolio

#### Strategy: Authenticated Session Scraping

```python
"""
For sites like On Deck, Neo (Bubble.io based)
"""
from playwright.sync_api import sync_playwright

def scrape_with_auth(url, username, password):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # Show browser for debugging
        context = browser.new_context()
        page = context.new_page()

        # Navigate to login
        page.goto(url)

        # Fill login form (adjust selectors)
        page.fill('input[name="email"]', username)
        page.fill('input[name="password"]', password)
        page.click('button[type="submit"]')

        # Wait for redirect after login
        page.wait_for_url('**/portfolio', timeout=10000)

        # Save cookies for future use
        cookies = context.cookies()
        with open('session_cookies.json', 'w') as f:
            json.dump(cookies, f)

        # Now scrape portfolio
        page.wait_for_selector('.company-card')
        companies = page.query_selector_all('.company-card')

        # ... extract data ...

        browser.close()
        
# Reuse saved session
def scrape_with_saved_session(url):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()

        # Load saved cookies
        with open('session_cookies.json', 'r') as f:
            cookies = json.load(f)
            context.add_cookies(cookies)

        page = context.new_page()
        page.goto(url)
        # ... scrape ...
```

**Important:** Only use this if you have legitimate access to the platform.

---

### Tier 3: Dynamic Loading + Minimal Metadata ⚡

**Challenge:** Infinite scroll, "Load More" buttons, minimal company info

#### Strategy: Automated Scrolling & Clicking

```python
"""
For sites like Capital Factory, MassChallenge, gener8tor
"""
from playwright.sync_api import sync_playwright
import time

def scrape_infinite_scroll(url):
    companies = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)

        previous_height = 0
        while True:
            # Scroll to bottom
            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            time.sleep(2)  # Wait for content to load

            # Check if we've loaded new content
            new_height = page.evaluate('document.body.scrollHeight')
            if new_height == previous_height:
                break  # No more content
            previous_height = new_height

        # Extract all companies after full scroll
        company_elements = page.query_selector_all('.company-card')
        for elem in company_elements:
            # Extract data...
            pass

        browser.close()

    return companies

def scrape_load_more_button(url):
    """For sites with 'Load More' pagination"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)

        while True:
            try:
                # Click "Load More" button
                load_more = page.query_selector('button:has-text("Load More"), .load-more, [class*="load-more"]')
                if not load_more:
                    break

                load_more.click()
                page.wait_for_timeout(2000)  # Wait for new content

            except:
                break  # No more button found

        # Extract all visible companies
        companies = page.query_selector_all('.company-card')
        # ... process ...

        browser.close()
```

#### Strategy: Vue.js/React Data Extraction

```python
"""
Extract data from Vue/React component state
"""
def extract_vue_data(page):
    """For Vue.js sites like gener8tor"""
    vue_data = page.evaluate('''() => {
        // Vue 3
        const app = document.querySelector('#app').__vue_app__;
        return app.config.globalProperties.$data;

        // Or Vue 2
        // return document.querySelector('#app').__vue__.$data;
    }''')
    return vue_data

def extract_react_data(page):
    """For React sites like Techstars"""
    react_data = page.evaluate('''() => {
        // Find React root
        const root = document.querySelector('#root');
        const key = Object.keys(root).find(k => k.startsWith('__reactContainer'));
        return root[key].memoizedState;
    }''')
    return react_data
```

---

### Tier 4: Pagination + Poor Structure 📄

**Challenge:** Multiple pages, inconsistent HTML

#### Strategy: Pagination Loop with Robust Parsing

```python
"""
For sites like Startupbootcamp, Seedcamp, SOSV
"""
import requests
from bs4 import BeautifulSoup

def scrape_paginated_portfolio(base_url, max_pages=None):
    companies = []
    page_num = 1

    while True:
        if max_pages and page_num > max_pages:
            break

        # Construct page URL (adjust pattern)
        url = f"{base_url}?page={page_num}"

        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # Find companies with flexible selectors
            company_cards = soup.find_all(
                ['div', 'article', 'li'],
                class_=lambda x: x and any(
                    keyword in str(x).lower()
                    for keyword in ['company', 'portfolio', 'startup', 'item']
                )
            )

            if not company_cards:
                break  # No more companies found

            for card in company_cards:
                company = extract_with_fallbacks(card)
                if company:
                    companies.append(company)

            print(f"Scraped page {page_num}: {len(company_cards)} companies")
            page_num += 1
            time.sleep(2)  # Rate limiting

        except Exception as e:
            print(f"Error on page {page_num}: {e}")
            break

    return companies

def extract_with_fallbacks(card):
    """Try multiple selectors to handle inconsistent HTML"""
    company = {}

    # Name - try multiple approaches
    name_elem = (
        card.find('h3') or
        card.find('h4') or
        card.find(class_=lambda x: x and 'name' in str(x).lower()) or
        card.find('strong')
    )
    company['name'] = name_elem.get_text(strip=True) if name_elem else None

    # Description - multiple fallbacks
    desc_elem = (
        card.find('p', class_=lambda x: x and 'description' in str(x).lower()) or
        card.find('p') or
        card.find('div', class_='description')
    )
    company['description'] = desc_elem.get_text(strip=True) if desc_elem else None

    # Website - look for links
    link_elem = card.find('a', href=True)
    if link_elem:
        href = link_elem.get('href')
        if href.startswith('http'):
            company['website'] = href

    # Year/Batch - check data attributes and text
    year = (
        card.get('data-year') or
        card.get('data-batch') or
        extract_year_from_text(card.get_text())
    )
    company['year'] = year

    return company if company['name'] else None

def extract_year_from_text(text):
    """Extract 4-digit year from text"""
    import re
    match = re.search(r'\b(20\d{2})\b', text)
    return match.group(1) if match else None
```

---

### Tier 5: Complex Frameworks 🛠️

**Challenge:** Advanced JavaScript frameworks, multiple data sources

#### Strategy A: Antler (Two-Stage Scraping)

```python
"""
Antler has companies on /portfolio and cohort dates on /cohort-start-dates
"""
def scrape_antler():
    # Stage 1: Get all companies
    companies = scrape_infinite_scroll('https://www.antler.co/portfolio')

    # Stage 2: Get cohort dates
    cohort_dates = scrape_cohort_dates('https://www.antler.co/cohort-start-dates')

    # Stage 3: Cross-reference
    for company in companies:
        location = company.get('location')
        for cohort in cohort_dates:
            if cohort['location'] == location:
                # Match companies to cohorts by location and founding date
                if is_date_in_cohort(company['founded'], cohort['dates']):
                    company['cohort'] = cohort['name']

    return companies

def scrape_cohort_dates(url):
    """Extract cohort schedule from separate page"""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url)

        # Extract table or list of cohorts
        cohort_elements = page.query_selector_all('.cohort-row, tr')
        cohorts = []

        for elem in cohort_elements:
            cohorts.append({
                'name': elem.query_selector('.name').inner_text(),
                'location': elem.query_selector('.location').inner_text(),
                'dates': elem.query_selector('.dates').inner_text()
            })

        browser.close()
        return cohorts
```

#### Strategy B: Airtable-Based Sites (gener8tor, Pioneer Fund)

```python
"""
Find and use Airtable API directly
"""
def find_airtable_credentials(url):
    """
    Look for Airtable API calls in browser network traffic
    """
    from playwright.sync_api import sync_playwright

    api_calls = []

    def capture_request(request):
        if 'airtable.com' in request.url:
            api_calls.append({
                'url': request.url,
                'headers': request.headers
            })

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on('request', capture_request)
        page.goto(url)
        page.wait_for_timeout(5000)
        browser.close()

    # Parse discovered API info
    for call in api_calls:
        print(f"Found Airtable call: {call['url']}")
        # Extract base ID and table name from URL
        # Extract API key from Authorization header

    return api_calls

def scrape_via_airtable(base_id, table_name, api_key):
    """
    Use Airtable API directly (much faster than scraping)
    """
    from pyairtable import Api

    api = Api(api_key)
    table = api.table(base_id, table_name)

    # Fetch all records (handles pagination automatically)
    records = table.all()

    companies = []
    for record in records:
        fields = record['fields']
        companies.append({
            'name': fields.get('Name'),
            'description': fields.get('Description'),
            'website': fields.get('Website'),
            'batch': fields.get('Batch'),
            'founded': fields.get('Founded'),
            # ... other fields
        })

    return companies
```

---

## Code Examples

### Complete Scraper Template

```python
"""
Template for building robust accelerator scrapers
"""
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
import json
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AcceleratorScraper:
    def __init__(self, accelerator_name, base_url):
        self.accelerator_name = accelerator_name
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })
        self.companies = []
        self.cache_file = f'cache_{accelerator_name.lower()}.json'

    def scrape(self, limit=None, use_cache=True):
        """Main scraping method"""
        logger.info(f"Starting scrape of {self.accelerator_name}")

        # Check cache
        if use_cache and self.load_cache():
            logger.info(f"Loaded {len(self.companies)} companies from cache")
            return self.companies[:limit] if limit else self.companies

        try:
            # Implement scraping logic
            self._scrape_portfolio()

            # Save cache
            self.save_cache()

        except Exception as e:
            logger.error(f"Error scraping {self.accelerator_name}: {e}")
            raise

        return self.companies[:limit] if limit else self.companies

    def _scrape_portfolio(self):
        """Override this method with specific scraping logic"""
        raise NotImplementedError

    def _extract_company_data(self, element):
        """Extract standardized company data from HTML element"""
        try:
            return {
                'name': self._get_text(element, 'h3, h4, .name'),
                'description': self._get_text(element, 'p, .description'),
                'website': self._get_link(element, 'a'),
                'logo': self._get_image(element, 'img'),
                'batch': None,  # Extract if available
                'founded': None,
                'location': self._get_text(element, '.location'),
                'source': self.accelerator_name,
                'scraped_date': datetime.now().isoformat()
            }
        except Exception as e:
            logger.warning(f"Error extracting company data: {e}")
            return None

    def _get_text(self, element, selector):
        """Safely extract text from element"""
        elem = element.select_one(selector)
        return elem.get_text(strip=True) if elem else None

    def _get_link(self, element, selector):
        """Safely extract href attribute"""
        elem = element.select_one(selector)
        return elem.get('href') if elem else None

    def _get_image(self, element, selector):
        """Safely extract image src"""
        elem = element.select_one(selector)
        return elem.get('src') if elem else None

    def save_cache(self):
        """Save scraped data to cache file"""
        with open(self.cache_file, 'w') as f:
            json.dump(self.companies, f, indent=2)
        logger.info(f"Saved {len(self.companies)} companies to cache")

    def load_cache(self):
        """Load data from cache if it exists"""
        try:
            with open(self.cache_file, 'r') as f:
                self.companies = json.load(f)
            return True
        except FileNotFoundError:
            return False

    def rate_limit(self, seconds=2):
        """Respectful rate limiting"""
        time.sleep(seconds)


# Example implementation for a specific accelerator
class SeedcampScraper(AcceleratorScraper):
    def __init__(self):
        super().__init__('Seedcamp', 'https://seedcamp.com/our-companies/')

    def _scrape_portfolio(self):
        """Seedcamp-specific scraping logic"""
        page = 1
        while True:
            url = f"{self.base_url}?page={page}"
            response = self.session.get(url, timeout=30)
            soup = BeautifulSoup(response.content, 'html.parser')

            company_cards = soup.find_all('div', class_='company-card')
            if not company_cards:
                break

            for card in company_cards:
                company = self._extract_company_data(card)
                if company:
                    self.companies.append(company)
                    logger.info(f"Scraped: {company['name']}")

            page += 1
            self.rate_limit()


# Usage
if __name__ == '__main__':
    scraper = SeedcampScraper()
    companies = scraper.scrape(limit=100)
    print(f"Total companies: {len(companies)}")
```

---

## Common Pitfalls

### 1. Not Waiting for JavaScript

**Problem:**
```python
# This won't work for React/Vue sites
response = requests.get(url)
soup = BeautifulSoup(response.content, 'html.parser')
companies = soup.find_all('.company')  # Returns empty!
```

**Solution:**
```python
# Use headless browser
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(url)
    page.wait_for_selector('.company')  # Wait for content
    companies = page.query_selector_all('.company')
```

### 2. Ignoring Rate Limits

**Problem:**
```python
# Don't do this!
for url in urls:
    scrape(url)  # No delay = banned
```

**Solution:**
```python
import time
import random

for url in urls:
    scrape(url)
    # Random delay between 2-5 seconds
    time.sleep(random.uniform(2, 5))
```

### 3. Not Handling Pagination

**Problem:**
```python
# Only gets first page
companies = scrape_page(url)
```

**Solution:**
```python
# Get all pages
companies = []
page = 1
while True:
    page_companies = scrape_page(f"{url}?page={page}")
    if not page_companies:
        break
    companies.extend(page_companies)
    page += 1
```

### 4. Brittle Selectors

**Problem:**
```python
# Breaks if HTML changes
name = soup.find('div', class_='company-name-header-v2')
```

**Solution:**
```python
# Multiple fallbacks
name = (
    soup.find('div', class_='company-name-header-v2') or
    soup.find('h3', class_='name') or
    soup.find(class_=lambda x: x and 'name' in str(x).lower()) or
    soup.find('h3')
)
```

### 5. Not Caching Results

**Problem:**
```python
# Re-scraping everything every time
companies = scrape_all_companies()  # Takes 30 minutes
```

**Solution:**
```python
import json
from pathlib import Path

CACHE_FILE = 'companies_cache.json'

def scrape_with_cache():
    # Check cache first
    if Path(CACHE_FILE).exists():
        with open(CACHE_FILE) as f:
            return json.load(f)

    # Scrape if no cache
    companies = scrape_all_companies()

    # Save to cache
    with open(CACHE_FILE, 'w') as f:
        json.dump(companies, f)

    return companies
```

---

## Legal & Ethical Considerations

### ✅ Generally Acceptable

1. **Public Data** - Scraping publicly visible portfolio pages
2. **Respectful Rate Limiting** - Not overwhelming servers
3. **robots.txt Compliance** - Respecting crawl directives
4. **Personal/Research Use** - Academic or individual analysis
5. **Attribution** - Citing data sources

### ⚠️ Proceed with Caution

1. **Terms of Service** - Read TOS before scraping
2. **API Alternatives** - Use official APIs when available
3. **Authentication** - Only use if you have legitimate access
4. **Commercial Use** - May require permission
5. **Data Privacy** - Don't scrape personal contact information

### ❌ Never Do This

1. **DDoS-like Behavior** - Overwhelming servers with requests
2. **Credential Theft** - Stealing or sharing login credentials
3. **Bypassing Paywalls** - Circumventing paid access
4. **CFAA Violations** - Accessing systems without authorization (US law)
5. **Reselling Data** - Selling scraped data without rights

### Best Practices

```python
# Check robots.txt first
import urllib.robotparser

def can_scrape(url):
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(f"{url}/robots.txt")
    rp.read()
    return rp.can_fetch("*", url)

if not can_scrape("https://example.com/portfolio"):
    print("Scraping not allowed per robots.txt")
    exit()
```

```python
# Respect rate limits
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def create_session():
    session = requests.Session()

    # Retry on failures
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)

    return session
```

---

## Additional Resources

### Documentation
- [BeautifulSoup Docs](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
- [Playwright Python](https://playwright.dev/python/)
- [Selenium Documentation](https://selenium-python.readthedocs.io/)
- [Scrapy Framework](https://docs.scrapy.org/) (for large-scale projects)

### Tools
- **Browser DevTools** - Inspect network requests, find APIs
- **mitmproxy** - HTTPS interception for API discovery
- **Postman** - Test discovered APIs
- **SelectorGadget** - Chrome extension for CSS selectors

### Learning
- Web Scraping with Python (Book)
- ScrapingHub Blog
- Real Python Web Scraping Tutorials

---

## Maintenance

This document should be updated when:
- New scraping techniques emerge
- Legal frameworks change
- Tools/libraries are updated
- New patterns are discovered

**Last Review:** 2026-02-06
**Next Review:** 2026-05-06


## Personal: Finalize a list of gov programs (country separation)

## Finalize Systematic Website Search with Hits and Nonhits (Universities)
## kept track of those with portfolios

## International Incubator Programs List






## Website is good, also look for company tab/portfolio, boolean




## Work with Victor on scraping more (potential aiccess to SOM server)
## Eventually keep scraper running on cloud server
## Start at 30 days
## Work to identify startup specific companies from REPO: merging with existing CSV files $be creative, what are startups?
## Particularly for Internationals
## JSON > ask Chat > validate results











## Priority List, Last Week
## scrape and organize portco's from universities








## New Meeting and Objectives

## Keep going with universities, potentially 1 by 1:
## Resources
## We still want to figure out up to date stuff
## De-duplicate, merging with other data sources
## Current picture, forward to automate 