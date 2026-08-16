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
- **When I'm writing the code, spec it Input → Logic → Output**, one compact block per function,
  examples taken from `evals/gold_40_candidates.json` rather than invented.
- **Keep docs and comments lean.** ROADMAP is a checklist plus locked decisions, not a design doc.
  Comments earn their place only where a decision is non-obvious — the rationale belongs in chat.
- When I say I've implemented something, verify it: read the code and run it before assessing.
  Paste-errors-not-fixes — explain the error, don't silently patch.
- I'm doing this to learn — explain the concept when I ask, not by default. Every file must pass
  the explain-back test before we call a step done.
- Watch my token budget: prefer a fresh session per phase over dragging a long context around, and
  say so when a wrap-up + new session is the cheaper move.

**Where we left off (2026-08-16):** Phase 1 is closed — ingestion, the frozen eval DB (1,098 rows,
`jobmarket_eval` behind the read-only `jobmarket_ro`) and the seeded gold-set sample are done and
verified. Phase 2 has started: `src/extraction/normalize.py` is written and verified over all 40
gold rows, with `remote_policy_enum()` half-finished at the bottom of the file.

**Next up:** finish `remote_policy_enum()` (takes a bool as well as a string — Web3 `is_remote`,
Habr `remoteWork`) → `schema.py` → source adapters → hand-label `evals/gold_labeled.json` → eval
script → Langfuse. Offline fixtures per source belong in the same phase.

`schema.py` shape, agreed but not yet written: two verbatim models (`RoleExtraction`,
`PostingExtraction`) plus a derived normalized pair. The four inheritable fields — `stack`,
`location`, `remote_policy`, `employment_type` — sit on both, `| None` at role level meaning
*inherit*. `source_quotes` is scoped to each model's own fields so the key check is
`set(quotes) <= set(model_fields)`. One validator per spike defect.

**Watch out:**
- Docker needs no babysitting — systemd service, enabled at boot, user is in the `docker` group. A
  rogue Windows Postgres service on the same port has bitten this before — if `docker compose up`
  fails to bind 5432, check `Get-Service *postgres*` in an elevated PowerShell.
- Proxy: `~/.proxy.env` is the single source of truth. Never put globs (`127.*`, `<local>`) in
  `no_proxy` — `requests`/`httpx` don't honor them the way `curl` does, and localhost calls silently
  route through the proxy.
- **`purge.py` deletes rows the boards will not serve again.**
  `evals/snapshots/2026-08-12_raw.dump` is the only copy; it is now committed. Re-snapshot to a new
  date-stamped filename, never in place.
- `docker exec ... pg_dump "$DATABASE_URL"` expands the variable on the **host** — an unsourced
  `.env` passes an empty string and pg_dump falls back to the container socket as `root`
  (`FATAL: role "root" does not exist`). `set -a; . ./.env; set +a` first, or pass
  `-U jobmarket -d jobmarket`. Same trap as bare `psycopg.connect()`.
- The ingestion clients, `generate_gold_dataset.py` and `normalize.py` carry no docstrings and few
  comments — deliberate, don't flag it again and don't add them back.
- `experiments/` is a scratchpad: never imported by `src/`, relative paths fine, no tests. A cell
  graduates to `src/` as a function with a test. `.gitignore` excludes `experiments/*` entirely.

Everything else that used to live here — Habr/Web3 API quirks, imputed salaries, the Habr labeling
rules, the spike defects — is now in ROADMAP.md under "Durable gotchas" and Phase 2. Don't duplicate
it back into this file.

Start by checking the current state of the repo in case I've changed things since.

---
