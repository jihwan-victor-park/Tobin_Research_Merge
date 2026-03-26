# AI Startup Scraper - Complete Project Overview

**Comprehensive guide to understanding what this project does and how it works**

---

## 🎯 What This Project Does

**AI Startup Scraper** is a comprehensive system that:

1. **Scrapes** startup data from accelerators, incubators, and investment sources
2. **Enriches** company information when only names are available
3. **Detects** which companies are AI-related using keyword analysis
4. **Tracks** stealth startups and data completeness
5. **Analyzes** trends across batches, cohorts, and time periods
6. **Exports** data to CSV for analysis in Excel/Google Sheets/databases

**Primary Use Case:** Build a database of AI startups from multiple sources, even when source data is limited (name-only).

---

## 🏗️ Project Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    INPUT SOURCES                            │
│  Accelerators • Incubators • VC Portfolios • Public APIs   │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                   DATA SCRAPERS                             │
│  • YC Scraper (Algolia API)                                │
│  • SkyDeck Scraper (Algolia API)                           │
│  • StartX Scraper (HTML)                                   │
│  • Name-Only Scraper (Multi-stage enrichment)              │
│  • Generic Scraper (Template for custom sources)           │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                ENRICHMENT LAYER                             │
│  If only names available:                                   │
│  • Domain pattern matching                                  │
│  • Website scraping                                         │
│  • LinkedIn/Crunchbase search                              │
│  • Google search with context                              │
│  • Stealth mode detection                                  │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│              PROCESSING & DETECTION                         │
│  • AI Keyword Detection                                     │
│  • Data Completeness Scoring                               │
│  • Stealth Mode Classification                             │
│  • Data Validation & Cleaning                              │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                  DATA STORAGE                               │
│  • CSV Database (data/ai_startups.csv)                     │
│  • Separate exports per analysis                           │
│  • Progress logs and reports                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure Explained

### Root Directory

```
ai_startup_scraper/
├── main.py                    # Main orchestrator
├── config.py                  # Configuration & settings
├── requirements.txt           # Python dependencies
│
├── README.md                  # Main documentation
├── PROJECT_OVERVIEW.md        # This file
├── ENRICHMENT_QUICKSTART.md   # Self-service guide
├── ENRICHMENT_CHEATSHEET.txt  # Quick commands
│
├── DIFFICULT_ACCELERATORS.md  # 20 hard-to-scrape sources
├── SCRAPING_STRATEGIES.md     # Advanced techniques
│
├── scrapers/                  # Data source scrapers
├── utils/                     # Utility modules
├── scripts/                   # Analysis & enrichment
├── data/                      # Output & storage
└── docs/                      # Analysis documents
```

---

## 🔧 Core Components

### 1. **Main Orchestrator** (`main.py`)

**Purpose:** Command-line interface to run scrapers

**What it does:**
- Accepts command-line arguments (`--sources`, `--limit`, `--ai-only`)
- Initializes appropriate scrapers
- Coordinates scraping from multiple sources
- Saves results to database

**Usage:**
```bash
# Scrape Y Combinator
python main.py --sources yc --limit 100

# Scrape multiple sources
python main.py --sources yc startx skydeck --ai-only

# Scrape everything
python main.py --all
```

**When to use:** Regular scraping from supported sources with full data available

---

### 2. **Scrapers** (`scrapers/`)

#### a) **YC Scraper** (`yc_scraper.py`)

**Source:** Y Combinator (YC) company directory
**Method:** Algolia search API (public API key)
**Data Available:** Full profiles with descriptions, batch, website, founders
**Coverage:** 4,000+ companies, all batches
**Quality:** ⭐⭐⭐⭐⭐ Excellent

**What you get:**
- Company name, description
- Batch (W24, S23, etc.)
- Website, location
- Founder names
- Team size
- Social links

**Usage:**
```python
from scrapers.yc_scraper import YCombinatorScraper
scraper = YCombinatorScraper()
companies = scraper.scrape(limit=100, batch="W24")
```

**Best for:** Comprehensive YC data with full metadata

---

#### b) **SkyDeck Scraper** (`skydeck_scraper.py`)

**Source:** Berkeley SkyDeck (UC Berkeley accelerator)
**Method:** Algolia search API
**Data Available:** Company names (descriptions often missing)
**Coverage:** 350+ companies
**Quality:** ⭐⭐⭐ Good (but minimal metadata)

