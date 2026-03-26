# Name-Only Enrichment Guide

Complete guide to automatically enriching company data when you only have names from accelerators.

## Problem

Many accelerators (see [DIFFICULT_ACCELERATORS.md](../DIFFICULT_ACCELERATORS.md)) only display:
- ✅ Company names
- ✅ Logos
- ❌ No descriptions
- ❌ No websites
- ❌ No batch/cohort dates
- ❌ No metadata

Examples:
- **StartX**: 500+ companies, just names and logos
- **Village Global**: Minimal metadata per company
- **Plug and Play**: Heavily obfuscated with no accessible data
- **Capital Factory**: 500+ companies, no batch dates

## Solution: Automatic Enrichment

Two-stage process:
1. **Scrape names** from portfolio page (or import from CSV)
2. **Automatically enrich** each company by searching multiple sources

## Quick Start

### Option 1: Interactive Mode (Easiest)

```bash
cd ai_startup_scraper
python scripts/enrich_name_only_companies.py --interactive
```

Enter company names one by one, then the script automatically finds their data.

### Option 2: From CSV File

Create a CSV with company names:
```csv
name,batch,source
Acme Corp,W24,Y Combinator
TechStartup,2025,StartX
DataAI Inc,S24,Y Combinator
```

Then run:
```bash
python scripts/enrich_name_only_companies.py --csv data/companies.csv --batch "2025" --accelerator "StartX"
```

### Option 3: Scrape + Enrich in One Step

```python
from scrapers.name_only_scraper import NameOnlyScraper

scraper = NameOnlyScraper(
    accelerator_name="StartX",
    portfolio_url="https://startx.com/companies",
    selector=".company-name"  # CSS selector for company names
)

enriched_companies = scraper.scrape_and_enrich(batch="2025", limit=50)
```

## How It Works

### CompanyEnricher Class

The enricher automatically searches multiple sources:

```python
from utils.company_enricher import CompanyEnricher

enricher = CompanyEnricher()
data = enricher.enrich("Anthropic")
```

**Search Strategy (in order):**
1. **Domain Search** - Try common patterns (company.com, company.ai, company.io, etc.)
2. **Website Scraping** - Extract description, social links, contact info
3. **LinkedIn Search** - Find company LinkedIn page
4. **Crunchbase Search** - Find funding and company data
5. **Google Search** - Use contextual search with accelerator name

**What It Extracts:**
- ✅ Website URL
- ✅ Company description/tagline
- ✅ LinkedIn company page
- ✅ Twitter/X account
- ✅ GitHub organization
- ✅ Contact email
- ✅ AI relevance detection
- ✅ Stealth mode detection
- ✅ Data completeness score

### Stealth Detection

Automatically detects if company is in stealth mode:

**Stealth Indicators:**
- No website found (or returns 404/403)
- Parked/placeholder domain ("coming soon", "under construction")
- No description or very short description (<30 chars)
- No social media presence (LinkedIn, Twitter)
- Description contains stealth keywords
- Very low data completeness score (<0.2)

**Classification:**
- Stealth if 2+ indicators present
- `is_stealth_mode: True`
- `stealth_indicators` field lists reasons

### Data Completeness Score

Score from 0.0 to 1.0 based on found data:

```python
Weights:
- website: 0.3
- description: 0.25
- linkedin: 0.15
- twitter: 0.1
- contact_email: 0.1
- crunchbase_url: 0.1
```

**Interpretation:**
- `0.8-1.0` - Excellent (all major data found)
- `0.5-0.8` - Good (website + description found)
- `0.2-0.5` - Partial (some data found)
- `0.0-0.2` - Poor (likely stealth mode)

## Usage Examples

### Example 1: StartX Portfolio (Name-Only)

StartX shows 500+ companies with only names and logos.

```python
from scrapers.name_only_scraper import StartXScraper

scraper = StartXScraper()
companies = scraper.scrape_and_enrich(batch="2025", limit=50)

# Automatically saves to data/ai_startups.csv
```

### Example 2: Manual Name List

```python
from utils.company_enricher import CompanyEnricher
from utils.data_manager import DataManager

companies = [
    "Anthropic",
    "OpenAI",
    "Scale AI",
    "Hugging Face"
]

enricher = CompanyEnricher()
enriched = enricher.batch_enrich(companies, accelerator="Custom List")

# Save to database
dm = DataManager()
for company in enriched:
    dm.add_startup(company)
dm.save()
```

### Example 3: CSV Import

Create `data/startx_names.csv`:
```csv
name
Anthropic
Applied Intuition
Cleerly
Descript
Gusto
Lattice
Snowflake
```

Then run:
```bash
python scripts/enrich_name_only_companies.py \
    --csv data/startx_names.csv \
    --batch "2025" \
    --accelerator "StartX" \
    --output data/startx_enriched.csv
```

### Example 4: Custom Accelerator

