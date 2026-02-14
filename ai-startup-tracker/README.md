# 🚀 Global AI Startup Tracker

**Real-time intelligence system that discovers, analyzes, and tracks emerging AI startups worldwide.**

Automatically scrapes 12+ global sources, stores in PostgreSQL, and visualizes on an interactive dashboard with geographic mapping.

---

## 🎯 What You Get

- **84+ startups tracked** across 3 active data sources
- **Global coverage** from North America, Europe, Asia, and beyond
- **Interactive map** showing startup locations worldwide
- **Startup directory** with search, filtering, and vertical categorization
- **Trend analysis** with time-series charts and source distribution
- **Automated pipeline** that scrapes, imports, and displays in 3 commands

---

## ⚡ Quick Start

```bash
# 1. Scrape global startup data
python run_full_scraper.py

# 2. Import to database
python scripts/import_scraped_data.py

# 3. Launch dashboard
streamlit run frontend/dashboard.py
```

**Or run complete pipeline:**
```bash
./update_tracker.sh
```

Dashboard opens at: [http://localhost:8501](http://localhost:8501)

---

## 🏗️ How It Works

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   SCRAPER    │  →   │   IMPORTER   │  →   │  DASHBOARD   │
│              │      │              │      │              │
│ Collects     │      │ Bridges      │      │ Displays     │
│ from 12+     │      │ JSON → DB    │      │ in browser   │
│ sources      │      │              │      │              │
└──────────────┘      └──────────────┘      └──────────────┘
```

### 1️⃣ Scraper
**File**: `run_full_scraper.py`

Collects startup data from:
- ✅ **Hacker News** (Show HN) - ~30 startups
- ✅ **TechCrunch** - ~25 startups
- ✅ **GitHub Trending** (AI repos) - ~12 startups
- 🔧 Crunchbase Search (configured)
- 🔧 Tech in Asia (configured)
- 🔧 EU-Startups (configured)
- 🔧 Indie Hackers (configured)
- 🔧 F6S Global (configured)
- 🔧 Product Hunt (configured)
- 🔧 Y Combinator (configured)
- 🔧 BetaList (configured)

**Output**: `data/global_startups_full.json`

### 2️⃣ Importer
**File**: `scripts/import_scraped_data.py`

Bridges JSON files → PostgreSQL database:
- Maps source names to database enums
- Extracts domain from URLs
- Parses location into country/city
- Sets default relevance scores
- Skips duplicates automatically
- Commits in batches of 50

### 3️⃣ Dashboard
**File**: `frontend/dashboard.py`

Interactive Streamlit dashboard with:
- 📊 Key metrics (startups, sources, countries, verticals)
- 🗺️ Geographic distribution map with coordinate plotting
- 📈 Trend analysis with time-series and source breakdown
- 🏢 Startup directory organized by vertical
- 🔍 Filtering by source, country, vertical, and relevance

---

## 📦 Installation

### Prerequisites
- Python 3.10+
- PostgreSQL 14+ with pgvector extension

### Setup

```bash
# 1. Clone repository
cd ai-startup-tracker

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Setup PostgreSQL
createdb ai_startup_tracker
psql -U postgres -d ai_startup_tracker -f backend/database/schema.sql

# 5. Configure environment (optional for LLM features)
cp .env.example .env
# Edit .env with GROQ_API_KEY if you want AI-powered location prediction
```

---

## 📊 Current Statistics

- **Total Startups**: 84
- **High Relevance** (≥0.70): 68
- **Countries**: 12+
- **Active Sources**: 3 (Hacker News, TechCrunch, GitHub)
- **Configured Sources**: 12+

---

## 🗄️ Database Schema

### Startup Table
```sql
CREATE TABLE startups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    url VARCHAR(512) UNIQUE NOT NULL,
    domain VARCHAR(255) NOT NULL,
    description TEXT,
    country VARCHAR(100),
    city VARCHAR(100),
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    source DataSource NOT NULL,
    relevance_score DECIMAL(3, 2),
    confidence_score DECIMAL(3, 2),
    industry_vertical VARCHAR(100),
    founder_names TEXT[],
    extra_metadata JSONB,
    discovered_date TIMESTAMP DEFAULT NOW(),
    status CompanyStatus DEFAULT 'active',
    review_status ReviewStatus DEFAULT 'pending'
);
```

---

## 🔧 Common Tasks

### Update Data Daily
```bash
./update_tracker.sh
```

### Re-import Without Re-scraping
```bash
python scripts/import_scraped_data.py
```

### View Raw Scraped Data
```bash
cat data/global_startups_full.json | python -m json.tool | less
```

### Check Database Status
```bash
psql ai_startup_tracker -c "SELECT COUNT(*) FROM startups;"
psql ai_startup_tracker -c "SELECT name, source, country FROM startups LIMIT 10;"
```

### Clear Database and Start Fresh
```bash
psql ai_startup_tracker -c "TRUNCATE startups CASCADE;"
python scripts/import_scraped_data.py
```

### Restart Dashboard with Fresh Cache
```bash
./restart_dashboard.sh
```

### Fix Location Data
```bash
# Extract locations from descriptions, set defaults
python scripts/fix_locations.py

# Add coordinates for mapping
python scripts/geocode_locations.py