**Limitation:** No batch/year data in API

**Usage:**
```python
from scrapers.skydeck_scraper import SkyDeckScraper
scraper = SkyDeckScraper()
companies = scraper.scrape(limit=None)  # Get all
```

**Best for:** Getting SkyDeck portfolio list (needs enrichment)

---

#### c) **StartX Scraper** (`startx_scraper.py`)

**Source:** StartX (Stanford accelerator)
**Method:** HTML parsing
**Data Available:** Name and logos only
**Coverage:** 500+ companies
**Quality:** ⭐⭐ Fair (name-only)

**Limitation:** No batch data, minimal metadata

**Usage:**
```bash
python scripts/scrape_startx_2025.py
```

**Best for:** Getting StartX company names (requires enrichment)

---

#### d) **Name-Only Scraper** (`name_only_scraper.py`)

**Source:** Any accelerator with name-only portfolios
**Method:** Two-stage (scrape names → enrich)
**Data Available:** Starts with names, enriches to full profiles
**Coverage:** Configurable
**Quality:** ⭐⭐⭐⭐ Very good (after enrichment)

**How it works:**
1. Scrape names from portfolio page (HTML/CSS selectors)
2. Automatically enrich each company using CompanyEnricher
3. Return full profiles

**Pre-configured for:**
- StartX
- Village Global
- Founder Institute
- Plug and Play

**Usage:**
```python
from scrapers.name_only_scraper import StartXScraper
scraper = StartXScraper()
enriched = scraper.scrape_and_enrich(batch="2025", limit=50)
```

**Best for:** Accelerators that only show names/logos

---

#### e) **Generic Scraper** (`generic_scraper.py`)

**Source:** Template for custom sources
**Method:** Configurable HTML parsing
**Quality:** Depends on source

**Usage:**
```python
from scrapers.generic_scraper import GenericScraper

scraper = GenericScraper(
    source_name="My Accelerator",
    base_url="https://myaccelerator.com/portfolio"
)
companies = scraper.scrape(limit=50)
```

**Best for:** Adding new sources not yet supported

---

### 3. **Enrichment System** (`utils/company_enricher.py`)

**Purpose:** Find company data when you only have names

**The Problem:**
Many accelerators/VCs show only:
- ✅ Company names
- ✅ Logos
- ❌ No websites
- ❌ No descriptions
- ❌ No metadata

**The Solution:**
Multi-stage automatic enrichment:

#### Stage 1: Domain Pattern Matching
```
Try: company.com, company.ai, company.io, company.co, etc.
Success rate: ~70-80%
```

#### Stage 2: Website Scraping
```
Extract:
- Meta descriptions
- Social links (LinkedIn, Twitter)
- Contact emails
- Taglines
Success rate: ~60-70% find descriptions
```

#### Stage 3: LinkedIn Search
```
Search for company LinkedIn page
Success rate: ~10-20% (heavily rate limited)
```

#### Stage 4: Crunchbase Search
```
Find Crunchbase profiles
Success rate: ~15-25%
```

#### Stage 5: Google Search
```
Contextual search with accelerator name
Fallback for hard-to-find companies
Success rate: ~30-40%
```

#### Stage 6: Classification
```
- Calculate data completeness score (0.0-1.0)
- Detect stealth mode (2+ indicators)
- Flag for re-enrichment
```

**What you get:**
- **Website URLs** (70-80% success)
- **Descriptions** (50-70% success)
- **Social links** (10-30% success)
- **Stealth detection** (85-90% accuracy)
- **Completeness scores** (objective measure)

**Performance:**
- ~6-8 seconds per company
- 100 companies = ~10-15 minutes
- 500 companies = ~50-75 minutes

**Usage:**
```python
from utils.company_enricher import CompanyEnricher

enricher = CompanyEnricher()
data = enricher.enrich("Anthropic", accelerator="Y Combinator")
# Returns full profile with website, description, etc.
```

**Best for:** Name-only company lists from any source

---

### 4. **AI Detection** (`utils/ai_detector.py`)

**Purpose:** Automatically detect if a company is AI-related

**Method:** Keyword matching with confidence scoring

