# 🚀 Complete AI Startup Tracker Workflow

## 📊 The Three Components

Your tracker has **3 main components** that work together:

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   SCRAPER    │  →   │   IMPORTER   │  →   │  DASHBOARD   │
│              │      │              │      │              │
│ Collects     │      │ Bridges      │      │ Displays     │
│ from web     │      │ JSON → DB    │      │ in browser   │
└──────────────┘      └──────────────┘      └──────────────┘
```

---

## 1️⃣ Scraper (Data Collection)

### Purpose:
Collects startup data from 12+ global sources

### Files:
- `run_full_scraper.py` - Main scraper runner
- `backend/scrapers/aggregator_scraper.py` - Scraping logic

### What it does:
- Scrapes Hacker News, TechCrunch, GitHub, etc.
- Saves to: `data/global_startups_full.json`

### Run it:
```bash
python run_full_scraper.py
```

### Output:
```json
[
  {
    "name": "Cool Startup",
    "url": "https://coolstartup.com",
    "description": "We build cool stuff",
    "source": "Hacker News",
    "location": "San Francisco",
    "launch_date": "2026-02-08"
  },
  ...
]
```

---

## 2️⃣ Importer (Data Bridge) ⭐ NEW!

### Purpose:
**Bridges the gap** between JSON files and PostgreSQL database

### File:
- `scripts/import_scraped_data.py`

### What it does:
1. Reads JSON files from `data/` directory
2. Maps source names to database enums
3. Extracts domain from URLs
4. Parses location into country/city
5. Sets default relevance scores
6. Inserts into PostgreSQL database
7. **Skips duplicates automatically**

### Run it:
```bash
python scripts/import_scraped_data.py
```

### What gets imported:
- ✅ Name, URL, description
- ✅ Source (mapped to enum)
- ✅ Country, city (parsed from location)
- ✅ Domain (extracted from URL)
- ✅ Default scores (relevance: 0.75, confidence: 0.70)
- ✅ Metadata (original source, scrape time)

---

## 3️⃣ Dashboard (Data Visualization)

### Purpose:
Beautiful web interface to view and analyze startups

### File:
- `frontend/dashboard.py`

### What it shows:
- 📊 Metrics (total startups, sources, countries)
- 🗺️ Geographic distribution
- 📈 Trends over time
- 🏢 Industry verticals
- ⭐ Top-rated startups (by relevance score)

### Run it:
```bash
streamlit run frontend/dashboard.py
```

### Access it:
Opens in browser at: `http://localhost:8501`

---

## 🔄 Complete Workflow

### Option A: One Command (Recommended)
```bash
./update_tracker.sh
```
This runs: Scrape → Import → Ready!

### Option B: Step by Step
```bash
# Step 1: Scrape data
python run_full_scraper.py

# Step 2: Import to database
python scripts/import_scraped_data.py

# Step 3: View dashboard
streamlit run frontend/dashboard.py
```

---

## 📁 File Structure

```
ai-startup-tracker/
├── run_full_scraper.py          # 1️⃣ Scraper entry point
├── update_tracker.sh            # 🔄 Complete pipeline script
│
├── backend/
│   ├── scrapers/
│   │   └── aggregator_scraper.py  # Scraping logic (12+ sources)
│   │
│   ├── database/
│   │   ├── models.py              # Database schema
│   │   └── connection.py          # DB connection
│   │
│   └── intelligence/
│       ├── embeddings.py          # AI embeddings
│       └── llm_analyzer.py        # AI analysis
│
├── scripts/
│   └── import_scraped_data.py   # 2️⃣ JSON → Database importer
│
├── frontend/
│   └── dashboard.py             # 3️⃣ Streamlit dashboard
│
└── data/
    ├── global_startups_full.json   # Scraped data
    └── test_results.json           # Test data
```

---

## 🗄️ Database Schema

The `Startup` model has these fields:

### Required:
- `name` - Startup name
- `url` - Website URL
- `domain` - Extracted domain
- `source` - Data source (enum)

### Optional but Important:
- `description` - What they do
- `country` - Country
- `city` - City
- `industry_vertical` - AI category
- `relevance_score` - AI relevance (0-1)
- `confidence_score` - AI confidence (0-1)
- `founder_names` - Array of founders
- `extra_metadata` - JSON with additional data

