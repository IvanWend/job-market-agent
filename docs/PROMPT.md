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

**Where we left off (2026-07-30):** Phase 1 (ingestion). `docker-compose.yml`,
`db/schema/001_raw_postings.sql` (all five constraints + guarded upsert verified by hand) and
`src/ingestion/hn_client.py` are done. On `main`, clean, level with `origin/main`, 5 commits —
there is no `feat/loader` branch. `DATABASE_URL` is in `.env` and `.env.example`.

**The dev environment moved to WSL2** (bash, Docker Engine native in WSL, `psql` 17.10 on the host,
Ollama still on the Windows host at `localhost:11434`). Consequence that matters: **Docker is
freshly installed, so there are no volumes and the database does not exist.** The schema was applied
in the old Docker Desktop `pgdata` volume, which is gone. See the environment table in
docs/ROADMAP.md.

`src/ingestion/load.py` — half written. Working: `to_thread_month()` and `thread_to_rows()`
(mypy clean, 276 rows off the July 2026 thread; the `"HN"` case bug is **fixed**). Not written: the
psycopg half.

**Next up (in order):**
1. `init/001_extensions.sql` with `CREATE EXTENSION IF NOT EXISTS vector;` — `init/` is empty and git
   doesn't track empty dirs, so pgvector gets created nowhere. **Do this first:** there is no
   `pgdata` volume now, so the next `docker compose up -d` is a real first boot and the entrypoint
   will actually run it. Once the volume exists it silently never runs again.
2. `docker compose up -d`, wait for healthy, then re-apply `001_raw_postings.sql` (re-runnable by
   design). The container will be `job-market-agent-db-1` — the directory name scopes it.
3. `UPSERT_SQL` — draft still says `ON CONFLICT (external_id)`; the only unique constraint is
   `(source, external_id)`, so it raises `42P10 there is no unique or exclusion constraint matching
   the ON CONFLICT specification` and cannot run at all. Add the `WHERE raw_text IS DISTINCT FROM
   EXCLUDED.raw_text` guard, `updated_at = now()` (no trigger exists), and `RETURNING (xmax = 0)`.
   Write it in psql first.
4. `upsert_postings(conn, rows) -> LoadStats` — caller owns the transaction, returns counts, does
   not print. Wire into `__main__`. Note: a suppressed guarded update returns *no row*, so
   `unchanged = len(rows) - returned`; `with psycopg.connect()` commits on clean exit. While here:
   `load.py:40` rebinds `thread_to_rows` over the function it just called (5 mypy errors), and
   `thread_to_rows[2]` will `IndexError` on a thread with under 3 comments.
5. Verify idempotency: run twice → `N/0/0` then `0/0/N`; hand-edit one `raw_text` → `0/1/N-1`.
6. Remotive client, then load to the ~700-posting target.

**Watch out:**
- Docker needs no babysitting now — it is a systemd service, `enabled` at boot, and the user is in
  the `docker` group (no `sudo`). The old "start Docker Desktop first" step is gone.
- `uv run mypy src` works directly; the broken `.venv/Scripts/mypy.exe` trampoline was a
  Windows-only uv bug and no longer applies.
- Proxy: `~/.proxy.env` is the single source of truth (`autoProxy=false`). Never put globs (`127.*`,
  `<local>`) in `no_proxy` — curl tolerates them, `requests`/`httpx` do not, and localhost calls
  then silently route through the proxy. The Docker **daemon** proxy is a separate scope in
  `/etc/systemd/system/docker.service.d/`.
- `.env.example` briefly held a real-looking `DEEPSEEK_API_KEY` (working tree only, never
  committed); it is an empty placeholder again. Keep secrets out of that file.
- `hn_client.py` docstrings/comments were removed deliberately; don't flag it again.
- Untracked junk in the tree: `.em.swp` and `.claude/settings.json` (`.gitignore` only covers
  `.claude/settings.local.json`).

Start by checking the current state of the repo in case I've changed things since.

---
