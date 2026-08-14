#!/usr/bin/env bash
# Run the scraping expansion plan (reports/SCRAPING_PLAN.md) one phase at a time.
#
# Phases are ordered cheapest-first, so a run that gets cut short by exhausted
# credits has already banked the free and low-cost coverage. Each phase is
# resumable: progress lives in the database, never in this script.
#
#   ./scripts/run_scraping_plan.sh free          # $0    — WHOIS + GitHub entity check
#   ./scripts/run_scraping_plan.sh depth         # ~$33  — fill fields on known domains
#   ./scripts/run_scraping_plan.sh longitudinal  # ~$15  — re-collect known sites (two time points)
#   ./scripts/run_scraping_plan.sh breadth       # ~$45  — discover new portfolio sites
#   ./scripts/run_scraping_plan.sh recommended   # free + depth + longitudinal
#   ./scripts/run_scraping_plan.sh all
#
# Required: DATABASE_URL (Railway), ANTHROPIC_API_KEY, TAVILY_API_KEY (breadth only)
set -uo pipefail
cd "$(dirname "$0")/.."

PY=./.venv/bin/python
PHASE="${1:-recommended}"
mkdir -p logs
LOG="logs/plan_$(date +%Y%m%d_%H%M).log"

say() { printf '\n\033[1m== %s\033[0m\n' "$*" | tee -a "$LOG"; }
note() { printf '   %s\n' "$*" | tee -a "$LOG"; }

if [ -z "${DATABASE_URL:-}" ]; then
  echo "! DATABASE_URL is not set — refusing to run against the stale local dump."
  echo "  export DATABASE_URL=<Railway DATABASE_PUBLIC_URL>"
  exit 1
fi

coverage() {
  $PY - <<'PY' 2>/dev/null | tee -a "$LOG"
import os, sys
sys.path.insert(0, ".")
from sqlalchemy import text
from backend.db.connection import get_engine
H = "verification_status='emerging_github'"
with get_engine().connect() as c:
    one = lambda q: c.execute(text(q)).scalar()
    tot = one(f"SELECT COUNT(*) FROM companies WHERE {H}")
    dom = one(f"SELECT COUNT(*) FROM companies WHERE {H} AND domain IS NOT NULL")
    des = one(f"SELECT COUNT(*) FROM companies WHERE {H} AND description <> ''")
    cls = one(f"""SELECT COUNT(*) FROM company_enrichment e JOIN companies co ON co.id=e.company_id
                  WHERE co.{H} AND e.ai_application IS NOT NULL""")
    yr  = one(f"""SELECT COUNT(*) FROM company_enrichment e JOIN companies co ON co.id=e.company_id
                  WHERE co.{H} AND COALESCE(e.founding_year, e.domain_created_year) IS NOT NULL""")
    pct = lambda n: f"{n:6,} ({n/max(tot,1)*100:4.1f}%)"
    print(f"   hidden {tot:,} | domain {pct(dom)} | description {pct(des)} | "
          f"classified {pct(cls)} | year {pct(yr)}")
PY
}

need_key() {
  if [ -z "${!1:-}" ] && ! grep -q "^$1=" .env 2>/dev/null; then
    note "! $1 is not set — skipping this phase"
    return 1
  fi
}

run_free() {
  say "PHASE 1 · free (\$0)"
  note "GitHub entity check — names that cannot be logins are settled by rule first"
  $PY scripts/classify_github_entities.py 2>&1 | tail -20 | tee -a "$LOG"
  note "WHOIS founding-year proxy on companies whose domain we already know"
  $PY scripts/enrich_fields.py whois --limit 8000 2>&1 | tail -8 | tee -a "$LOG"
  note "country from ccTLD — no API involved"
  $PY scripts/infer_country_from_tld.py 2>&1 | tail -5 | tee -a "$LOG"
}

run_depth() {
  say "PHASE 2 · depth (~\$33, Anthropic only)"
  need_key ANTHROPIC_API_KEY || return 0
  note "site scrape for rows with a domain but no description — costs no Tavily credit"
  $PY scripts/enrich_fields.py web --limit 9000 --workers 8 2>&1 | tail -12 | tee -a "$LOG"
  note "classify everything that now has a description"
  $PY scripts/enrich_fields.py classify --limit 12000 --workers 8 2>&1 | tail -12 | tee -a "$LOG"
}

run_longitudinal() {
  say "PHASE 3 · longitudinal (~\$15) — the only phase that produces a second time point"
  need_key ANTHROPIC_API_KEY || return 0
  note "re-collect sites already registered: new portfolio entries since the last pass"
  $PY scripts/run_orchestrator.py --batch --cooldown 0 2>&1 | tail -15 | tee -a "$LOG"
  note "retry sites whose last run returned nothing (most failed on dead credits)"
  $PY scripts/run_orchestrator.py --retry 2>&1 | tail -15 | tee -a "$LOG"
}

run_breadth() {
  say "PHASE 4 · breadth (~\$45, Anthropic + Tavily) — where new companies come from"
  need_key ANTHROPIC_API_KEY || return 0
  need_key TAVILY_API_KEY || return 0
  note "discover portfolio/accelerator sites we do not have yet, country by country"
  $PY scripts/run_international_scout.py --all --limit 20 2>&1 | tail -20 | tee -a "$LOG"
  note "scrape whatever the scout registered"
  $PY scripts/run_orchestrator.py --batch 2>&1 | tail -15 | tee -a "$LOG"
}

say "start $(date '+%F %T')  ·  phase=$PHASE  ·  log=$LOG"
say "coverage BEFORE"; coverage

case "$PHASE" in
  free)         run_free ;;
  depth)        run_depth ;;
  longitudinal) run_longitudinal ;;
  breadth)      run_breadth ;;
  recommended)  run_free; run_depth; run_longitudinal ;;
  all)          run_free; run_depth; run_longitudinal; run_breadth ;;
  *) echo "unknown phase: $PHASE (free|depth|longitudinal|breadth|recommended|all)"; exit 1 ;;
esac

say "coverage AFTER"; coverage
say "done $(date '+%F %T')  ·  full log: $LOG"
