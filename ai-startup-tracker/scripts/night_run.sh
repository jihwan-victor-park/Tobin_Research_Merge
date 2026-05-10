#!/bin/bash
# Robust night-run wrapper:
#  - Wait for Phase 1 (high-ROI categories)
#  - Auto-launch Phase 2 (accelerator + vc) with budget = $9 - phase1_cost
#  - Skip Phase 2 if remaining budget < $1
#  - Generate MORNING_REPORT.md so the user sees one summary on wake

set -u
PHASE1_PID="${1:?Usage: night_run.sh <phase1_pid>}"
PROJ="/Users/jihwanpark/Tobin_Research/ai-startup-tracker"
LOGDIR="$PROJ/logs"
TOTAL_BUDGET="9.0"

mkdir -p "$LOGDIR"

log() {
  echo "[chain] $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log "Waiting for Phase 1 (PID $PHASE1_PID)..."
while kill -0 "$PHASE1_PID" 2>/dev/null; do
  sleep 60
done
log "Phase 1 done."

cd "$PROJ"
source .venv/bin/activate

# Read Phase 1 cost
P1_COST=$(python3 -c "
import json
try:
    d = json.load(open('${LOGDIR}/batch_high_roi.json'))
    print(f\"{d.get('total_cost_usd', 0):.4f}\")
except Exception:
    print('0.0000')
")
log "Phase 1 cost: \$${P1_COST}"

# Compute Phase 2 budget — strict cap, skip if too small
P2_BUDGET=$(python3 -c "
remaining = ${TOTAL_BUDGET} - float('${P1_COST}')
print(round(remaining, 2) if remaining >= 1.0 else 0.0)
")
log "Phase 2 budget: \$${P2_BUDGET}"

if [ "$P2_BUDGET" = "0.0" ]; then
  log "Remaining budget < \$1, skipping Phase 2."
else
  log "Launching Phase 2 (accelerator + vc_portfolio)..."
  python scripts/run_batch_by_category.py \
    --categories accelerator vc_portfolio \
    --budget "${P2_BUDGET}" \
    --report "${LOGDIR}/batch_phase2.json" \
    >> "${LOGDIR}/batch_phase2.log" 2>&1 || log "Phase 2 exited non-zero"
  log "Phase 2 done."
fi

# Generate morning report
log "Generating morning report..."
python scripts/morning_report.py > "${LOGDIR}/MORNING_REPORT.md" 2>>"${LOGDIR}/chain.log" \
  || log "Morning report generation failed"

log "All done. See ${LOGDIR}/MORNING_REPORT.md"

# Release caffeinate
pkill -f "caffeinate -dis" 2>/dev/null || true
