# Roadmap

Building the **service / infrastructure** half of my AI-engineering portfolio one phase at a time:
ingestion → LLM extraction + evals → storage/retrieval → agent → serving. Later phases build on
earlier ones. The pure retrieval + agent lab lives in **product-search**; see
[out of scope](#deliberately-out-of-scope-lives-in-product-search).

## Working style (for AI-assisted sessions)

- **Short, structured answers.** Numbered flow or bullets, not prose walls. Actionable steps first,
  rationale only where a decision hinges on it.
- I write the code; the assistant guides, reviews, and verifies (read + run before assessing).
- Paste errors, not fixes. No silent edits to project files.

## Build status (updated 2026-07-28)

**Working now:** `docker-compose.yml` (Postgres 17 + pgvector, healthcheck, `pgdata` volume,
`init/` mounted). `db/schema/001_raw_postings.sql` applied and verified. `hn_client.py` is
**complete**: `find_latest_hiring_thread()` resolves the newest thread via `search_by_date`, and
`fetch_thread(story_id)` returns a typed `HNThread` with its top-level comments. Toolchain is
uv + ruff + mypy, all three clean. Repo is on git (`main`).

**Decision (2026-07-26) — two schema mechanisms, one job each.** Compose mounts `./init` at
`/docker-entrypoint-initdb.d`, whose scripts run **only when the data directory is empty** — first
boot, then silently never again. That makes it *bootstrap*, not migration. So `db/schema/` stays the
re-runnable path applied by hand (the skill worth having), and `init/` is reserved for at most
`CREATE EXTENSION IF NOT EXISTS vector;`. `001_raw_postings.sql` must not live in both.

**Decision (2026-07-27) — `/items/` over paginated search.** Two Algolia routes reach a thread's
comments. `search_by_date?tags=comment,story_<id>` returns every comment at every depth (436 for the
July 2026 thread, of which 276 are top-level), so it needs a client-side `parent_id` filter and
pagination once a thread passes the 1000-hit ceiling. `/api/v1/items/<story_id>` returns the tree in
one request, where `children` *is* the top-level list — no pagination, no depth filter — and carries
the story's own `created_at` and `title` in the same payload. Verified: both routes agree at 276.

**Decision (2026-07-27) — the client speaks HN, the loader speaks SQL.** `fetch_thread` returns
`HNThread`/`HNComment` (frozen dataclasses), *not* dicts shaped like table columns, so that exactly
one module knows `raw_postings`' column names when the Remotive client lands. Consequence: the
client returns `created_at` as the **raw ISO string**; `load.py` owns the truncation to
`thread_month`. The field is deliberately not named `thread_month` in the client — it holds a full
timestamp, and a name that promises a month would read as correct in review while being wrong.
`raw_postings_thread_month_is_month_start` is the backstop if the loader ever forgets.

**In progress — `load.py` flow** (skeleton written 2026-07-28; runs end-to-end, DB half unwired):

1. [x] Pre-flight: `docker compose up -d`, `DATABASE_URL` in `.env`, branch `feat/loader`.
2. [x] `to_thread_month(created_at: str) -> date` — `fromisoformat` (handles the `Z`), stay in UTC,
   `.date().replace(day=1)`. Returns `date(2026, 7, 1)`; mypy clean.
3. [~] `thread_to_rows(thread) -> list[tuple]` — emits `(source, external_id, raw_text,
   thread_month)`, month derived once outside the loop; mypy clean. *One bug left: `source` is
   `"HN"`, but the CHECK is `source IN ('hn', …)`.* Throwaway when Remotive lands.
4. [ ] `UPSERT_SQL` — write it in psql by hand first. *Current draft names `title`/`created_at`/
   `text` (none exist), omits `source`, and conflicts on `(external_id)` where the unique
   constraint is `(source, external_id)`.*
5. [ ] `upsert_postings(conn, rows) -> LoadStats` — source-agnostic, reused by Remotive. Caller
   owns the transaction. Returns counts; does not print.
6. [x] `__main__`: find thread → fetch → rows → print. Verified: 276 rows off the July 2026 thread.
   Still needs the upsert + count output wired in.
7. [ ] Verify: run twice → `N/0/0` then `0/0/N`. Then hand-edit one `raw_text` in psql → `0/1/N-1`.

Gotchas: `DO UPDATE` must set `updated_at = now()` (no trigger exists); count via
`RETURNING (xmax = 0)` — a suppressed guarded update returns *no row*, so `unchanged = len(rows) -
returned`; `with psycopg.connect()` commits on clean exit (not autocommit); `%s` placeholders only.

**Compose note:** `container_name:` was removed. It is a *global* Docker name, so after the project
directory was renamed (`job-market-agent` → `jobmarket`) the old stopped container still owned the
name and blocked `up`. Compose now scopes the name itself (`jobmarket-db-1`). An orphaned
`job-market-agent_pgdata` volume from the old project is still on disk and can be deleted.

**Housekeeping / tech debt:**
- [x] Consolidated the HN client into `src/ingestion/`; fixed both package `__init__.py` files.
- [x] Dropped `requirements.txt` (UTF-16 `pip freeze`, ~90 stale transitive deps) for `uv` +
      `pyproject.toml` + committed `uv.lock`. Direct deps only: `requests`, `psycopg[binary]`,
      `python-dotenv`. `uv sync` prunes anything undeclared — it removed a leftover `httpx`.
- [x] Git repo bootstrapped: `main` branch, baseline commit, `.gitignore`, `.env.example` committed.
- [x] `.gitattributes` forces LF — `core.autocrlf=true` is set globally and CRLF files break once
      mounted into the Linux Postgres container.
- [x] `.env` has `POSTGRES_PASSWORD`; `DEEPSEEK_API_KEY` placeholder in `.env.example` for Phase 2.
- [x] `hn_client.py` split string literal (`"objec" "tID"`) rejoined; still resolves the thread.
- [x] ruff + mypy in the `dev` dependency group (ruff excludes `*.md` so it leaves the aligned
      comments in the doc fences alone).
- [x] Closed the mypy `params` error: annotated `dict[str, str | int]`. Mixed `str`+`int` values
      infer as `dict[str, object]`, and `object` isn't in the union `requests.get` accepts — so the
      fix is an annotation, not a value change. `mypy src` is now clean; consider flipping
      `disallow_untyped_defs = true`.
- [x] `ruff format` applied to `hn_client.py`; all four files now report "already formatted".
      Adopting it repo-wide is therefore free — no reformat churn pending.
- [ ] **Tooling gotcha:** `.venv/Scripts/mypy.exe` is a broken uv trampoline (`failed to
      canonicalize script path`). Use `uv run python -m mypy src`. `ruff.exe` works fine.
- [ ] `init/` is empty, and git does not track empty directories — so a fresh clone has no `init/`,
      Docker auto-creates it, and `CREATE EXTENSION vector` runs nowhere. Add
      `init/001_extensions.sql` before Phase 3 or pgvector will fail confusingly.

**Git — ongoing across every phase:**
- [ ] Every feature: branch → PR → self-review → merge (no direct commits to `main`)
      — **not yet honoured**: all three commits so far went straight to `main`. Start with the
      loader on a branch.
- [ ] Commit early and often (lesson: mid-session revert on cv-tailor-ru)

## Phase 1 — Ingestion (no LLM calls) ← IN PROGRESS

- [x] Docker Compose: Postgres 17 + pgvector (healthcheck, named volume, `init/` entrypoint)
- [x] Algolia HN client
  - [x] `find_latest_hiring_thread()` → newest thread `story_id` + title
  - [x] `fetch_thread(story_id)` → `HNThread` with all **top-level** comments. One `/items/` call,
        so no pagination. Comment `id` → `str` (it is the `external_id` dedup key; the API returns
        an int). Text kept as **verbatim HTML** — the table is a replay buffer, and stripping is a
        lossy parse that Phase 2 should do instead. Drops unusable comments via
        `(child.get("text") or "").strip()`, which covers all three shapes: absent key, present-but-
        null (deleted), and whitespace-only. `.get("text", "")` does **not** — a default only fires
        on a missing key, never on a present `null`.
- [ ] Remotive client
- [~] `raw_postings` schema + loader with dedup
  - [x] DDL `db/schema/001_raw_postings.sql` — applied clean, re-apply is a no-op. Verified: the
        guarded upsert gives `INSERT 0 1` / `0 0` / `0 1`, `(remotive, test-1)` inserts alongside
        `(hn, test-1)`, and all five constraints reject bad rows (bad source, mid-month
        `thread_month`, HN without a month, blank text, manual `id`).
  - [~] loader: idempotent upsert on `(source, external_id)` — SQL verified by hand in psql;
        `load.py` skeleton written (fetch → rows → print works, 276 rows). The `psycopg` half and
        the row/column mapping are still wrong — see the numbered flow above.
- [ ] Target: ~700 raw postings loaded
- [ ] Collect gold-set candidates while ingesting (copy ~30 deliberately messy HN posts aside)

## Phase 2 — Extraction + evals

*Known ground: LLM extraction, Pydantic, evals (cv-tailor-ru patterns).*

*Concept:* the Pydantic schema is the single contract for extraction and evals; every non-null field
carries a **verbatim source quote**, and evals check quote-in-text containment — not just values — to
catch fabrication.

- [ ] Finalize the Pydantic schema (resolve open questions below)
- [ ] Extraction pipeline: JSON mode + retry on validation failure
- [ ] Hand-label `evals/gold_30.json` (~30 messy HN postings)
- [ ] Eval script: per-field accuracy (exact match for enums/numbers, set-F1 for `skills[]`,
      containment for `source_quotes`)
- [ ] Langfuse wired into every extraction call
- [ ] Iterate the prompt until acceptable accuracy (set the threshold after the first run)

**Open schema questions:**
- `skills` vs `stack` boundary — or merge into one tagged list?
- Salary normalization: hourly/monthly → annual conversion rules
- Multi-role postings (one comment, three positions) — split or take first?

## Phase 3 — Storage + retrieval

*Concept (interview material — don't rush):* what an embedding vector is, cosine similarity, why
384-dim; why semantic search finds "k8s" for the query "kubernetes"; what pgvector adds to Postgres
and how HNSW/IVF differs from a brute-force scan.

- [ ] Embedding pipeline — decide what text gets embedded (raw vs. structured summary; likely the
      structured summary) and document why
- [ ] pgvector search + basic metadata filters (seniority, remote)
- [ ] SQL analytics queries (skill frequency, salary distributions) — hand-written

## Phase 4 — Agent

*Concept:* a hand-rolled DeepSeek tool-calling loop; `sql_query` uses **whitelisted templates, not
raw SQL**.

- [ ] Tools: `sql_query` (whitelisted), `vector_search`, `resume_match`
- [ ] Agent loop with DeepSeek tool-calling
- [ ] Agent eval suite (~15 canned questions with expected-answer assertions vs. SQL ground truth)
- [ ] FastAPI endpoint with SSE streaming

*Concept (Phase 4 tooling):* endpoints, dependency injection, SSE streaming; trace one request
end-to-end (HTTP in → agent loop → tool calls → streamed response).

## Phase 5 — Polish

- [ ] README with architecture diagram, eval-results table, demo GIF
- [ ] (Optional) Adzuna source, cross-source dedup (fuzzy company+title), trend charts

## Ownership split (what I write by hand vs. delegate)

| Written by hand (learning targets) | Delegated to Claude Code (plumbing) |
|---|---|
| Extraction prompt + Pydantic schema | Docker Compose, scaffolding, config |
| Eval scripts + gold-set labeling | HN/Remotive API clients, pagination |
| Agent loop + tool definitions | FastAPI boilerplate, DB migrations |
| SQL analytics queries | Test scaffolding, refactors |
| Embedding + vector-search logic (v1) | |

**Explain-back test:** every generated file must pass *"could I walk an interviewer through this
file — why each part exists?"* before its phase is marked done. If not, ask for an explanation;
don't move on.