**Keywords Detected:**
- **High confidence:** artificial intelligence, machine learning, deep learning, LLM, generative AI
- **Medium confidence:** AI, ML, NLP, computer vision, neural networks
- **Lower confidence:** automation, algorithms, predictive analytics

**Scoring:**
```
0.8-1.0 = Very confident (multiple AI keywords)
0.5-0.8 = Confident (AI keywords present)
0.2-0.5 = Possible (automation/algorithm keywords)
0.0-0.2 = Unlikely (no AI keywords)
```

**Usage:**
```python
from utils.ai_detector import AIDetector

detector = AIDetector()
is_ai, score = detector.detect("AI-powered sales automation platform")
# Returns: (True, 0.85)
```

**Accuracy:** ~85-90% on clear descriptions

**Best for:** Automatic AI classification at scale

---

### 5. **Data Manager** (`utils/data_manager.py`)

**Purpose:** CSV database management

**What it does:**
- Loads existing data from CSV
- Adds new companies (avoiding duplicates)
- Updates existing records
- Handles data type conversions
- Saves to CSV with proper formatting

**Database:** `data/ai_startups.csv`

**Fields:**
```
- startup_name
- description
- website
- founding_date
- location
- funding_stage
- funding_amount
- investors
- team_size
- founders
- linkedin
- twitter
- contact_email
- source (accelerator/VC)
- batch (cohort)
- is_ai_related
- ai_confidence_score
- is_stealth_mode
- stealth_indicators
- data_completeness_score
- scraped_date
```

**Deduplication:** By `(startup_name, source)` combination

**Usage:**
```python
from utils.data_manager import DataManager

dm = DataManager()
dm.add_startup({
    'startup_name': 'Anthropic',
    'website': 'https://anthropic.com',
    'source': 'Y Combinator',
    'is_ai_related': True
})
dm.save()  # Saves to data/ai_startups.csv
```

**Best for:** Centralized data storage and updates

---

### 6. **Scripts** (`scripts/`)

#### Analysis Scripts

**Purpose:** Historical analysis and batch comparisons

| Script | Purpose | Output |
|--------|---------|--------|
| `analyze_2024_cohorts.py` | Compare 2024 cohorts | Multi-accelerator stats |
| `analyze_w24_ai.py` | YC W24 deep analysis | AI percentage, trends |
| `quick_w24_analysis.py` | Fast W24 stats | Console report |
| `scrape_recent_batches.py` | YC historical trends | 4-batch comparison |

**When to use:** Understanding trends and historical data

---

#### Enrichment Scripts

**Purpose:** Enrich companies from any source

| Script | Purpose | Best For |
|--------|---------|----------|
| `universal_enrichment.py` | Multi-source enrichment | Production workflows |
| `enrich_name_only_companies.py` | Simple/interactive | Quick tests |

**When to use:** Have company names, need full profiles

---

### 7. **Configuration** (`config.py`)

**Purpose:** Centralized settings

**Contains:**
- Output file paths
- Data field definitions
- AI keywords list
- Rate limiting settings
- Default parameters

**Customization:**
```python
# config.py
OUTPUT_FILE = "data/ai_startups.csv"
RATE_LIMIT = 2  # seconds between requests
AI_KEYWORDS = [
    "artificial intelligence",
    "machine learning",
    # ... add your keywords
]
```

---

## 🔄 How Data Flows

### Workflow 1: Full Data Available (e.g., Y Combinator)

```
1. User runs: python main.py --sources yc --limit 100

2. YC Scraper:
   └─> Queries Algolia API
   └─> Gets full company profiles
   └─> Includes: name, description, batch, website, founders

3. AI Detector:
   └─> Analyzes descriptions
   └─> Flags AI companies
   └─> Calculates confidence scores

4. Data Manager:
   └─> Checks for duplicates
   └─> Adds/updates records
   └─> Saves to data/ai_startups.csv

5. Output:
   └─> CSV with 100 companies, all fields populated
```

**Result:** High-quality data, minimal enrichment needed

---

### Workflow 2: Name-Only Available (e.g., StartX)

