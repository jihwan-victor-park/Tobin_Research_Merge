-- Add category column to site_health for inventory grouping.
-- Values: university_incubator | accelerator | vc_portfolio
--       | discovery_aggregator | government_program | other
--
-- Idempotent: safe to re-run.

ALTER TABLE site_health
    ADD COLUMN IF NOT EXISTS category VARCHAR(32);

CREATE INDEX IF NOT EXISTS ix_site_health_category ON site_health (category);
