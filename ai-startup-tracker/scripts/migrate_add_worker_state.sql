-- Add worker_state column to site_health.
-- Master classification: "working" if the scraper's last attempt produced valid records,
-- otherwise "pending" (failed, returned zero, or never tried).
--
-- Backfill rule: existing rows with status = 'healthy' are working; everything else is pending.

ALTER TABLE site_health
    ADD COLUMN IF NOT EXISTS worker_state VARCHAR(16) NOT NULL DEFAULT 'pending';

UPDATE site_health
SET worker_state = CASE
    WHEN status = 'healthy' AND last_success_at IS NOT NULL THEN 'working'
    ELSE 'pending'
END;

CREATE INDEX IF NOT EXISTS ix_site_health_worker_state ON site_health (worker_state);
