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

**Where we left off (2026-08-11):** the last session produced **decisions, not code** — nothing was
implemented. The project is being repointed at remote-only sources with a rolling 90-day freshness
window; corpus size is explicitly no longer a goal. Full write-up is **Phase 1b in ROADMAP.md**
(source-by-source probe results, retention rules, frozen-eval-DB design) — read that section before
touching ingestion.

Short version: **HN stays** (rolling; the only pure-prose source), **Remotive stays**,
**Web3.career and Habr Career get added**, **Adzuna is cut**, **CryptoJobsList is parked** (no
usable public feed — its RSS returns zero items and the site API is Cloudflare-guarded). API keys
were applied for at Web3.career, CryptoJobsList, and Habr on 2026-08-10, expected back 2026-08-11.
**Habr needs no key** — its frontend API answered fine unauthenticated — so it's unblocked either way.

Phase 2 is still designed but not implemented; the schema decisions and the five `pydantic-ai` spike
defects in ROADMAP.md are unchanged and still the plan.

**Next up (in order):**
1. **Take the frozen snapshot — before anything deletes rows.** Only step with a real deadline:
   4,176 HN rows fall outside the 90-day window and are unrecoverable once purged. ~2.9 MB
   compressed, commit it. Design and exact commands are in ROADMAP.md Phase 1b.
2. **Fix the broken working tree** — `hn_client.py` lost `find_hiring_threads()` but `load.py:12`
   still imports it, so `load.py` won't even import. 8 ruff errors alongside it.
3. `003_*.sql` — widen the `source` CHECK for `web3`/`habr`, `posted_at NOT NULL`, add `db_meta`.
4. Restore `jobmarket_eval` + read-only role; then purge + ingest-side age filter behind the
   `db_meta` guard.
5. Habr client (unblocked), then Web3.career client once the key lands.
6. Only then back to Phase 2: source adapters → finalize schema → label the gold set → eval script.

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
- `.env` line `WEB3_API_KEY =` has a space before `=` — bash reads it as a command when sourcing,
  and python-dotenv doesn't see the key name you expect. Fix it.
- Web3.career without a valid token **302s to its sales page** rather than erroring; `web3_client.py`
  swallows that in a catch-all `except` and returns `[]`. Five more defects in that file are listed
  in ROADMAP.md Phase 1b — it was written before a token existed, so its field names are guesses.
- Habr's list endpoint has **no description text** — cards only. The posting prose needs an HTML
  parse of `/vacancies/{id}`; the JSON detail endpoint just serves the SPA shell.
- `adzuna_client.py`'s retry logic only catches `ConnectionError`/`Timeout` — a 429 or 5xx still
  kills the whole `load.py` run. Known, not fixed, and now lower priority since Adzuna is cut as a
  live source (its rows stay in the frozen eval DB).
- The old note that "276 HN rows have NULL `posted_at`" is **stale** — verified 0 NULLs on
  2026-08-11. The 276 is the count of HN rows *inside* the 90-day window, which is a coincidence.
- The gold-set's random (not hand-curated) selection is a real quality tradeoff — worth revisiting
  if Phase 2 eval accuracy looks off and the postings themselves turn out to be too easy/uniform.
  It is also **no longer regenerable** once the purge runs, hence step 1.
- `hn_client.py`, `remotive_client.py`, and `adzuna_client.py` have no docstrings/comments —
  deliberate, don't flag it again.
- Adzuna's `salary_min`/`salary_max` are **imputed** on 9 of 10 gold rows
  (`"salary_is_predicted": "1"`, tell: min == max exactly). Only `"0"` rows are usable as salary
  ground truth. Its `description` is also truncated at ~1.5KB, so held-out fields often have no
  evidence in the input — legitimate nulls, not extraction misses.
- `experiments/` is a scratchpad: never imported by `src/`, relative paths fine, no tests. A cell
  graduates to `src/` as a function with a test. The failure mode is a notebook that quietly
  becomes load-bearing. `experiments/.ipynb_checkpoints/` still isn't gitignored, and
  `experiments/` is untracked — decide before the next commit whether notebooks get committed
  (if so, strip outputs, e.g. `nbstripout`).

Start by checking the current state of the repo in case I've changed things since.

---
