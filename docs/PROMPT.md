# Session kickoff prompt

Paste this to start the next Claude Code session:

---

Read README.md and docs/ROADMAP.md first — a job-market intelligence agent: ingest HN "Who is
Hiring" + Remotive + Adzuna postings → LLM structured extraction (Pydantic, quote-grounded) →
Postgres + pgvector → DeepSeek agent with tools → FastAPI. This is the **service/infra** portfolio
project; the retrieval/agent lab is the separate **product-search** repo. Built skill-by-skill, to
learn.

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

**Where we left off (2026-08-01):** Phase 1 (ingestion) is **done end-to-end** — all three sources
working. `docker-compose.yml`, `db/schema/001_raw_postings.sql`, `src/ingestion/hn_client.py`,
`remotive_client.py`, `adzuna_client.py`, and `load.py` (idempotent upsert, retry/backoff on
Adzuna's page loop) are all working and verified. **2,807 postings loaded** (276 HN + 34 Remotive +
2,497 Adzuna) — past the ~700 target. Adzuna was pulled forward from Phase 5 deliberately: Remotive's
free API only ever exposes ~34 currently-live postings (no historical/paginated data), so it
couldn't carry the volume target alone. Full build/bug log is in ROADMAP.md's "Remotive + Adzuna
additions" section. **Uncommitted:** `load.py`, `init/`, `remotive_client.py`, `adzuna_client.py`,
plus this doc wrap-up — commit before starting Phase 2.

**Next up (in order):**
1. Collect gold-set candidates (~30 deliberately messy HN posts) — the one item left in Phase 1.
2. Phase 2: finalize the Pydantic extraction schema (open questions logged in ROADMAP.md), then
   build the extraction pipeline.

**Watch out:**
- Docker needs no babysitting — it is a systemd service, `enabled` at boot, and the user is in the
  `docker` group (no `sudo`) — but stopping the rogue Windows Postgres service *did* need an
  elevated PowerShell (`Start-Process -Verb RunAs`).
- `uv run mypy src` works directly; the broken `.venv/Scripts/mypy.exe` trampoline was a
  Windows-only uv bug and no longer applies.
- Proxy: `~/.proxy.env` is the single source of truth (`autoProxy=false`). Never put globs (`127.*`,
  `<local>`) in `no_proxy` — curl tolerates them, `requests`/`httpx` do not, and localhost calls
  then silently route through the proxy. The Docker **daemon** proxy is a separate scope in
  `/etc/systemd/system/docker.service.d/`. It's also flaky on long-running loops against external
  hosts — a real run died mid-`adzuna_client.py` page loop on a dropped proxy connection; retry/
  backoff there now absorbs it.
- `hn_client.py`, `remotive_client.py`, and `adzuna_client.py` docstrings/comments were removed
  deliberately across all three; don't flag it again.
- Untracked junk in the tree: `.claude/settings.json` (`.gitignore` only covers
  `.claude/settings.local.json`).

Start by checking the current state of the repo in case I've changed things since.

---
