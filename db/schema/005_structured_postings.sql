-- 005_structured_postings.sql
-- Phase 2 output: the extraction pipeline's two write targets.
--   1. structured_postings — one row per ROLE, 1:N with raw_postings.
--   2. extraction_runs     — one row per raw_posting, success or not.
--
-- Two tables because transform() returns roles=[] for doc_type <> 'posting':
-- a resume posted in the wrong HN thread produces ZERO role rows, which is
-- indistinguishable from "not extracted yet". extraction_runs is what makes the
-- run resumable and its coverage countable.
-- Re-runnable: applying twice is a no-op.

BEGIN;

CREATE TABLE IF NOT EXISTS structured_postings (
    id              BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    raw_posting_id  BIGINT      NOT NULL REFERENCES raw_postings(id) ON DELETE CASCADE,
    role_index      INT         NOT NULL,

    -- Posting-level, denormalized onto every role: Phase 3 embeds and returns
    -- the role row, so carrying company here saves a join on every search hit.
    -- Cost is a 4-role posting storing it 4x, rewritten together on re-extract.
    company         TEXT,

    title           TEXT,
    location        TEXT,

    -- Mirrors the Literals in normalize.py exactly. CHECK rather than a PG enum:
    -- widening a CHECK is one ALTER, widening an enum is a migration.
    -- NOT NULL DEFAULT 'unknown' matches NormalizedRole, so no query needs
    -- `IS NULL OR`.
    seniority       TEXT        NOT NULL DEFAULT 'unknown'
                    CHECK (seniority IN ('intern', 'junior', 'mid', 'senior', 'staff+', 'unknown')),
    remote_policy   TEXT        NOT NULL DEFAULT 'unknown'
                    CHECK (remote_policy IN ('remote', 'hybrid', 'onsite', 'unknown')),
    employment_type TEXT        NOT NULL DEFAULT 'unknown'
                    CHECK (employment_type IN ('full-time', 'part-time', 'contract', 'unknown')),

    -- TEXT[] not a join table: Phase 3's skill-frequency query is unnest(stack),
    -- and the alias map in normalize.py already controls the vocabulary.
    stack           TEXT[]      NOT NULL DEFAULT '{}',

    -- Monthly, per the locked ÷12 rule. NULL where the period was unknown —
    -- Web3 and Remotive state amounts with no period, and a guessed monthly
    -- figure would corrupt every downstream aggregate silently.
    salary_min      INT,
    salary_max      INT,
    salary_currency TEXT,

    source_quotes   JSONB       NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Arbitrates the pipeline's ON CONFLICT. Without it, re-extraction inserts a
    -- second copy of every role instead of updating the first.
    CONSTRAINT structured_postings_raw_posting_role_key
        UNIQUE (raw_posting_id, role_index),

    -- The one constraint that catches a real ÷12 bug rather than restating a
    -- guarantee the Pydantic layer already makes.
    CONSTRAINT structured_postings_salary_band_ordered
        CHECK (salary_max IS NULL OR salary_min IS NULL OR salary_max >= salary_min)
);

CREATE TABLE IF NOT EXISTS extraction_runs (
    -- raw_posting_id is the PK, not an identity column: that makes the write
    -- ON CONFLICT (raw_posting_id) DO UPDATE, and makes resume a single
    --   WHERE NOT EXISTS (SELECT 1 FROM extraction_runs r WHERE r.raw_posting_id = p.id)
    raw_posting_id BIGINT      PRIMARY KEY REFERENCES raw_postings(id) ON DELETE CASCADE,

    -- ok      = validated, roles written
    -- invalid = model returned JSON that lost the retry loop
    -- error   = transport / timeout / refusal, nothing to validate
    status         TEXT        NOT NULL
                   CHECK (status IN ('ok', 'invalid', 'error')),

    -- NULL unless status = 'ok'. Retrieval never needs it: structured_postings
    -- only ever holds doc_type = 'posting', so the filter lives here, once.
    doc_type       TEXT        CHECK (doc_type IN ('posting', 'candidate', 'other')),

    role_count     INT         NOT NULL DEFAULT 0,
    model          TEXT        NOT NULL,
    error          TEXT,
    extracted_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMIT;

-- ON DELETE CASCADE on both is load-bearing, not tidiness: purge.py deletes
-- raw_postings past the 90-day window, and an unqualified FK would abort it.
--
-- Coverage query — run this after the full pass to see whether it was real:
--   SELECT status, doc_type, count(*) FROM extraction_runs GROUP BY 1, 2;
