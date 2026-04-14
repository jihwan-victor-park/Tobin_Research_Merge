# AI Startup Intelligence Platform

## Current State
Merged codebase combining two contributors' work. Primary working directory 
is ai-startup-tracker/ which contains the active codebase.

## Architecture
- Database: PostgreSQL (ai_startup_tracker), schema in ai-startup-tracker/backend/db/models.py
- Scrapers: ai-startup-tracker/backend/scrapers/easy/ (12 sources)
- Agent: ai-startup-tracker/backend/agentic/engine.py
- Pipeline: ai-startup-tracker/scripts/run_weekly_update.py
- Original scrapers (reference only): scrapers/ at root

## Environment
- Python via miniconda
- .env file at root and ai-startup-tracker/
- DATABASE_URL=postgresql://localhost/ai_startup_tracker
- ANTHROPIC_API_KEY set in .env