```
1. User creates CSV: data/startx_companies.csv
   name
   Anthropic
   Scale AI
   ...

2. User runs: python scripts/universal_enrichment.py --csv data/startx_companies.csv

3. Company Enricher (for each company):
   └─> Try domain patterns (anthropic.com, anthropic.ai, ...)
       └─> Found: https://anthropic.com

   └─> Scrape website:
       └─> Extract description from meta tags
       └─> Find social links (LinkedIn, Twitter)
       └─> Locate contact email

   └─> Search LinkedIn:
       └─> Try to find company page
       └─> (Often rate limited)

   └─> Search Crunchbase:
       └─> Look for funding data
       └─> (Often rate limited)

   └─> Calculate completeness:
       └─> website: 0.3
       └─> description: 0.25
       └─> linkedin: 0.15
       └─> Total: 0.70 (Good!)

   └─> Detect stealth mode:
       └─> Has website ✓
       └─> Has description ✓
       └─> Not stealth ✓

4. AI Detector:
   └─> Analyzes found description
   └─> "AI safety and research" → AI: True, Score: 0.95

5. Data Manager:
   └─> Saves enriched data
   └─> Output: data/ai_startups.csv

6. Output:
   └─> CSV with enriched profiles
   └─> 70-80% have websites
   └─> 50-70% have descriptions
   └─> Stealth companies flagged
```

**Result:** Good quality data from name-only input

---

### Workflow 3: Mixed Sources

```
1. User creates CSV with multiple sources:
   name,source,batch
   Anthropic,Y Combinator,S21
   Scale AI,Y Combinator,S16
   Company X,Berkeley SkyDeck,2024
   Company Y,Sequoia Capital,

2. User runs: python scripts/universal_enrichment.py --csv data/mixed.csv

3. For each company:
   └─> Check if data already exists in database
   └─> If incomplete, enrich it
   └─> Otherwise, use existing data

4. Output:
   └─> Single CSV with all companies
   └─> Stats broken down by source
   └─> Report showing completeness per source
```

**Result:** Unified database from multiple sources

---

## 📊 Data Sources Summary

### Currently Supported

| Source | Method | Data Quality | Batch Info | Coverage |
|--------|--------|--------------|------------|----------|
| **Y Combinator** | Algolia API | ⭐⭐⭐⭐⭐ | ✅ Yes | 4,000+ |
| **Berkeley SkyDeck** | Algolia API | ⭐⭐⭐ | ❌ No | 350+ |
| **StartX** | HTML | ⭐⭐ | ❌ No | 500+ |
| **Seedcamp** | HTML | ⭐⭐⭐ | ⚠️ Partial | 550+ |
| **Antler** | HTML | ⭐⭐⭐ | ✅ Yes | 1,400+ |

### Enrichment-Ready (Name-Only)

These work with the enrichment system:

- Village Global
- Founder Institute
- Plug and Play
- Capital Factory
- DreamIt Ventures
- MassChallenge
- Startupbootcamp
- SOSV
- **Any VC portfolio** (Sequoia, a16z, Accel, etc.)
- **Any accelerator** with public portfolio

### Difficult Sources

See [DIFFICULT_ACCELERATORS.md](DIFFICULT_ACCELERATORS.md) for 20 challenging sources:

**Tier 1:** Heavy JavaScript, no batch data
- 500 Global, Techstars, Plug and Play

**Tier 2:** Authentication required
- On Deck, Neo

**Tier 3:** Dynamic loading, minimal metadata
- MassChallenge, Capital Factory

---

## 🎯 Use Cases

### 1. **Build AI Startup Database**

**Goal:** Comprehensive list of AI startups from top accelerators

**Steps:**
```bash
# Scrape YC (best data)
python main.py --sources yc --ai-only

# Scrape SkyDeck (needs enrichment)
python main.py --sources skydeck

# Enrich any missing data
python scripts/universal_enrichment.py --csv data/ai_startups.csv

# Result: Unified database in data/ai_startups.csv
```

---

### 2. **Track Accelerator Cohorts**

**Goal:** Analyze specific batches (e.g., YC W24)

**Steps:**
```bash
# Quick analysis
python scripts/quick_w24_analysis.py

# Full analysis with storage
python scripts/analyze_w24_ai.py

# Compare multiple cohorts
python scripts/scrape_recent_batches.py

# Result: Reports showing AI adoption trends
```

---

### 3. **Enrich VC Portfolios**

**Goal:** Get details on portfolio companies

