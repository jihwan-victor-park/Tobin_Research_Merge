# Scaling Discovery: Automated AI Startup Finding

**Goal:** Automate discovery of AI startups from universities, government programs, VCs, HackerNews, and all other sources

---

## 🎯 Overview

You now have access to **14 million companies**. This guide shows you how to systematically discover and organize AI startups from every major source.

---

## 📊 Current Data Sources

### **1. Crunchbase (3.8M companies)**
- ✅ **Available now** via `organizations.parquet`
- Coverage: Startups, funding data, categories
- Quality: 97% have websites, 100% descriptions
- Best for: General startup discovery, funding tracking

### **2. PitchBook (198K VC-backed)**
- ✅ **Available now** via `pitchbook_vc_na_company.parquet`
- Coverage: VC-backed companies only, North America focus
- Quality: 99.9% descriptions, detailed metrics
- Best for: High-quality VC-backed startups

### **3. Revelio (10M companies)**
- ✅ **Available now** via `revelio_company_mapping-000000.parquet`
- Coverage: LinkedIn-heavy, company hierarchies
- Quality: 94% have LinkedIn URLs
- Best for: LinkedIn enrichment, employee data

---

## 🎓 Strategy 1: University Accelerators (100+ programs)

### **A. Discover All University Programs**

**From Crunchbase:**
```python
# Script: scripts/discover_universities.py
import pandas as pd
import os

cb_path = os.path.expanduser('~/Downloads/organizations.parquet')
df = pd.read_parquet(cb_path)

# Find all university accelerators/incubators
universities = df[
    (df['category_list'].str.contains('accelerator|incubator', case=False, na=False)) &
    (df['short_description'].str.contains('university|college', case=False, na=False))
]

# Extract program names
programs = universities[['name', 'homepage_url', 'city', 'region']].copy()
programs.to_csv('data/university_programs.csv', index=False)

print(f"Found {len(programs)} university programs")
```

**Top 20 University Accelerators:**
1. **Stanford StartX** - https://startx.com
2. **Berkeley SkyDeck** - https://skydeck.berkeley.edu
3. **MIT delta v** - https://entrepreneurship.mit.edu/delta-v/
4. **Harvard Innovation Labs** - https://i-lab.harvard.edu
5. **Yale Tsai CITY** - https://tsaicity.yale.edu
6. **Columbia Startup Lab** - https://entrepreneurship.columbia.edu
7. **Princeton eLab** - https://elab.princeton.edu
8. **Penn Wharton Innovation Fund** - https://innovation.upenn.edu
9. **Caltech Innovation** - https://innovation.caltech.edu
10. **Cornell eLab** - https://elab.cornell.edu
11. **Oxford Foundry** - https://www.oxfordfoundry.ox.ac.uk
12. **Cambridge Judge** - https://www.jbs.cam.ac.uk/entrepreneurship/
13. **Imperial Enterprise Lab** - https://www.imperial.ac.uk/enterprise/
14. **ETH Zurich** - https://eth.ch/en/the-eth-zurich/entrepreneurship
15. **NUS Enterprise** - https://enterprise.nus.edu.sg
16. **INSEAD** - https://www.insead.edu/centres/insead-innovation-entrepreneurship-centre
17. **Technion T3** - https://t3.technion.ac.il
18. **Tel Aviv University** - https://starttau.org
19. **Tsinghua x-lab** - https://www.x-lab.tsinghua.edu.cn
20. **Peking University** - https://www.pku.edu.cn/innovation

### **B. Automated Scraping Pipeline**

**Create:** `scripts/scrape_all_universities.py`

```python
#!/usr/bin/env python3
"""
Automated University Scraper
Scrapes all major university accelerators
"""

import pandas as pd
import time
from datetime import datetime

# List of university programs
UNIVERSITY_PROGRAMS = [
    {
        'name': 'Stanford StartX',
        'url': 'https://startx.com/companies',
        'scraper': 'startx_scraper',
        'batch_available': False
    },
    {
        'name': 'Berkeley SkyDeck',
        'url': 'https://skydeck.berkeley.edu/portfolio',
        'scraper': 'skydeck_scraper',
        'batch_available': False
    },
    {
        'name': 'MIT delta v',
        'url': 'https://entrepreneurship.mit.edu/delta-v/',
        'scraper': 'generic_scraper',
        'batch_available': True
    },
    # Add more...
]

def scrape_all_universities():
    """Scrape all university programs"""

    all_companies = []

    for program in UNIVERSITY_PROGRAMS:
        print(f"\n🎓 Scraping {program['name']}...")

        try:
            # Import appropriate scraper
            scraper_module = __import__(f"scrapers.{program['scraper']}",
                                       fromlist=[program['scraper']])

            # Create scraper instance
            scraper = scraper_module.Scraper()

            # Scrape
            companies = scraper.scrape()

            # Add to list
            all_companies.extend(companies)

            print(f"✅ Got {len(companies)} companies from {program['name']}")

        except Exception as e:
            print(f"❌ Error scraping {program['name']}: {e}")
            continue

        time.sleep(5)  # Rate limiting

    # Save
    df = pd.DataFrame(all_companies)
    timestamp = datetime.now().strftime('%Y%m%d')
    df.to_csv(f'data/all_universities_{timestamp}.csv', index=False)

    print(f"\n✅ Total companies: {len(all_companies)}")
    return df

if __name__ == '__main__':
    scrape_all_universities()
```

