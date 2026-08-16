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

**Where we left off (2026-08-16):** Phase 1 is closed. Phase 2's extraction path is **wired end to
end and verified** on one row per source — `source_adapters` → LLM → `schema` validators →
`transform` → `NormalizedRole`. Four modules done: `normalize.py`, `schema.py`,
`source_adapters.py`, `transform.py`. Uncommitted at wrap-up; ruff and mypy clean.

**Next up:** hand-label `evals/gold_labeled.json` → eval script → extraction pipeline module with
the retry loop → Langfuse. Offline fixtures per source belong in the same phase.

**Settle the four labeling questions in ROADMAP "Still open" before labeling** — each one decides
what a correct label *is*, and relabeling 40 rows twice is the expensive mistake here. Shortest
version: `stack` ground truth barely intersects extracted stack; card fields contradict body prose
on Habr and Remotive; `location` has no normalizer; a quote for a `None` field goes unchecked.

Two things that will bite the eval script specifically:
- **Containment runs against `html_to_text(raw_text)`, never `raw_text`** — and must whitespace-
  normalize both sides, because source prose is hard-wrapped mid-sentence.
- **Only Habr's salary has a known period.** Web3 and Remotive amounts stay unconverted in
  `salary_raw`; skip salary scoring there rather than guessing a period.

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
  comments — deliberate, don't flag it again and don't add them back. `schema.py`, `transform.py`
  and `source_adapters.py` do carry short docstrings where a model's *contract* is non-obvious.
- **Import direction inside `extraction/` is one-way:** `normalize` is model-free, `schema` and
  `source_adapters` import it, `transform` imports both. Don't put fill-down back in `normalize.py`.
- `experiments/` is a scratchpad: never imported by `src/`, relative paths fine, no tests. A cell
  graduates to `src/` as a function with a test. `.gitignore` excludes `experiments/*` entirely.

Everything else that used to live here — Habr/Web3 API quirks, imputed salaries, the Habr labeling
rules, the spike defects — is now in ROADMAP.md under "Durable gotchas" and Phase 2. Don't duplicate
it back into this file.

Start by checking the current state of the repo in case I've changed things since.

---