**Steps:**
```bash
# Create CSV with portfolio names
cat > data/sequoia.csv << EOF
name,source
OpenAI,Sequoia Capital
Anthropic,Sequoia Capital
MongoDB,Sequoia Capital
EOF

# Enrich
python scripts/universal_enrichment.py --csv data/sequoia.csv

# Result: Full profiles with websites, descriptions
```

---

### 4. **Monitor Stealth Startups**

**Goal:** Track companies in stealth, re-check when they launch

**Steps:**
```bash
# Initial enrichment flags stealth companies
python scripts/universal_enrichment.py --csv data/companies.csv

# Export stealth companies
python -c "
import pandas as pd
df = pd.read_csv('data/ai_startups.csv')
stealth = df[df['is_stealth_mode'] == True]
stealth.to_csv('data/stealth.csv', index=False)
print(f'Found {len(stealth)} stealth companies')
"

# Re-check in 3-6 months
python scripts/universal_enrichment.py --csv data/stealth.csv

# Result: Updated data showing which exited stealth
```

---

### 5. **Comparative Analysis**

**Goal:** Compare AI adoption across accelerators

**Steps:**
```bash
# Scrape multiple sources
python main.py --sources yc skydeck startx

# Analyze by source
python -c "
import pandas as pd
df = pd.read_csv('data/ai_startups.csv')
print(df.groupby('source')['is_ai_related'].agg(['sum', 'count', 'mean']))
"

# Result:
#                     sum  count   mean
# Y Combinator        133    251   0.53
# Berkeley SkyDeck     42     55   0.76
# StartX              120    200   0.60
```

---

## 🚀 Getting Started

### Installation

```bash
# Clone or download
cd ai_startup_scraper

# Install dependencies
pip install -r requirements.txt
```

### Quick Start

```bash
# 1. Scrape YC (full data)
python main.py --sources yc --limit 100 --ai-only

# 2. Check results
head -20 data/ai_startups.csv

# 3. Stats
python -c "
import pandas as pd
df = pd.read_csv('data/ai_startups.csv')
print(f'Total: {len(df)}')
print(f'AI: {df[\"is_ai_related\"].sum()}')
"
```

### For Name-Only Sources

```bash
# 1. Create CSV with names
cat > data/my_companies.csv << EOF
name,source
Company1,My Accelerator
Company2,My Accelerator
EOF

# 2. Enrich
python scripts/universal_enrichment.py --csv data/my_companies.csv

# 3. Check results
head -20 data/ai_startups.csv
```

---

## 📈 Expected Results

### Data Quality by Source Type

| Source Type | Websites | Descriptions | Social Links | Completeness |
|-------------|----------|--------------|--------------|--------------|
| **Full API (YC)** | 95%+ | 95%+ | 80%+ | 0.85-0.95 |
| **Enriched (name-only)** | 70-80% | 50-70% | 10-30% | 0.35-0.50 |
| **Stealth companies** | 0-20% | 0-20% | 0-10% | 0.00-0.20 |

### Processing Times

| Task | Time |
|------|------|
| Scrape 100 YC companies | ~30 seconds |
| Enrich 10 companies | ~2 minutes |
| Enrich 100 companies | ~15 minutes |
| Enrich 500 companies | ~75 minutes |
| Full SkyDeck enrichment (346) | ~45 minutes |

---

## 🛠️ Customization

### Add New Source

1. **If full data available:**
```python
# Create custom scraper in scrapers/my_scraper.py
class MyAcceleratorScraper:
    def scrape(self, limit=None):
        # Your scraping logic
        # Return list of company dicts
        pass
```

2. **If name-only:**
```python
# Use NameOnlyScraper template
from scrapers.name_only_scraper import NameOnlyScraper

scraper = NameOnlyScraper(
    accelerator_name="My Accelerator",
    portfolio_url="https://example.com/portfolio",
    selector="h3.company-name"  # CSS selector
)

companies = scraper.scrape_and_enrich(batch="2025")
```

3. **Register in config.py:**
```python
SOURCES = {
    'my_accel': MyAcceleratorScraper,
    # ...
}
```

### Customize AI Detection

Edit `config.py`:
```python
AI_KEYWORDS = [
    "artificial intelligence",
    "machine learning",
    # Add your industry-specific terms
    "robotics",
    "autonomous",
]
```

### Adjust Rate Limiting

