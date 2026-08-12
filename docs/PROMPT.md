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

**Where we left off (2026-08-12):** **ingestion is done — all four sources are live.** The Habr
client landed, so the corpus is now 1,098 rows — hn 502, habr 460, web3 100, remotive 36, all inside
the 90-day window, zero Adzuna. `load.py` runs four independent source pipelines and each fetcher is
handed the `external_id`s already stored for its source; only Habr uses them, because only Habr pays
one HTTP request per posting for its prose. A cold Habr run is ~15 min, a warm one 35s. All 460 Habr
rows carry a `description_html` (avg 2,786 chars, none missing). ruff and mypy are clean.

**Next up (in order):**
1. **Snapshot the four-source corpus**, then resample the gold set per source from it. The old
   pre-pivot dump was deleted — it predated web3 and habr, so it could only label half the sources.
2. **Restore `jobmarket_eval`** from that snapshot + create the read-only role, then
   `UPDATE db_meta SET role = 'eval'` in it.
3. **Cache a fixture response per source** so the demo path runs offline.
4. **Phase 2**: source adapters → finalize the Pydantic schema → label the gold set against the
   frozen snapshot → eval script. The schema decisions and the five `pydantic-ai` spike defects in
   ROADMAP.md are unchanged and still the plan.

**Watch out:**
- Docker needs no babysitting — systemd service, enabled at boot, user is in the `docker` group. A
  rogue Windows Postgres service on the same port has bitten this before — if `docker compose up`
  fails to bind 5432, check `Get-Service *postgres*` in an elevated PowerShell.
- Proxy: `~/.proxy.env` is the single source of truth. Never put globs (`127.*`, `<local>`) in
  `no_proxy` — `requests`/`httpx` don't honor them the way `curl` does, and localhost calls silently
  route through the proxy.
- `docker exec ... pg_dump "$DATABASE_URL"` expands the variable on the **host** — if `.env` wasn't
  sourced it passes an empty string and pg_dump falls back to the container socket as user `root`
  (`FATAL: role "root" does not exist`). Either `set -a; . ./.env; set +a` first, or pass
  `-U jobmarket -d jobmarket` explicitly. Same trap as the `psycopg.connect()` one.
- **`purge.py` deletes rows that the boards will not serve again**, and **there is currently no
  snapshot at all** — the pre-pivot dump was deleted. It is dry-run by default and refuses to run
  unless `db_meta.role = 'live'`, but snapshot before the next purge.
- **`conn.transaction()` on an idle psycopg connection is a real `BEGIN`/`COMMIT`, not a savepoint.**
  It only nests as a savepoint inside an open transaction — which is why `upsert_posting` opens an
  explicit outer block, and why the `known_ids` `SELECT` in `load_source` is wrapped in one too. A
  bare `SELECT` leaves the connection `INTRANS` and silently demotes the next block to a savepoint.
- Web3.career: hard cap of 100 jobs per call, `page`/`offset` are ignored, dates are RFC 2822 (use
  `date_epoch`), and an invalid token 302s to the sales page instead of erroring. Its ToS requires
  linking back via `apply_url` and crediting web3.career as the source.
- Habr: the list endpoint has **no description text** — cards only, so the prose comes from an HTML
  parse of `/vacancies/{id}` (`div.vacancy-description__text`); the JSON detail endpoint serves the
  SPA shell. `per_page=50` is the real cap — a larger value is echoed back in `meta.perPage` but
  still yields 50 rows, so page off `meta.totalPages`. Its offset pagination over a live date-desc
  feed is **racy**: a posting published mid-run shifts the pages and duplicates a boundary card
  (459 cards → 458 ids on the first run), so `fetch_habr_rows` dedupes by id.
- **Imputed salaries are not ground truth:** Web3's `estimated_*` and Habr's `predictedSalary` are
  the sites' own guesses. Only Web3's `salary_min_value`/`salary_max_value` and Habr's
  `salary.from`/`salary.to` are employer-stated.
- The gold set is being resampled from the new four-source snapshot. Random selection was a known
  quality tradeoff — this time weight it toward HN (the only multi-role source) and hand-pick a few
  messy postings. The old 30 rows survive with full `raw_text` in `evals/gold_30_candidates.json`.
- The ingestion clients have no docstrings/comments — deliberate, don't flag it again.
- `experiments/` is a scratchpad: never imported by `src/`, relative paths fine, no tests. A cell
  graduates to `src/` as a function with a test. `.gitignore` now excludes `experiments/*` entirely.

Start by checking the current state of the repo in case I've changed things since.

---
