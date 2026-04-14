#!/bin/bash
# Restart Dashboard with Fresh Cache

echo "🔄 Restarting Dashboard with Fresh Data..."
echo ""

# Kill any running streamlit processes
echo "1️⃣ Stopping existing dashboard..."
pkill -f "streamlit run" 2>/dev/null || echo "   No running dashboard found"
sleep 2

# Clear streamlit cache
echo ""
echo "2️⃣ Clearing Streamlit cache..."
rm -rf ~/.streamlit/cache 2>/dev/null || true
echo "   ✅ Cache cleared"

# Start dashboard
echo ""
echo "3️⃣ Starting dashboard..."
echo "   Opening in your browser at: http://localhost:8501"
echo ""
streamlit run frontend/dashboard.py