```python
from scrapers.name_only_scraper import NameOnlyScraper

scraper = NameOnlyScraper(
    accelerator_name="My Custom Accelerator",
    portfolio_url="https://myaccelerator.com/portfolio",
    selector="h3.company-name"  # CSS selector for company names
)

# Automatically scrapes names, then enriches each one
companies = scraper.scrape_and_enrich(batch="Q1 2025")
```

### Example 5: Handle Existing Data with Missing Info

```python
import pandas as pd
from utils.company_enricher import CompanyEnricher
from utils.data_manager import DataManager

# Load existing data
df = pd.read_csv('data/ai_startups.csv')

# Find companies missing website or description
incomplete = df[
    (df['website'].isna() | (df['website'] == '')) |
    (df['description'].isna() | (df['description'] == ''))
]

print(f"Found {len(incomplete)} companies with incomplete data")

# Re-enrich them
enricher = CompanyEnricher()
dm = DataManager()

for _, company in incomplete.iterrows():
    print(f"Re-enriching: {company['startup_name']}")
    enriched = enricher.enrich(
        company['startup_name'],
        batch=company.get('batch'),
        accelerator=company.get('source')
    )
    dm.add_startup(enriched)

dm.save()
```

## Rate Limiting & Performance

### Default Behavior
- 2 second delay between companies
- 2 second delay between sources per company
- ~6-8 seconds per company total

### Processing Time Estimates
- 10 companies: ~1-2 minutes
- 50 companies: ~5-7 minutes
- 100 companies: ~10-15 minutes
- 500 companies: ~50-75 minutes

### Adjust Rate Limiting

```python
# Faster (risky - may get blocked)
enricher = CompanyEnricher(rate_limit_delay=0.5)

# Slower (safer for large batches)
enricher = CompanyEnricher(rate_limit_delay=5)
```

## Best Practices

### 1. Start Small
Test with 5-10 companies first to verify it works for your data.

```bash
python scripts/enrich_name_only_companies.py --interactive
# Enter 5 test companies
```

### 2. Use Batches for Large Lists
Process 50-100 companies at a time, not 500+ in one run.

```python
companies = load_all_companies()  # 500 companies

# Process in batches
for i in range(0, len(companies), 50):
    batch = companies[i:i+50]
    enricher.batch_enrich(batch)
    time.sleep(60)  # 1 minute between batches
```

### 3. Re-Enrich Stealth Companies Later

```python
# Find stealth companies
stealth = df[df['is_stealth_mode'] == True]

# Re-check them after 3 months
# Many stealth startups launch within 3-6 months
```

### 4. Manual Review for High-Value Companies
Check the top companies manually - automated enrichment isn't perfect.

### 5. Handle Rate Limiting Gracefully

```python
try:
    enriched = enricher.enrich(company_name)
except Exception as e:
    if "429" in str(e) or "rate limit" in str(e).lower():
        print("Rate limited, waiting 60 seconds...")
        time.sleep(60)
        enriched = enricher.enrich(company_name)
```

## Limitations & Considerations

### What Works Well ✅
- Companies with standard domain names (company.com)
- Companies with active websites
- Companies with LinkedIn presence
- Recently launched companies with press coverage

### What's Challenging ❌
- **Common names** ("Apple", "Meta") - may find wrong company
- **Rebranded companies** - old name doesn't match new website
- **Acquired/shut down companies** - may find acquirer's site
- **International companies** - non-English websites harder to parse
- **True stealth companies** - no public presence anywhere
- **Rate limiting** - LinkedIn, Google heavily rate limit scrapers

### Accuracy Estimates
- Website found: ~70-80% success rate
- Description found: ~60-70%
- Social links found: ~50-60%
- Stealth detection: ~85-90% accurate

### Legal & Ethical Considerations
- **Respect robots.txt**: Some sites block automated access
- **Rate limiting**: Don't hammer websites with rapid requests
- **Terms of Service**: Some sites prohibit scraping (LinkedIn, Crunchbase)
- **API alternatives**: Use official APIs when available (Crunchbase, etc.)
- **Data accuracy**: Always verify critical data manually

## Troubleshooting

### "No website found" for known companies

**Possible reasons:**
1. Domain doesn't match company name pattern
2. Company rebranded (old name, new domain)
3. Domain uses uncommon TLD (.xyz, .tech, etc.)

**Solution:** Manually add website, or check if company uses different name online.

### Rate limiting errors (403, 429)

**Solution:**
```python
# Increase delay between requests
enricher = CompanyEnricher(rate_limit_delay=5)

# Or pause and resume later
enricher.batch_enrich(companies[:50])
time.sleep(300)  # 5 minute pause
enricher.batch_enrich(companies[50:100])
```

### Wrong company found (name collision)

**Solution:** Add accelerator context to help disambiguation:
```python
enricher.enrich("Meta", accelerator="Y Combinator", batch="W24")
# Helps distinguish from Facebook's Meta
```

### LinkedIn not found

