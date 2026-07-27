# Session kickoff prompt

Paste this to start the next Claude Code session:

---

Read README.md and docs/ROADMAP.md first — a job-market intelligence agent: ingest HN "Who is
Hiring" + Remotive postings → LLM structured extraction (Pydantic, quote-grounded) → Postgres +
pgvector → DeepSeek agent with tools → FastAPI. This is the **service/infra** portfolio project;
the retrieval/agent lab is the separate **product-search** repo. Built skill-by-skill, to learn.

**How to work with me:**
- I write the code by default. Your job is guidance, review, and feedback — don't edit project
  files unless I ask. Docs (README / ROADMAP checkboxes) are fair game on a wrap-up.
- When I say I've implemented something, verify it: read the code and run it before assessing.
  Paste-errors-not-fixes — explain the error, don't silently patch.
- I'm doing this to learn — explain the concept, not just the change. Every file must pass the
  explain-back test before we call a step done.
- Watch my token budget: prefer a fresh session per phase over dragging a long context around, and
  say so when a wrap-up + new session is the cheaper move.

**Where we left off (2026-07-27):** Phase 1 (ingestion), ~halfway. Done: `docker-compose.yml`
(Postgres 17 + pgvector), `db/schema/001_raw_postings.sql` applied with all five constraints and the
guarded upsert verified by hand, and `src/ingestion/hn_client.py` **complete** —
`find_latest_hiring_thread()` plus `fetch_thread(story_id) -> HNThread` (frozen dataclasses
`HNThread`/`HNComment`, one `/items/` call, 276 comments off the July 2026 thread). ruff, `ruff
format` and mypy are all clean. Repo is on git (`main`, 3 commits).

`src/ingestion/load.py` is an **empty file** — that's the next piece.

**Next up (in order):**
1. `load.py`: parse `thread.created_at` (raw ISO) → `.date().replace(day=1)` for `thread_month`, map
   each `HNComment` to `(source='hn', external_id, raw_text, thread_month)`, and run the guarded
   upsert via `psycopg`. Report inserted-vs-unchanged counts so idempotency is visible on re-run.
   Needs a `DATABASE_URL` in `.env` / `.env.example` (only `POSTGRES_PASSWORD` is there now).
2. `init/001_extensions.sql` with `CREATE EXTENSION IF NOT EXISTS vector;` — `init/` is empty and
   git doesn't track empty dirs, so pgvector currently gets created nowhere.
3. Remotive client, then load to the ~700-posting target.

**Watch out:** start Docker Desktop before anything DB-shaped (it was down last session). Use
`uv run python -m mypy src` — the `mypy.exe` shim in `.venv` is a broken uv trampoline. And put the
loader on a branch; the roadmap says no direct commits to `main` and all 3 so far ignored that.

Start by checking the current state of the repo in case I've changed things since.

---
