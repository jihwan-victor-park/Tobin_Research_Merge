#!/bin/sh
# Railway sets $PORT dynamically. Expand it in a real shell BEFORE handing the
# args to streamlit, otherwise streamlit sees the literal string "$PORT".
set -e

PORT="${PORT:-8080}"

# If someone set STREAMLIT_SERVER_PORT=$PORT (literal) in the Railway dashboard,
# click validates that env var before our CLI flag and crashes on the unexpanded
# string. Force it to the expanded numeric value here.
export STREAMLIT_SERVER_PORT="${PORT}"
export STREAMLIT_SERVER_ADDRESS="0.0.0.0"

# Create tables in the (likely empty) target DB before Streamlit boots,
# otherwise the dashboard's first SELECT crashes with "relation does not exist".
echo "[entrypoint] running init_db() to create tables if missing..."
python -c "from backend.db.connection import init_db; init_db()" \
    || echo "[entrypoint] init_db() failed (continuing anyway)"

echo "[entrypoint] starting streamlit on port=${PORT}"

exec streamlit run frontend/pipeline_dashboard.py \
    --server.port="${PORT}" \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --browser.gatherUsageStats=false
