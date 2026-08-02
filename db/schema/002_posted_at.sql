-- 002_posted_at.sql
-- Per-row publish timestamp, tz-aware. thread_month stays as the coarse
-- month marker (still used for HN's thread-level grouping); posted_at is
-- the actual per-posting time and is what Phase 3/4 date filters should use.
-- Re-runnable: applying twice is a no-op.

BEGIN;

ALTER TABLE raw_postings ADD COLUMN IF NOT EXISTS posted_at TIMESTAMPTZ;

-- Adzuna's `created` is already tz-aware (e.g. "2026-08-01T22:02:37Z").
UPDATE raw_postings
   SET posted_at = (raw_text::jsonb ->> 'created')::timestamptz
 WHERE source = 'adzuna' AND posted_at IS NULL;

-- Remotive's `publication_date` is naive (no offset) — cast straight to
-- timestamptz would silently apply the session's timezone. Interpret it as
-- UTC explicitly instead.
UPDATE raw_postings
   SET posted_at = (raw_text::jsonb ->> 'publication_date')::timestamp AT TIME ZONE 'UTC'
 WHERE source = 'remotive' AND posted_at IS NULL;

-- HN's raw_text is bare comment prose, not JSON — no timestamp to recover
-- here. Existing HN rows stay NULL until backfilled from Algolia directly;
-- rows loaded going forward carry posted_at from ingestion (see load.py).

COMMIT;
