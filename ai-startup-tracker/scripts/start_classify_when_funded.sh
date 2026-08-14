#!/usr/bin/env bash
# Wait for the Anthropic balance to come back, then start the classify run.
# A top-up can take a few minutes to register, and the run is worth starting the
# moment it does rather than whenever someone next checks.
set -uo pipefail
cd "$(dirname "$0")/.."
PY=./.venv/bin/python
LOG=logs/classify.log
for i in $(seq 1 240); do          # up to ~4 hours of waiting
  if $PY -c "
import sys; sys.path.insert(0,'.')
from scripts.enrich_companies_with_ai import _call_llm
sys.exit(0 if _call_llm([{'role':'user','content':'ok'}]) else 1)
" >/dev/null 2>&1; then
    echo "$(date '+%F %T') credits live — starting classify" >> logs/classify_watch.log
    $PY scripts/enrich_fields.py classify --all-hidden --limit 20000 --workers 8 >> "$LOG" 2>&1
    echo "$(date '+%F %T') classify finished" >> logs/classify_watch.log
    exit 0
  fi
  sleep 60
done
echo "$(date '+%F %T') gave up waiting for credits" >> logs/classify_watch.log