**Schedule Weekly:**
```bash
# Add to crontab (runs every Sunday at 2am)
0 2 * * 0 cd /path/to/ai_startup_scraper && python scripts/scrape_all_universities.py
```

---

## 🏛️ Strategy 2: Government Programs

### **Discover Government Startup Programs**

**Major Programs:**

**USA:**
- **SBIR/STTR** - https://www.sbir.gov (Small Business Innovation Research)
- **NSF I-Corps** - https://www.nsf.gov/i-corps
- **DOE Cyclotron Road** - https://cyclotronroad.lbl.gov
- **NIH SBIR** - https://sbir.nih.gov
- **NASA iTech** - https://www.nasa.gov/solve/itech

**UK:**
- **Innovate UK** - https://www.ukri.org/councils/innovate-uk/
- **Tech Nation** - https://technation.io

**EU:**
- **European Innovation Council** - https://eic.ec.europa.eu
- **Horizon Europe** - https://ec.europa.eu/info/horizon-europe

**Other:**
- **Singapore IMDA** - https://www.imda.gov.sg
- **Israel Innovation Authority** - https://innovationisrael.org.il
- **Canada IRAP** - https://nrc.canada.ca/en/support-technology-innovation

### **Query Government-Funded Companies**

```python
# Find companies that mention government grants
gov_companies = df[
    df['short_description'].str.contains(
        'SBIR|STTR|NSF|NIH|DOE|government grant|innovate uk',
        case=False, na=False
    )
]

gov_companies.to_csv('data/government_funded.csv', index=False)
```

---

## 💼 Strategy 3: VC Programs (500+ top VCs)

### **A. Extract VC Portfolios from Crunchbase**

```python
# Script: scripts/extract_vc_portfolios.py
import pandas as pd
import os

# Load Crunchbase
cb_path = os.path.expanduser('~/Downloads/organizations.parquet')
df = pd.read_parquet(cb_path)

# Top VC firms to extract
TOP_VCS = [
    'Sequoia Capital', 'Andreessen Horowitz', 'Accel',
    'Benchmark', 'Greylock Partners', 'Kleiner Perkins',
    'Index Ventures', 'Lightspeed Venture Partners',
    'NEA', 'General Catalyst', 'Founders Fund',
    'First Round Capital', 'Battery Ventures',
    'Insight Partners', 'Tiger Global', 'Coatue',
    'Y Combinator', 'Techstars', '500 Startups'
]

# For each VC, find their portfolio companies
for vc_name in TOP_VCS:
    # Find companies that mention this VC in investors field
    portfolio = df[
        df['investors'].str.contains(vc_name, case=False, na=False)
    ]

    # Save
    filename = vc_name.lower().replace(' ', '_')
    portfolio.to_csv(f'data/vc_portfolios/{filename}.csv', index=False)

    print(f"{vc_name}: {len(portfolio)} companies")
```

### **B. Scrape VC Websites Directly**

Many VCs have public portfolio pages:

**Create:** `scrapers/vc_portfolio_scraper.py`

```python
#!/usr/bin/env python3
"""
VC Portfolio Scraper
Generic scraper for VC portfolio pages
"""

class VCPortfolioScraper:
    """Scrape VC portfolio pages"""

    VC_CONFIGS = {
        'a16z': {
            'url': 'https://a16z.com/portfolio',
            'selector': '.portfolio-company'
        },
        'sequoia': {
            'url': 'https://www.sequoiacap.com/companies/',
            'selector': '.company-card'
        },
        'accel': {
            'url': 'https://www.accel.com/companies',
            'selector': '.company-item'
        }
        # Add more...
    }

    def scrape(self, vc_name):
        """Scrape a specific VC portfolio"""
        # Implementation here
        pass
```

---

## 🔥 Strategy 4: HackerNews Discovery

