-- Add pending_reason columns to site_health.
-- pending_reason holds a one-line NL explanation of why a scraper keeps failing,
-- written by backend.orchestrator.diagnose once consecutive_failures hits 2.
--
-- Idempotent: safe to re-run.

ALTER TABLE site_health
    ADD COLUMN IF NOT EXISTS pending_reason TEXT;

ALTER TABLE site_health
    ADD COLUMN IF NOT EXISTS pending_reason_at TIMESTAMP;