# (Optional) Use LLM to predict locations intelligently
python scripts/llm_predict_locations.py
```

---

## 🗺️ Location Intelligence

The tracker includes 3 location scripts:

### 1. `fix_locations.py`
Extracts locations from descriptions, sets default (San Francisco) for unknowns

### 2. `geocode_locations.py`
Comprehensive coordinate database for 100+ global tech hubs

### 3. `llm_predict_locations.py`
Uses Groq LLM to intelligently predict startup locations from:
- Company names (geographic indicators)
- Descriptions (market mentions)
- URL domains (.com vs .co.uk vs .de)
- Source platform patterns
- Industry conventions

**Requires**: `GROQ_API_KEY` in `.env` (free tier: 30 req/min)

---

## 📁 Project Structure

```
ai-startup-tracker/
├── run_full_scraper.py          # Scraper entry point
├── update_tracker.sh            # Complete pipeline automation
├── restart_dashboard.sh         # Dashboard restart utility
│
├── backend/
│   ├── scrapers/
│   │   ├── aggregator_scraper.py    # Main scraping logic (12+ sources)
│   │   └── base_scraper.py          # Scraper base class
│   │
│   ├── database/
│   │   ├── models.py                # SQLAlchemy ORM models
│   │   ├── connection.py            # Database connection
│   │   └── schema.sql               # PostgreSQL schema
│   │
│   ├── intelligence/
│   │   ├── embeddings.py            # Vector embeddings
│   │   └── llm_analyzer.py          # Groq LLM analysis
│   │
│   └── config.py                    # Configuration management
│
├── scripts/
│   ├── import_scraped_data.py       # JSON → Database importer
│   ├── fix_locations.py             # Location extraction
│   ├── geocode_locations.py         # Coordinate mapping
│   └── llm_predict_locations.py     # AI location prediction
│
├── frontend/
│   └── dashboard.py                 # Streamlit dashboard
│
├── data/
│   ├── global_startups_full.json    # Scraped data
│   └── test_results.json            # Test data
│
├── requirements.txt                 # Python dependencies
├── .env.example                     # Environment template
└── COMPLETE_WORKFLOW.md             # Detailed workflow documentation
```

---

## 🔄 Data Flow

### Initial Setup (Empty Database)
```bash
# Step 1: Scrape data
python run_full_scraper.py
# Output: data/global_startups_full.json (67 startups)

# Step 2: Import to database
python scripts/import_scraped_data.py
# Output: ✅ Added 55, ⏭️ Skipped 12 duplicates

# Step 3: View dashboard
streamlit run frontend/dashboard.py
# Shows: 55 startups with metrics and map
```

### Daily Update (Incremental)
```bash
./update_tracker.sh
# New scrape: 80 startups (30 new, 50 existing)
# Import result: ✅ Added 30, ⏭️ Skipped 50
# Database now: 85 startups total
```

---

## 🐛 Troubleshooting

### Dashboard shows 0 startups
**Problem**: Database is empty
**Solution**: Run `python scripts/import_scraped_data.py`

### Import says "0 added"
**Problem**: All startups already in database OR no JSON files
**Solution**: Check if `data/global_startups_full.json` exists, run scraper first

### Scraper gets 0 from some sources
**Problem**: Website HTML changed or anti-scraping measures
**Solution**: Normal! 3 sources (Hacker News, TechCrunch, GitHub) currently work reliably

### Map doesn't show startups
**Problem**: Startups missing coordinates
**Solution**: Run `python scripts/fix_locations.py` and `python scripts/geocode_locations.py`

### Database connection error
**Problem**: PostgreSQL not running
**Solution**: Start postgres or check `.env` file configuration

### Streamlit cache issues
**Problem**: Dashboard shows stale data
**Solution**: Run `./restart_dashboard.sh` to clear cache

---

## 🚀 Advanced Features

### Automate with Cron
```bash
# Edit crontab
crontab -e

# Add daily update at 9 AM
0 9 * * * cd /Users/jihwanpark/Tobin_Research/ai-startup-tracker && ./update_tracker.sh
```

### Export Data to CSV
```bash
psql ai_startup_tracker -c "COPY (SELECT name, url, description, country, city FROM startups) TO '/tmp/startups.csv' CSV HEADER;"
```

### Filter Dashboard by Multiple Criteria
Dashboard supports filtering by:
- Source (Hacker News, TechCrunch, GitHub, etc.)
- Country
- Industry vertical
- Relevance score threshold

---

## 📈 Metrics You Can Track

- ✅ Total global startups discovered
- ✅ Geographic distribution (countries, cities)
- ✅ Trending industry verticals
- ✅ Source effectiveness (which finds more startups?)
- ✅ Emerging markets
- ✅ Time-series trends (with AI embeddings)
- ✅ Similar startup clusters (with vector search)

---

## 🔑 API Keys (Optional)

For enhanced AI features, add to `.env`:

```env
# Groq LLM (for intelligent location prediction)
GROQ_API_KEY=your_key_here

# Get free key at: https://console.groq.com
# Free tier: 30 requests/min
```

---

## 📄 License

MIT License

---

## 🙏 Acknowledgments

Built with:
- **Streamlit** - Dashboard framework
- **PostgreSQL + pgvector** - Database with vector extensions
- **BeautifulSoup4** - Web scraping
- **Plotly** - Interactive visualizations
- **Groq LLM** - AI-powered analysis

---

## 📧 Support

For detailed workflow documentation, see: [COMPLETE_WORKFLOW.md](COMPLETE_WORKFLOW.md)

For issues or questions:
- Check the troubleshooting section above
- Review `COMPLETE_WORKFLOW.md` for detailed explanations
- Examine logs: `full_scraper_final.log`

---

**🌍 Track global AI startups in real-time!**