### **A. Scrape "Show HN" Posts**

**HackerNews is gold for early-stage startups!**

```python
# Script: scrapers/hackernews_scraper.py
import requests
import time
from datetime import datetime, timedelta

class HackerNewsScraper:
    """Scrape Show HN posts for new startups"""

    API_BASE = 'https://hacker-news.firebaseio.com/v0'

    def get_show_hn_posts(self, days_back=30):
        """Get Show HN posts from last N days"""

        # Get top stories
        top_stories = requests.get(f'{self.API_BASE}/topstories.json').json()

        show_hn_posts = []

        for story_id in top_stories[:500]:  # Check last 500 stories
            # Get story details
            story = requests.get(
                f'{self.API_BASE}/item/{story_id}.json'
            ).json()

            if not story:
                continue

            # Check if it's a Show HN post
            title = story.get('title', '')
            if 'Show HN' in title:
                show_hn_posts.append({
                    'title': title,
                    'url': story.get('url', ''),
                    'time': story.get('time'),
                    'score': story.get('score', 0)
                })

            time.sleep(0.1)  # Rate limiting

        return show_hn_posts

    def extract_startups(self, posts):
        """Extract startup info from Show HN posts"""

        startups = []

        for post in posts:
            # Parse title to get company name
            title = post['title'].replace('Show HN:', '').strip()

            # Extract first part as company name
            company_name = title.split('–')[0].split('-')[0].strip()

            startups.append({
                'startup_name': company_name,
                'description': title,
                'website': post['url'],
                'source': 'HackerNews Show HN',
                'hn_score': post['score']
            })

        return startups

# Usage
scraper = HackerNewsScraper()
posts = scraper.get_show_hn_posts(days_back=90)
startups = scraper.extract_startups(posts)

# Save
pd.DataFrame(startups).to_csv('data/hackernews_startups.csv', index=False)
```

### **B. Monitor "Who's Hiring" Threads**

HN monthly hiring threads reveal growing startups:

```python
def scrape_whos_hiring():
    """Scrape monthly Who's Hiring threads"""

    # Search for "Ask HN: Who is hiring?"
    # Extract company names from comments
    # Build list of actively hiring startups
    pass
```

---

## 🤖 Strategy 5: Automated Discovery Pipeline

### **Complete Automation System**

**Create:** `scripts/automated_discovery_pipeline.py`

```python
#!/usr/bin/env python3
"""
Automated Discovery Pipeline
Runs weekly to discover new AI startups from all sources
"""

import pandas as pd
from datetime import datetime
import os

class DiscoveryPipeline:
    """Automated startup discovery"""

    def __init__(self):
        self.all_companies = []

    def discover_from_crunchbase(self):
        """Query Crunchbase for new AI companies"""
        print("🔍 Discovering from Crunchbase...")
        # Implementation
        pass

    def discover_from_universities(self):
        """Scrape university accelerators"""
        print("🎓 Discovering from universities...")
        # Scrape StartX, SkyDeck, MIT, etc.
        pass

    def discover_from_vcs(self):
        """Extract from VC portfolios"""
        print("💼 Discovering from VC portfolios...")
        # Query top 50 VCs
        pass

    def discover_from_government(self):
        """Find government-funded startups"""
        print("🏛️ Discovering from government programs...")
        # Query SBIR, NSF, etc.
        pass

    def discover_from_hackernews(self):
        """Scrape HackerNews"""
        print("🔥 Discovering from HackerNews...")
        # Scrape Show HN
        pass

    def deduplicate(self):
        """Remove duplicates across sources"""
        df = pd.DataFrame(self.all_companies)
        df = df.drop_duplicates(subset=['startup_name', 'website'])
        return df

    def run(self):
        """Run complete discovery pipeline"""
        print("=" * 80)
        print("🚀 AUTOMATED DISCOVERY PIPELINE")
        print("=" * 80)

        self.discover_from_crunchbase()
        self.discover_from_universities()
        self.discover_from_vcs()
        self.discover_from_government()
        self.discover_from_hackernews()

        # Deduplicate
        df = self.deduplicate()

        # Save
        timestamp = datetime.now().strftime('%Y%m%d')
        output = f'data/discovered_{timestamp}.csv'
        df.to_csv(output, index=False)

        print(f"\n✅ Discovered {len(df)} unique companies")
        print(f"💾 Saved to: {output}")

        return df

if __name__ == '__main__':
    pipeline = DiscoveryPipeline()
    pipeline.run()
```

### **Schedule Weekly Runs**

