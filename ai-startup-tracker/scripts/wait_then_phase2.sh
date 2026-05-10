#!/bin/bash
# Wait for Phase 1 (high-ROI) to finish, then auto-launch Phase 2 (accelerator + vc).
# Phase 2 capped at $6 so total stays under $9.

set -e
PHASE1_PID="${1:?Usage: wait_then_phase2.sh <phase1_pid>}"
LOGDIR="/Users/jihwanpark/Tobin_Research/ai-startup-tracker/logs"
PROJ="/Users/jihwanpark/Tobin_Research/ai-startup-tracker"

echo "[chain] Waiting for Phase 1 (PID $PHASE1_PID)..."
while kill -0 "$PHASE1_PID" 2>/dev/null; do
  sleep 60
done
echo "[chain] Phase 1 done at $(date '+%Y-%m-%d %H:%M:%S')."

# Read phase 1 cost from report (best-effort)
P1_COST=$(python3 -c "
import json, os
try:
    d = json.load(open('${LOGDIR}/batch_high_roi.json'))
    print(f\"{d.get('total_cost_usd', 0):.2f}\")
except Exception:
    print('0.00')
" 2>/dev/null || echo "0.00")

echo "[chain] Phase 1 cost: \$${P1_COST}"

# Phase 2: accelerator + vc, with budget cap so total stays under $9
P2_BUDGET=$(python3 -c "print(max(1.0, round(9.0 - float('${P1_COST}'), 2)))")
echo "[chain] Phase 2 budget cap: \$${P2_BUDGET}"

cd "$PROJ"
source .venv/bin/activate

echo "[chain] Launching Phase 2..."
python scripts/run_batch_by_category.py \
  --categories accelerator vc_portfolio \
  --budget "${P2_BUDGET}" \
  --report "${LOGDIR}/batch_phase2.json" \
  >> "${LOGDIR}/batch_phase2.log" 2>&1

echo "[chain] Phase 2 done at $(date '+%Y-%m-%d %H:%M:%S')."