### Auto-filled:
- `discovered_date` - When scraped
- `status` - Active/Stealth/etc
- `review_status` - Pending/Approved/etc

---

## 🔧 Common Tasks

### Update Data Daily:
```bash
./update_tracker.sh
```

### Re-import Without Re-scraping:
```bash
python scripts/import_scraped_data.py
```
(Useful if you modify the JSON file manually)

### View Raw Data:
```bash
cat data/global_startups_full.json | python -m json.tool | less
```

### Check Database:
```bash
psql ai_startup_tracker -c "SELECT COUNT(*) FROM startups;"
psql ai_startup_tracker -c "SELECT name, source, country FROM startups LIMIT 10;"
```

### Clear Database (Start Fresh):
```bash
psql ai_startup_tracker -c "TRUNCATE startups CASCADE;"
python scripts/import_scraped_data.py
```

---

## 🎯 Data Flow Example

### Starting Point: Empty Database
```
Database: 0 startups
```

### Step 1: Run Scraper
```bash
python run_full_scraper.py
```
Output: `data/global_startups_full.json` with 67 startups

### Step 2: Import to Database
```bash
python scripts/import_scraped_data.py
```
Output:
```
✅ Added: 55 startups
⏭️  Skipped: 12 duplicates
```

Database now has: **55 startups**

### Step 3: View Dashboard
```bash
streamlit run frontend/dashboard.py
```
Shows: **55 startups** with metrics and charts

### Later: Run Again (Update)
```bash
./update_tracker.sh
```
New scrape gets: 80 startups
- 30 new ones
- 50 duplicates (already in DB)

Database now has: **85 startups** (55 + 30 new)

---

## 🐛 Troubleshooting

### Dashboard shows 0 startups:
**Problem**: Database is empty
**Solution**: Run `python scripts/import_scraped_data.py`

### Import says "0 added":
**Problem**: All startups already in database OR no JSON files
**Solution**:
1. Check if `data/global_startups_full.json` exists
2. Run scraper first: `python run_full_scraper.py`

### Scraper gets 0 from some sources:
**Problem**: Website HTML changed or anti-scraping
**Solution**: This is normal! 3 sources (HN, TC, GitHub) currently work

### Database connection error:
**Problem**: PostgreSQL not running
**Solution**: Start postgres or check `.env` file

### Streamlit error:
**Problem**: Missing dependencies
**Solution**: `pip install streamlit plotly pandas`

---

## 💡 Pro Tips

### 1. Automate with Cron:
```bash
# Edit crontab
crontab -e

# Add this line (runs daily at 9 AM)
0 9 * * * cd /Users/jihwanpark/Tobin_Research/ai-startup-tracker && ./update_tracker.sh
```

### 2. Filter Dashboard by Source:
The dashboard can filter by:
- Source (Hacker News, TechCrunch, GitHub)
- Country
- Industry vertical
- Relevance score

### 3. Export Data:
```bash
# Export to CSV
psql ai_startup_tracker -c "COPY (SELECT name, url, description, country FROM startups) TO '/tmp/startups.csv' CSV HEADER;"
```

### 4. Analyze with AI:
If you have GROQ_API_KEY in `.env`, the system can:
- Generate embeddings for similarity search
- Analyze startup relevance with LLM
- Cluster similar startups
- Extract industry verticals

---

## 📈 Metrics You Can Track

With this system, you can:
- ✅ Track 100+ global startups daily
- ✅ See geographic distribution
- ✅ Identify trending verticals
- ✅ Compare sources (which finds more startups?)
- ✅ Spot emerging markets
- ✅ Find similar startups (with AI embeddings)

---

## 🎉 Summary

You now have a **complete 3-stage pipeline**:

1. **Scraper** → Collects from web
2. **Importer** → Saves to database
3. **Dashboard** → Visualizes beautifully

All connected and working! 🚀

---

## 🆘 Quick Commands Reference

```bash
# Complete update (recommended)
./update_tracker.sh

# Individual steps
python run_full_scraper.py              # Scrape
python scripts/import_scraped_data.py   # Import
streamlit run frontend/dashboard.py     # View

# Check status
ls -lh data/                            # Check JSON files
psql ai_startup_tracker -c "SELECT COUNT(*) FROM startups;"  # DB count

# View logs
tail -f full_scraper_final.log          # Scraper logs
```

---

**Ready to track global startups! 🌍🚀**