```bash
# Crontab entry (runs every Sunday at 3am)
0 3 * * 0 cd /path/to/ai_startup_scraper && python scripts/automated_discovery_pipeline.py

# Or use a simple bash script
#!/bin/bash
# weekly_discovery.sh

cd /path/to/ai_startup_scraper

# Take snapshot
python scripts/snapshot_database.py create --reason "before_weekly_discovery"

# Run discovery
python scripts/automated_discovery_pipeline.py

# Enrich new companies
python utils/parquet_enricher.py --csv data/discovered_*.csv

# Send email notification
echo "Discovery complete: $(date)" | mail -s "Weekly Discovery Report" you@email.com
```

---

## 📊 Discovery Targets

### **By End of Month 1:**
- ✅ 100+ university accelerators mapped
- ✅ 50+ top VC portfolios extracted
- ✅ 20+ government programs indexed
- ✅ Weekly HackerNews scraper running
- ✅ 5,000+ AI startups in database

### **By End of Month 3:**
- ✅ Full automation (weekly runs)
- ✅ 200+ data sources tracked
- ✅ 20,000+ AI startups in database
- ✅ Change detection (new companies weekly)
- ✅ Email alerts for significant discoveries

---

## 🎯 Quick Start Actions

**This Week:**
1. ✅ Extract top 20 university programs from Crunchbase
2. ✅ Query 10 major VC portfolios
3. ✅ Build HackerNews scraper
4. ✅ Test automation pipeline

**Next Week:**
1. Schedule weekly runs
2. Add email notifications
3. Build monitoring dashboard
4. Scale to 100+ sources

---

## 💡 Pro Tips

1. **Start with Crunchbase** - It already has most companies
2. **VCs change slowly** - Only re-scrape monthly
3. **HackerNews is fast** - Check daily for Show HN
4. **Universities are seasonal** - Batch scraping aligns with cohorts
5. **Government is updated quarterly** - SBIR awards are public

---

**Next Steps:** See [ACCELERATOR_LEARNING.md](ACCELERATOR_LEARNING.md) for testing different websites and [DATABASE_AUTOMATION.md](DATABASE_AUTOMATION.md) for auto-updates.







**Tasks from Last Week

Investigate Potential Ways to Automate, Find, and Organize

 - Difference in timing hacker news/maybe github: weekly, VC Portfolios: Monthly, accelerators/Universities/Gov: Quarterly
 - Hacker News/GitHub
    - Weekly Scrape
 - Accelerators/Incubators: YC, Techstars, Plug and Play, Seedcamp, Antler, 500 Global, Microsoft/Google for Startups
    - Find Largest 20/30 and create manual webscrapers for each
    - Make configurable scraper websites: HTML, API, Directory, Detail Page
 - University Based: Stanford StartX, Berkeley Skydeck, Accelerate Cambridge, MIT delta v, Harvard Innovation Labs, NYU entrepreneurial Institue
    - Potential Automation (discover_university_accelerators), demodays
    - Webscrape Most Promising, using config webscraper, 
 - Government Based: Startup Chile, Israel Innovation Authority, Germany EXIST Program
    - Potential Automation (Gov Accelerators), also specific APIs (SBIR.gov API)


Play around with more accelerators, their website structure, and what information they have:
 - YC (great for scraping)
 - SkyDeck (Good for scraping used Algolia API)
 - Antler (solid for scraping)
 - Techstars (next.js framework, very hard to get updated information), however AI/ML vertical, very organized
 - Plug and Play (custom scraper per vertical)
 - Potentially Using an Agent:


Begin Thinking about how to build database (What do the websites include?, and how to update automatically)
 - Update Weekly
 - Cross-Reference with Linkedin, Pitchbook, CrunchBase, (CSVs)
 - ^Add what the websites were Missing (EXAMPLE: techstars, Plug and Play, Antler), only when needed, and to find AI information, or every month (leave a note as to not showing up / checking after )
 - Core Information: id, name, description, founding date, location, AI classification (and what sub-vertical), Sourced From, Batch/Founding Date, Snapshot Date
 - Checking for duplicates ( add new source)
 - Monitoring Over Time, Flagging Meaningful Changes (name, description, existence)
 - Weekly New Companies, Weekly Changes
 - Anything not covered, go to Pitchbook, CrunchBase, Linkedin Directly, and search 2024 onwards with AI in name/description (want to check feasibility)
 - Code death: after months of no appearance or no update (12 month / 18 month), (x/linkedin) checking 
 - Focus on earliest stage, if Pitchbook/Crunchbase, perhaps link to them
 - 

 Future Plans:
 - Test with 5 Specific Accelerators, and track changes
 - begin integrating w Victor
 - Cross-Reference those with crunchbase/pitchbook if needed
