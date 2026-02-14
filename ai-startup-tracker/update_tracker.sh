#!/bin/bash
# Complete Update Pipeline: Scrape → Import → Ready for Dashboard

echo "🚀 Starting AI Startup Tracker Update..."
echo ""

# Step 1: Scrape
echo "1️⃣ Scraping global startups..."
python run_full_scraper.py
echo ""

# Step 2: Import
echo "2️⃣ Importing into database..."
python scripts/import_scraped_data.py
echo ""

# Step 3: Done
echo "✅ Update complete!"
echo ""
echo "📊 View your dashboard:"
echo "   streamlit run frontend/dashboard.py"
echo ""