Edit `config.py`:
```python
RATE_LIMIT = 3  # Increase to 3 seconds (safer)
# or
RATE_LIMIT = 1  # Decrease to 1 second (riskier)
```

---

## 📚 Documentation Files

| File | Purpose |
|------|---------|
| **README.md** | Project overview & installation |
| **PROJECT_OVERVIEW.md** | This file - complete system explanation |
| **ENRICHMENT_QUICKSTART.md** | Self-service enrichment guide |
| **ENRICHMENT_CHEATSHEET.txt** | Quick command reference |
| **DIFFICULT_ACCELERATORS.md** | 20 hard-to-scrape sources catalog |
| **SCRAPING_STRATEGIES.md** | Advanced scraping techniques |
| **scripts/README.md** | Scripts documentation |
| **docs/NAME_ONLY_ENRICHMENT_GUIDE.md** | Deep dive on enrichment |

---

## 🎓 Learning Path

**Beginner:**
1. Read README.md
2. Run: `python main.py --sources yc --limit 10`
3. Check: `data/ai_startups.csv`
4. Read: ENRICHMENT_QUICKSTART.md

**Intermediate:**
5. Try enrichment: `python scripts/enrich_name_only_companies.py --interactive`
6. Create CSV with companies
7. Run: `python scripts/universal_enrichment.py --csv your_file.csv`
8. Read: PROJECT_OVERVIEW.md (this file)

**Advanced:**
9. Read: DIFFICULT_ACCELERATORS.md
10. Read: SCRAPING_STRATEGIES.md
11. Create custom scraper for new source
12. Build analysis scripts for your needs

---

## 🆘 Common Questions

**Q: What's the difference between scrapers and enrichment?**
A: Scrapers get data from specific sources (YC, SkyDeck). Enrichment finds data when you only have names.

**Q: When should I use enrichment vs scrapers?**
A: Use scrapers when source has full data. Use enrichment when you only have names.

**Q: How accurate is AI detection?**
A: ~85-90% accurate with good descriptions. Less accurate with vague descriptions.

**Q: Can I scrape without enrichment?**
A: Yes, if your source has full data (like YC). Just use: `python main.py --sources yc`

**Q: Can I enrich without scraping?**
A: Yes, create a CSV with names and run: `python scripts/universal_enrichment.py --csv file.csv`

**Q: How do I handle stealth startups?**
A: They're automatically flagged. Re-enrich them in 3-6 months when they may have launched.

**Q: Can I use this for non-AI startups?**
A: Yes! Remove `--ai-only` flag. AI detection is automatic but doesn't filter unless specified.

**Q: How do I add a new accelerator?**
A: If name-only: Use universal_enrichment.py with CSV. If full data: Create custom scraper.

**Q: Is this legal?**
A: Scraping public data is generally okay for research. Check robots.txt and terms of service. Use official APIs when available.

---

## 🎯 Summary

**AI Startup Scraper is a three-layer system:**

1. **Scraping Layer:** Gets data from sources (YC, SkyDeck, StartX, etc.)
2. **Enrichment Layer:** Finds missing data when only names available
3. **Processing Layer:** AI detection, stealth flagging, completeness scoring

**Primary workflows:**

- **Full data sources (YC):** Scrape → Process → Save
- **Name-only sources (StartX):** Get names → Enrich → Process → Save
- **Mixed sources:** CSV → Enrich gaps → Unify → Save

**Output:** Single CSV database with standardized fields across all sources

**Best used for:** Building comprehensive startup databases, tracking AI trends, portfolio analysis, competitive research

---

**Last Updated:** 2026-02-16
**Version:** 2.1 (Week 2 complete - Cross-referencing proven)
**Total Scripts:** 9 (added Antler and Plug and Play tests)
**Supported Sources:** 5+ direct, unlimited via enrichment
**Active Tests:** Antler (84%), Plug and Play (100%)

---

## 🚀 WEEK 2: Scaling & Automation

**New capabilities added:**
- ✅ **14 million company database** (Crunchbase, PitchBook, Revelio)
- ✅ **Query & enrichment tools** for instant data access
- ✅ **Database builders** for targeted exports
- ✅ **Versioning system** for change tracking
- ✅ **Automation frameworks** for weekly updates

### **New Documentation (Week 2)**

