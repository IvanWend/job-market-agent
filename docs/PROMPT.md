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

**Where we left off (2026-08-01):** Phase 1 (ingestion) — HN ingestion is now **done end-to-end**.
`docker-compose.yml`, `db/schema/001_raw_postings.sql`, `src/ingestion/hn_client.py`, and
`src/ingestion/load.py` (idempotent upsert) are all working and verified. Still on `main`, not a
branch. **Uncommitted:** `docker-compose.yml` (port now scoped to `127.0.0.1`) and `load.py`;
`init/` is untracked. Commit these before starting Remotive.

**Next up (in order):**
1. Remotive client — semi-structured JSON, the deliberate contrast with HN's pure prose.
2. Load toward the ~700-posting target (276 HN so far + Remotive).
3. Collect gold-set candidates (~30 deliberately messy HN posts) while ingesting, per the ROADMAP.

**Watch out:**
- Docker needs no babysitting — it is a systemd service, `enabled` at boot, and the user is in the
  `docker` group (no `sudo`) — but stopping the rogue Windows Postgres service *did* need an
  elevated PowerShell (`Start-Process -Verb RunAs`).
- `uv run mypy src` works directly; the broken `.venv/Scripts/mypy.exe` trampoline was a
  Windows-only uv bug and no longer applies.
- Proxy: `~/.proxy.env` is the single source of truth (`autoProxy=false`). Never put globs (`127.*`,
  `<local>`) in `no_proxy` — curl tolerates them, `requests`/`httpx` do not, and localhost calls
  then silently route through the proxy. The Docker **daemon** proxy is a separate scope in
  `/etc/systemd/system/docker.service.d/`.
- `hn_client.py` docstrings/comments were removed deliberately; don't flag it again.
- Untracked junk in the tree: `.em.swp` and `.claude/settings.json` (`.gitignore` only covers
  `.claude/settings.local.json`).

Start by checking the current state of the repo in case I've changed things since.

---
