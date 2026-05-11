#!/bin/sh
# Railway sets $PORT dynamically. Expand it in a real shell BEFORE handing the
# args to streamlit, otherwise streamlit sees the literal string "$PORT".
set -e

PORT="${PORT:-8080}"

echo "[entrypoint] starting streamlit on port=${PORT}"

exec streamlit run frontend/pipeline_dashboard.py \
    --server.port="${PORT}" \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --browser.gatherUsageStats=false