#### **[SCALING_DISCOVERY.md](SCALING_DISCOVERY.md)** 📈
**Complete guide to automating startup discovery**
- 🎓 Discover 100+ university accelerators automatically
- 🏛️ Extract government-funded startups (SBIR, NSF, etc.)
- 💼 Query 500+ VC portfolios from Crunchbase/PitchBook
- 🔥 Scrape HackerNews for early-stage startups
- 🤖 Build automated discovery pipeline

**Key Features:**
- Pre-built university list (Stanford, MIT, Berkeley, etc.)
- VC portfolio extraction from 14M companies
- HackerNews "Show HN" scraper
- Government program database
- Weekly automation scripts

**Quick Start:**
```bash
# Find all AI companies from top universities
python scripts/build_database.py --type university --limit 500

# Extract VC portfolios
python scripts/query_parquet.py --name "Sequoia Capital" --export data/sequoia.csv

# Build custom category database
python scripts/build_database.py --type custom --category "fintech" --limit 1000
```

---

#### **[ACCELERATOR_LEARNING.md](ACCELERATOR_LEARNING.md)** 📚
**Educational guide for testing accelerator websites**
- ⭐ **Tier 1 (Easy):** Y Combinator, SkyDeck, 500 Global (APIs & HTML)
- ⭐⭐ **Tier 2 (Medium):** Techstars, Entrepreneur First (Selenium & JS)
- ⭐⭐⭐ **Tier 3 (Hard):** Plug and Play, MassChallenge (Anti-bot techniques)

**What You Learn:**
- API discovery using browser DevTools
- Reverse engineering Algolia search
- Selenium for dynamic content
- Infinite scroll handling
- Anti-bot evasion techniques
- CAPTCHA handling strategies

**Learning Path:**
- **Week 1:** Master 5 easy accelerators (9,000+ companies)
- **Week 2:** Learn Selenium with 5 medium accelerators (14,000+ total)
- **Week 3-4:** Tackle 3-5 hard accelerators (20,000+ total)

**Includes:**
- Step-by-step tutorials for each tier
- Scraper templates (API, HTML, Selenium)
- Debugging tips and tricks
- 20 accelerator database with difficulty ratings

---

#### **[DATABASE_AUTOMATION.md](DATABASE_AUTOMATION.md)** 🤖
**Guide to building self-updating databases**
- 🔄 **Auto-enrichment:** Fill missing data weekly
- 🔍 **Change detection:** Track funding updates, website changes
- 🏥 **Health monitoring:** Find 404s, duplicates, low-quality data
- 📧 **Email reports:** Weekly database stats
- 📊 **Dashboard:** Terminal-based monitoring

**Automation Components:**
1. **Weekly enrichment** - Auto-fill missing descriptions/websites
2. **Change tracking** - Detect funding rounds, shutdowns
3. **Health checks** - Monitor data quality
4. **Notifications** - Email/Slack updates
5. **Cron scheduling** - Fully automated updates

**Quick Setup:**
```bash
# Auto-enrich missing data
python scripts/auto_enrich.py

# Detect changes since last week
python scripts/detect_changes.py

# Check database health
python scripts/monitor_health.py

# Schedule weekly updates
crontab -e  # Add: 0 2 * * 0 /path/to/scripts/weekly_update.sh
```

---

### **New Tools (Week 2)**

| Tool | Purpose | Usage |
|------|---------|-------|
| **query_parquet.py** | Search 14M companies | `python scripts/query_parquet.py --name "Anthropic"` |
| **parquet_enricher.py** | Auto-enrich from Parquet | `python utils/parquet_enricher.py --csv input.csv` |
| **build_database.py** | Build targeted databases | `python scripts/build_database.py --type ai --limit 1000` |
| **analyze_data_gaps.py** | Find missing data | `python scripts/analyze_data_gaps.py` |
| **snapshot_database.py** | Version control | `python scripts/snapshot_database.py create` |
| **auto_enrich.py** | Weekly enrichment | Runs via cron |
| **detect_changes.py** | Change tracking | Compares snapshots |
| **monitor_health.py** | Quality checks | Finds issues |
| **test_antler_enrichment.py** | Antler cross-reference test | `python scripts/test_antler_enrichment.py` |
| **test_plugandplay_enrichment.py** | Plug and Play test | `python scripts/test_plugandplay_enrichment.py` |

