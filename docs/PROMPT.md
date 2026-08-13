# Session kickoff prompt

Paste this to start the next Claude Code session:

---

Read README.md and docs/ROADMAP.md first — a remote job search agent over heterogeneous boards:
ingest HN "Who is Hiring" + Remotive + Web3.career + Habr Career postings, **kept to a rolling
90-day window** → LLM structured extraction (Pydantic, quote-grounded) → Postgres + pgvector →
DeepSeek agent with tools → FastAPI. This is the **service/infra** portfolio project; the
retrieval/agent lab is the separate **product-search** repo. Built skill-by-skill, to learn.

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

**Where we left off (2026-08-13):** **Phase 1 is closed.** Ingestion, the frozen eval DB, and the
gold-set sample are all done and verified — 1,098 rows, `jobmarket_eval` restored with
`db_meta.role = 'eval'` behind the read-only `jobmarket_ro`, and `evals/gold_40_candidates.json`
sampled reproducibly (seed `20260813`, hn 16 / habr 10 / web3 8 / remotive 6). ROADMAP.md now covers
only what is left; it opens with a data-flow diagram. ruff and mypy are clean.

**Next up:** Phase 2 in ROADMAP order — source adapters → finalize the Pydantic schema (five spike
defects + the new `doc_type` enum) → hand-label `evals/gold_labeled.json` → eval script → Langfuse.
Offline fixtures per source are still unbuilt and belong in the same phase.

**Watch out:**
- Docker needs no babysitting — systemd service, enabled at boot, user is in the `docker` group. A
  rogue Windows Postgres service on the same port has bitten this before — if `docker compose up`
  fails to bind 5432, check `Get-Service *postgres*` in an elevated PowerShell.
- Proxy: `~/.proxy.env` is the single source of truth. Never put globs (`127.*`, `<local>`) in
  `no_proxy` — `requests`/`httpx` don't honor them the way `curl` does, and localhost calls silently
  route through the proxy.
- **`purge.py` deletes rows the boards will not serve again.** `evals/snapshots/2026-08-12_raw.dump`
  is the only copy and is still **untracked** — commit it before the next purge, or a `git clean`
  takes it.
- `docker exec ... pg_dump "$DATABASE_URL"` expands the variable on the **host** — an unsourced
  `.env` passes an empty string and pg_dump falls back to the container socket as `root`
  (`FATAL: role "root" does not exist`). `set -a; . ./.env; set +a` first, or pass
  `-U jobmarket -d jobmarket`. Same trap as bare `psycopg.connect()`.
- The ingestion clients and `generate_gold_dataset.py` carry no docstrings and few comments —
  deliberate, don't flag it again.
- `experiments/` is a scratchpad: never imported by `src/`, relative paths fine, no tests. A cell
  graduates to `src/` as a function with a test. `.gitignore` excludes `experiments/*` entirely.

Everything else that used to live here — Habr/Web3 API quirks, imputed salaries, the Habr labeling
rules, the spike defects — is now in ROADMAP.md under "Durable gotchas" and Phase 2. Don't duplicate
it back into this file.

Start by checking the current state of the repo in case I've changed things since.

---
