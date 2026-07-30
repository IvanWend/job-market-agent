# Session kickoff prompt

Paste this to start the next Claude Code session:

---

Read README.md and docs/ROADMAP.md first — a job-market intelligence agent: ingest HN "Who is
Hiring" + Remotive postings → LLM structured extraction (Pydantic, quote-grounded) → Postgres +
pgvector → DeepSeek agent with tools → FastAPI. This is the **service/infra** portfolio project;
the retrieval/agent lab is the separate **product-search** repo. Built skill-by-skill, to learn.

**How to work with me:**
- **Short, structured answers.** Numbered steps or bullets, not prose walls. Actionable first,
  rationale only where a decision hinges on it. Long detailed messages are the wrong format for me.
- I write the code by default. Your job is guidance, review, and feedback — don't edit project
  files unless I ask. Docs (README / ROADMAP / PROMPT) are fair game on a wrap-up.
- When I say I've implemented something, verify it: read the code and run it before assessing.
  Paste-errors-not-fixes — explain the error, don't silently patch.
- I'm doing this to learn — explain the concept when I ask, not by default. Every file must pass
  the explain-back test before we call a step done.
- Watch my token budget: prefer a fresh session per phase over dragging a long context around, and
  say so when a wrap-up + new session is the cheaper move.

**Where we left off (2026-07-29):** Phase 1 (ingestion). `docker-compose.yml`,
`db/schema/001_raw_postings.sql` (applied, all five constraints + guarded upsert verified by hand)
and `src/ingestion/hn_client.py` are done. On branch `feat/loader`, uncommitted; `DATABASE_URL` is
in `.env` and `.env.example`.

`src/ingestion/load.py` — half written. Working: `to_thread_month()` and `thread_to_rows()`
(mypy clean, 276 rows off the July 2026 thread). Not written: the psycopg half.

**Next up (in order):**
1. Fix `source` — `thread_to_rows` emits `"HN"`; the CHECK is `source IN ('hn', …)`. One-char bug,
   fails only at insert time.
2. `UPSERT_SQL` — draft still says `ON CONFLICT (external_id)`; the unique constraint is
   `(source, external_id)`. Add the `WHERE raw_text IS DISTINCT FROM EXCLUDED.raw_text` guard,
   `updated_at = now()` (no trigger exists), and `RETURNING (xmax = 0)`. Write it in psql first.
3. `upsert_postings(conn, rows) -> LoadStats` — caller owns the transaction, returns counts, does
   not print. Wire into `__main__`. Note: a suppressed guarded update returns *no row*, so
   `unchanged = len(rows) - returned`; `with psycopg.connect()` commits on clean exit.
4. Verify idempotency: run twice → `N/0/0` then `0/0/N`; hand-edit one `raw_text` → `0/1/N-1`.
5. `init/001_extensions.sql` with `CREATE EXTENSION IF NOT EXISTS vector;` — `init/` is empty and
   git doesn't track empty dirs, so pgvector gets created nowhere. Note the existing `pgdata`
   volume means init scripts won't re-run; apply by hand or `docker compose down -v`.
6. Remotive client, then load to the ~700-posting target.

**Watch out:**
- Start Docker Desktop first — it has gone down mid-session twice.
- `uv run python -m mypy src`; the `mypy.exe` shim in `.venv` is a broken uv trampoline.
- `.env.example` briefly held a real-looking `DEEPSEEK_API_KEY` (working tree only, never
  committed); it is an empty placeholder again. Keep secrets out of that file.
- `hn_client.py` docstrings/comments were removed deliberately; don't flag it again.

Start by checking the current state of the repo in case I've changed things since.

---