---

### **Week 2 Achievements**

**Data Sources:**
- ✅ Crunchbase: 3.8M companies
- ✅ PitchBook: 198K VC-backed companies
- ✅ Revelio: 10M companies with LinkedIn
- ✅ **Total:** 14M+ companies accessible

**Databases Built:**
- ✅ 50 university AI startups (100% completeness)
- ✅ Query tool for any category
- ✅ Enrichment from 14M companies
- ✅ **84% success rate** on Antler cross-referencing (50 companies)
- ✅ **100% success rate** on Plug and Play test (20 companies)

**Infrastructure:**
- ✅ Versioning/snapshot system
- ✅ Gap analysis automation
- ✅ Change detection framework
- ✅ Health monitoring
- ✅ Email reporting (template ready)

**Cross-Reference Testing:**
- ✅ **Plug and Play:** 20 companies, 100% found in Crunchbase ($30.9B funding tracked)
- ✅ **Antler:** 50 companies scraped automatically, 84% enriched (42/50 found)
- ✅ **Automated Selenium scraper** built for Antler portfolio
- ✅ **Parquet enrichment** working across Crunchbase/PitchBook/Revelio
- ✅ **Proof of concept:** Can scrape just names and enrich with full data

---

### **Quick Reference: Week 2 Workflows**

#### **Workflow 1: Build AI Database**
```bash
# 1. Query Crunchbase for AI companies
python scripts/build_database.py --type ai --limit 1000

# 2. Analyze gaps
python scripts/analyze_data_gaps.py

# 3. Enrich missing data
python utils/parquet_enricher.py --csv data/ai_database.csv
```

#### **Workflow 2: Discover Universities**
```bash
# 1. Build university AI database
python scripts/build_database.py --type university --limit 500

# 2. Export to work with
cp data/university_database.csv data/my_universities.csv

# 3. Auto-enrich
python utils/parquet_enricher.py --csv data/my_universities.csv
```

#### **Workflow 3: Query & Export**
```bash
# Search for specific company
python scripts/query_parquet.py --name "Anthropic"

# Find category and export
python scripts/query_parquet.py --category "robotics" --export data/robotics.csv --limit 500

# Search specific source
python scripts/query_parquet.py --category "fintech" --source pitchbook --limit 300
```

#### **Workflow 4: Weekly Automation**
```bash
# Take snapshot before changes
python scripts/snapshot_database.py create --reason "weekly_update"

# Auto-enrich gaps
python scripts/auto_enrich.py

# Detect changes
python scripts/detect_changes.py

# Check health
python scripts/monitor_health.py
```

---

### **Next Steps (Week 3+)**

**Accelerator Scaling:**
- ✅ Antler scraper built (Selenium-based, automated)
- [ ] Scale Antler to all 1,400+ companies
- [ ] Build Techstars scraper (3,600+ companies)
- [ ] Build 500 Global scraper (2,900+ companies)
- [ ] Extract top 100 VC portfolios from database

**Discovery Automation:**
- [ ] Automate university portfolio discovery (100+ universities)
- [ ] Set up HackerNews daily scraping
- [ ] Government program extraction (SBIR, NSF)

**Database Automation:**
- [ ] Deploy cron jobs for weekly updates
- [ ] Configure email notifications
- [ ] Build monitoring dashboard
- [ ] Set up change alerts

**Data Quality:**
- [ ] Achieve 90%+ completeness on existing data
- [ ] Remove duplicates across sources
- [ ] Validate all website URLs (find 404s)
- [ ] Enrich with LinkedIn data where missing

---

**See Week 2 Guides:**
- [SCALING_DISCOVERY.md](SCALING_DISCOVERY.md) - Automate discovery
- [ACCELERATOR_LEARNING.md](ACCELERATOR_LEARNING.md) - Accelerator investigation & difficulty ratings
- [DATABASE_AUTOMATION.md](DATABASE_AUTOMATION.md) - Self-updating database
- [ANTLER_TEST_RESULTS.md](ANTLER_TEST_RESULTS.md) - Antler cross-reference test (84% success)
- [PLUG_AND_PLAY_FINDINGS.md](PLUG_AND_PLAY_FINDINGS.md) - Plug and Play test (100% success)