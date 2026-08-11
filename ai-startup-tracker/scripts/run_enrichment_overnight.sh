#!/usr/bin/env bash
# Unattended enrichment loop for the hidden AI companies.
#
# Cycles the three tiers in dependency order for a fixed wall-clock budget:
#   classify -> web -> classify (picks up descriptions web just found) -> deep
# Each stage is resumable and skips rows it already attempted, so a cycle that
# is interrupted simply resumes on the next pass.
#
#   ./scripts/run_enrichment_overnight.sh            # 10 hours (default)
#   HOURS=4 ./scripts/run_enrichment_overnight.sh    # shorter run
#
# Logs: logs/enrichment_overnight.log (progress + a coverage line per cycle).

set -uo pipefail
cd "$(dirname "$0")/.."

HOURS="${HOURS:-10}"
WEB_BATCH="${WEB_BATCH:-400}"      # tier 2 is the slow one (fetch + LLM per row)
DEEP_BATCH="${DEEP_BATCH:-400}"    # tier 3 is Tavily-bound
CLASSIFY_BATCH="${CLASSIFY_BATCH:-2000}"
WORKERS="${WORKERS:-8}"
PY="./.venv/bin/python"
LOG_DIR="logs"; mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/enrichment_overnight.log"

: "${DATABASE_URL:?set DATABASE_URL (use the Railway URL for production data)}"

DEADLINE=$(( $(date +%s) + HOURS * 3600 ))
say() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

say "=== enrichment run start · ${HOURS}h budget · workers=${WORKERS} ==="

cycle=0
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  cycle=$((cycle + 1))
  say "--- cycle ${cycle} ---"

  for stage in "classify:$CLASSIFY_BATCH" "web:$WEB_BATCH" "classify:$CLASSIFY_BATCH" "deep:$DEEP_BATCH"; do
    [ "$(date +%s)" -ge "$DEADLINE" ] && break
    name="${stage%%:*}"; batch="${stage##*:}"
    say "  running ${name} (limit ${batch})"
    $PY scripts/enrich_fields.py "$name" --limit "$batch" --workers "$WORKERS" \
      >>"$LOG" 2>&1 || say "  ! ${name} exited non-zero (continuing)"
  done

  # one coverage line per cycle so the log reads as a progress curve
  $PY - <<'PY' 2>/dev/null | tee -a "$LOG"
import sys
sys.path.insert(0, ".")
from backend.db.connection import get_engine
from backend.utils.ai_filter import ai_filter_sql
from sqlalchemy import text
c = get_engine().connect()
AI = ai_filter_sql("c"); H = "c.verification_status='emerging_github'"
one = lambda q: c.execute(text(q)).scalar()
tot = one(f"SELECT COUNT(*) FROM companies c WHERE {H} AND {AI}")
j = "FROM companies c JOIN company_enrichment e ON e.company_id=c.id WHERE " + H + " AND " + AI
what = one(f"SELECT COUNT(*) {j} AND e.ai_application IS NOT NULL")
loc = one(f"SELECT COUNT(*) {j} AND e.location_country IS NOT NULL")
fnd = one(f"SELECT COUNT(*) {j} AND e.founders IS NOT NULL")
yr = one(f"SELECT COUNT(*) {j} AND e.founding_year IS NOT NULL")
fun = one(f"SELECT COUNT(*) {j} AND e.recent_funding IS NOT NULL")
p = lambda n: f"{n:,} ({n/tot*100:.0f}%)"
print(f"  COVERAGE of {tot:,} hidden-AI | what-they-do {p(what)} | location {p(loc)} "
      f"| founders {p(fnd)} | year {p(yr)} | funding {p(fun)}")
PY

  # every stage empty means there is nothing left to do this pass
  sleep 5
done

say "=== enrichment run complete (${cycle} cycles) ==="
