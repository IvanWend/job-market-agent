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

**Where we left off (2026-07-26):** Phase 1 (ingestion) in progress. Working: `docker-compose.yml`
(Postgres 17 + pgvector) and `hn_client.py::find_latest_hiring_thread()`. The `raw_postings` DDL
(`db/schema/001_raw_postings.sql`) is **designed but not yet on disk** — CHECK + composite unique +
guarded upsert. Repo is **not yet under git**; `requirements.txt` still needs cleanup; `.env` empty.

**Next up (pick one):**
1. Write `db/schema/001_raw_postings.sql`, apply it from a clean `docker compose down -v`, and verify
   the three upsert conflict behaviors (`INSERT 0 1` / `0 0` / `0 1`; Remotive `test-1` also inserts).
2. Housekeeping first: `git init` + `.gitignore`, curate `requirements.txt` (+ `psycopg[binary]`),
   `.env.example`.
3. Then: extend `hn_client.py` to fetch all top-level comments for the `story_id`, and write the
   idempotent loader (`load.py`) that upserts them into `raw_postings`.

Start by checking the current state of the repo in case I've changed things since. Do not make any changes. We are just planning.

---
