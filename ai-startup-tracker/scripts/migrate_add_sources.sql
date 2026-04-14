-- Migration: Add 20 new IncubatorSource enum values
-- Run this ONCE against your existing PostgreSQL database if the tables already exist.
-- Safe to run multiple times (uses IF NOT EXISTS pattern via DO block).
--
-- Usage:
--   psql $DATABASE_URL -f scripts/migrate_add_sources.sql

-- Drop old CHECK constraints that SQLAlchemy may have auto-generated.
-- These block insertion of new enum values until the constraint is updated.
-- The native PostgreSQL enum type handles validation; CHECK constraints are redundant.
ALTER TABLE companies DROP CONSTRAINT IF EXISTS companies_incubator_source_check;
ALTER TABLE incubator_signals DROP CONSTRAINT IF EXISTS incubator_signals_source_check;

DO $$
BEGIN
    -- University Incubators
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'berkeley_skydeck'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'berkeley_skydeck';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'mit_engine'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'mit_engine';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'stanford_startx'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'stanford_startx';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'uiuc_enterpriseworks'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'uiuc_enterpriseworks';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'cmu_swartz'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'cmu_swartz';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'harvard_ilabs'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'harvard_ilabs';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'georgia_tech_atdc'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'georgia_tech_atdc';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'michigan_zell_lurie'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'michigan_zell_lurie';
    END IF;

    -- Major Accelerators
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'techstars'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'techstars';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'five_hundred_global'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'five_hundred_global';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'alchemist'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'alchemist';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'sosv'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'sosv';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'plug_and_play'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'plug_and_play';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'masschallenge'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'masschallenge';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'lux_capital'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'lux_capital';
    END IF;

    -- Trend / Discovery
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'betalist'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'betalist';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'wellfound'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'wellfound';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'f6s'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'f6s';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'hn_who_is_hiring'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'hn_who_is_hiring';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'techcrunch_battlefield'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'techcrunch_battlefield';
    END IF;

    -- International Incubators (from international_incubators.csv)
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'era_nyc'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'era_nyc';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'startup_chile'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'startup_chile';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'flat6labs'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'flat6labs';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'ventures_platform'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'ventures_platform';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'hax'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'hax';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'surge'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'surge';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'brinc'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'brinc';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'sparklabs'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'sparklabs';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'parallel18'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'parallel18';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'wayra'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'wayra';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'nxtp_ventures'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'nxtp_ventures';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'allvp'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'allvp';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'astrolabs'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'astrolabs';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'grindstone'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'grindstone';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'seedstars'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'seedstars';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'station_f'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'station_f';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'startupbootcamp'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'startupbootcamp';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'h_farm'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'h_farm';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'sting_stockholm'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'sting_stockholm';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'rockstart'
                   AND enumtypid = 'incubator_source_enum'::regtype) THEN
        ALTER TYPE incubator_source_enum ADD VALUE 'rockstart';
    END IF;

END$$;

-- Verify: show all current enum values
SELECT enumlabel FROM pg_enum
WHERE enumtypid = 'incubator_source_enum'::regtype
ORDER BY enumsortorder;
