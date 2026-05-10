# How the Multi-Agent System Actually Runs (Live)

This is a 5-minute tour of what's actually moving inside the tracker, so you
can see it work in real time instead of trusting that "agents" exist.

There are four cooperating agents. They all share one Postgres database
(`ai_startup_tracker`) and one log stream — that shared state is what makes
the system feel alive.

---

## The agents

| Agent | What it does | Code path |
|---|---|---|
| **SCRAPER** | Goes to a registered website, pulls company rows, writes to `companies` + `incubator_signals` + `scrape_runs`. Each visit is one row in `scrape_runs`. | `backend/orchestrator/orchestrator.py` + `backend/scrapers/easy/*.py` (14 hardcoded scrapers) + `backend/agentic/engine.py` (hard-tier Claude+Tavily agent). |
| **HEALER** | Watches every scrape outcome. After 2 consecutive easy-tier failures, it auto-escalates the same domain to the hard-tier agent. After 3 hard-tier failures it excludes the domain for 90 days. Writes the verdict and a one-sentence diagnosis to `site_health.pending_reason`. | `backend/orchestrator/health.py` + `backend/orchestrator/diagnose.py`. |
| **DISCOVERY** | Whenever new domains are seeded (`scripts/seed_curated_sites.py`, GitHub weekly, agentic scout), they appear in `site_health` with `worker_state='pending'`. The orchestrator then picks them up on the next "run all due" pass. | `scripts/seed_curated_sites.py`, `scripts/github_weekly_discover.py`, `backend/discovery/scout.py`. |
| **CLASSIFIER** | LLM batch classifier for unprocessed GitHub repo snapshots and weak Crunchbase descriptions. Together (Llama-3.3-70B) by default; auto-fails over to Claude Haiku 4.5 on credit-out. | `scripts/run_llm_classify_failover.py`, `scripts/reclassify_ai_with_llm.py`. |

The 562 sites you've already seen in the dashboard's "Sources Analyzed" panel
are entries the SCRAPER agent has been visiting (or trying to). Of those, 73
are healthy and producing rows; the rest are pending and waiting for either
credit (for the agentic path) or a new instruction file.

---

## How "live" looks

Open two terminals side by side:

### Terminal A — the activity ticker

```bash
cd ai-startup-tracker
source .venv/bin/activate
python scripts/live_agent_monitor.py --interval 3
```

Every few seconds it polls the same DB the dashboard reads and prints one
line per real event. You should see things like:

```
[07:55:01] [BOOT] [monitor   ] primed: 443 historical runs, 562 known domains
[07:55:14] [OK  ] [SCRAPER   ] huggingface.co                    tier=easy status=success    found= 312 new= 312  (8.4s)
[07:55:14] [INFO] [HEALER    ] huggingface.co                    status: pending -> healthy
[07:55:31] [WARN] [SCRAPER   ] alliance.rice.edu                 tier=easy status=zero_result found=   0 new=   0  (1.9s)
[07:55:31] [INFO] [HEALER    ] alliance.rice.edu                 diagnosis: page returned no rows; escalate to hard tier
[07:55:34] [STAT] [DATAWALL  ] companies=117,915 | runs(1h)=8 | working=78 | pending=484
```

Each prefix tags which agent produced it:

- `SCRAPER` — a scrape just completed (one row added to `scrape_runs`)
- `HEALER`  — `site_health` status flipped, or a new diagnosis got written
- `DISCOVERY` — a brand-new domain entered `site_health`
- `DATAWALL` — periodic running totals

If lines stop flowing, no agent is actually working at that moment. That
*is* the live signal.

### Terminal B — drive the system

In a second terminal, you can poke the agents on demand:

```bash
# Run every site that's due (orchestrator picks easy or hard per domain)
python scripts/run_orchestrator.py --batch

# Retry only the zero-result sites from the last 48 hours
python scripts/run_orchestrator.py --retry

# Hit one site directly (auto-detects easy vs hard tier from registry)
python scripts/run_orchestrator.py --url https://huggingface.co/organizations
```

Watch terminal A — every command above shows up there as it happens.

---

## Why the dashboard "Sources Analyzed" looks low

73 working / 489 pending is misleading without context. ~235 of those
pending sites failed because at the time of their last attempt the
**Anthropic API had no credit**, so the agentic engine couldn't run.

You can see that in the report:

```
ai-startup-tracker/reports/site_status.txt
  >> blocked: Anthropic credits exhausted   (~235 sites)
```

Two ways to unblock them:

1. **Top up Anthropic credits** and run `python scripts/run_orchestrator.py --retry`. The HEALER will retry every zero-result domain from the last 48 hours.
2. **Use the Together fallback** for the agentic engine (planned next iteration). The classifier already has this fallback; the agentic engine is currently Claude-only.

The 5 untried easy-tier scrapers (`alchemistaccelerator.com`, `alliance.rice.edu`, `huggingface.co`, `kellercenter.princeton.edu`, `startups.columbia.edu`) don't need Claude at all — they have hardcoded scraper classes in `backend/scrapers/easy/` and just need to be triggered. They get picked up automatically by `--batch`.

---

## How to convince yourself this is real, not theatre

Open three things at once:

1. The dashboard ([http://localhost:8501](http://localhost:8501))
2. The live monitor (`live_agent_monitor.py`)
3. A psql session

Then in a fourth shell run:

```bash
python scripts/run_orchestrator.py --url https://huggingface.co/organizations
```

You will see, in order:

1. Monitor prints `[SCRAPER] huggingface.co tier=easy status=success found=N new=N`.
2. Monitor prints `[HEALER] huggingface.co status: pending -> healthy`.
3. psql `SELECT COUNT(*) FROM scrape_runs;` increments by 1.
4. psql `SELECT COUNT(*) FROM companies;` jumps by ~N.
5. Dashboard, after its 60-second cache TTL, shows the new totals.

That's the system, end-to-end, in under a minute.