LinkedIn heavily rate limits. Solutions:
- Use official LinkedIn API (requires partnership)
- Manual lookup for high-priority companies
- Accept that LinkedIn data may be incomplete

### Very slow performance

**Solutions:**
1. Reduce rate limiting delay (risky):
   ```python
   enricher = CompanyEnricher(rate_limit_delay=1)
   ```

2. Skip certain sources:
   ```python
   # Modify company_enricher.py to skip slow sources
   # Comment out LinkedIn or Crunchbase search
   ```

3. Parallel processing (advanced):
   ```python
   from concurrent.futures import ThreadPoolExecutor

   with ThreadPoolExecutor(max_workers=3) as executor:
       results = executor.map(enricher.enrich, companies)
   ```

## Integration with Existing Scrapers

### Add to main.py

```python
# main.py
from scrapers.name_only_scraper import StartXScraper

if 'startx' in sources:
    scraper = StartXScraper()
    startups = scraper.scrape_and_enrich(batch=batch, limit=limit)
    for startup in startups:
        data_manager.add_startup(startup)
```

### Use with Difficult Accelerators

For accelerators in [DIFFICULT_ACCELERATORS.md](../DIFFICULT_ACCELERATORS.md) that only show names:

```python
from scrapers.name_only_scraper import NameOnlyScraper

# Plug and Play (Tier 1 - Very difficult)
scraper = NameOnlyScraper(
    "Plug and Play",
    "https://www.plugandplaytechcenter.com/companies/",
    selector=None  # Auto-detect
)

# Village Global (Tier 3)
scraper = NameOnlyScraper(
    "Village Global",
    "https://www.villageglobal.com/portfolio",
    selector="h3"
)

# Capital Factory (Tier 3)
scraper = NameOnlyScraper(
    "Capital Factory",
    "https://capitalfactory.com/portfolio/",
    selector=".company-name"
)
```

## Output Format

Enriched data includes all standard fields plus:

```python
{
    'startup_name': 'Anthropic',
    'website': 'https://anthropic.com',
    'description': 'AI safety and research company',
    'linkedin': 'https://linkedin.com/company/anthropic',
    'twitter': 'https://twitter.com/anthropicai',
    'github': 'https://github.com/anthropics',
    'contact_email': 'hello@anthropic.com',
    'batch': '2021',
    'source': 'StartX',

    # Enrichment metadata
    'is_stealth_mode': False,
    'stealth_indicators': None,
    'data_completeness_score': 0.85,

    # AI detection
    'is_ai_related': True,
    'ai_confidence_score': 0.95,

    # Timestamps
    'scraped_date': '2026-02-09 14:30:00'
}
```

## Advanced Usage

### Custom Search Strategy

```python
class CustomEnricher(CompanyEnricher):
    def enrich(self, company_name, **kwargs):
        # Your custom search logic
        data = super().enrich(company_name, **kwargs)

        # Add custom sources
        custom_data = self._search_my_custom_source(company_name)
        data.update(custom_data)

        return data
```

### Parallel Processing

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def enrich_parallel(companies, max_workers=3):
    enricher = CompanyEnricher()
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_company = {
            executor.submit(enricher.enrich, company): company
            for company in companies
        }

        for future in as_completed(future_to_company):
            company = future_to_company[future]
            try:
                data = future.result()
                results.append(data)
            except Exception as e:
                print(f"Error enriching {company}: {e}")

    return results
```

### Scheduled Re-Enrichment

```python
import schedule
import time

def reenrich_stealth_companies():
    """Re-check stealth companies weekly"""
    df = pd.read_csv('data/ai_startups.csv')
    stealth = df[df['is_stealth_mode'] == True]

    enricher = CompanyEnricher()
    dm = DataManager()

    for _, company in stealth.iterrows():
        enriched = enricher.enrich(company['startup_name'])
        dm.add_startup(enriched)

    dm.save()

# Run every Sunday at 2am
schedule.every().sunday.at("02:00").do(reenrich_stealth_companies)

while True:
    schedule.run_pending()
    time.sleep(3600)
```

## Next Steps

1. **Test the enricher**: Run interactive mode with 5 companies
2. **Try an accelerator**: Use pre-built StartX scraper
3. **Import your data**: Use CSV import for existing name lists
4. **Build custom scraper**: Adapt NameOnlyScraper for your accelerator
5. **Schedule re-enrichment**: Set up weekly checks for stealth companies

## Related Documentation

- [DIFFICULT_ACCELERATORS.md](../DIFFICULT_ACCELERATORS.md) - Catalog of challenging accelerators
- [SCRAPING_STRATEGIES.md](../SCRAPING_STRATEGIES.md) - Advanced scraping techniques
- [README.md](../README.md) - Main project documentation
- [utils/company_enricher.py](../utils/company_enricher.py) - Enricher source code
- [scrapers/name_only_scraper.py](../scrapers/name_only_scraper.py) - Name-only scraper source

---

**Last Updated:** 2026-02-09
