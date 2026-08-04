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

## Build status (updated 2026-08-01)

**Working now:** all three ingestion clients are **complete** — `hn_client.py`, `remotive_client.py`,
and `adzuna_client.py` (pulled forward from Phase 5; see Phase 1 below) — plus `load.py`, which
fetches all three, converts each to `(source, external_id, raw_text, thread_month)` rows, and
idempotently upserts them. Toolchain is uv + ruff + mypy, all clean. Repo is on git (`main`, level
with `origin/main`), but `load.py`, `init/`, `remotive_client.py`, and `adzuna_client.py` are
uncommitted as of this update.

**Running now:** the database, fully (re-)provisioned in the new WSL2 Docker install.
`init/001_extensions.sql` bootstrapped `vector` + `pg_trgm` on first boot, `001_raw_postings.sql`
is applied and verified, and the loader has round-tripped all three sources for real:
**2,807 postings loaded** (276 HN + 34 Remotive + 2,497 Adzuna) — past the ~700 target (see the
`load.py` flow section below).

**Done — `load.py` flow** (skeleton written 2026-07-28; DB half landed and verified 2026-08-01):

1. [x] Pre-flight: `docker compose up -d`, re-apply `001_raw_postings.sql`, `DATABASE_URL` in
   `.env`. *(Still landed on `main`, not a branch — see Git section below.)*
2. [x] `to_thread_month(created_at: str) -> date` — `fromisoformat` (handles the `Z`), stay in UTC,
   `.date().replace(day=1)`. Returns `date(2026, 7, 1)`; mypy clean.
3. [x] `thread_to_rows(thread) -> list[tuple]` — emits `(source, external_id, raw_text,
   thread_month)`, month derived once outside the loop; mypy clean. Throwaway when Remotive lands.
4. [x] `UPSERT_SQL` — conflict target is `(source, external_id)`, matching the real unique
   constraint, plus the `WHERE raw_text IS DISTINCT FROM EXCLUDED.raw_text` guard, `updated_at =
   now()`, and `RETURNING (xmax = 0)` to tell insert from update in one round-trip.
5. [x] `upsert_postings(conn, rows) -> LoadStats` — one `execute` per row (needed for per-row
   `RETURNING`; `executemany` would discard results), classified via `fetchone()`: no row =
   suppressed/unchanged, `xmax = 0` = insert, else update. Caller's
   `with psycopg.connect(db_url) as conn:` owns commit/rollback — the function doesn't call
   `commit()` itself.
6. [x] `__main__`: find thread → fetch → rows → upsert → print counts.
7. [x] Verified against the real July 2026 HN thread (276 postings):
   - Run 1: fresh insert of all 276.
   - Run 2 (re-run, unchanged data): `0 / 0 / 276` — true no-op, `updated_at` untouched.
   - Hand-edited one row's `raw_text` in psql, ran again: `0 / 1 / 275` — that row's text was
     repaired and `updated_at` bumped; the other 275 stayed untouched.

Bug caught along the way: `psycopg.connect()` called with **no argument** does not read
`DATABASE_URL` from the environment — it falls back to a local Unix socket, which doesn't exist
for a Dockerized Postgres (`OperationalError: ... /var/run/postgresql/.s.PGSQL.5432 ... No such
file or directory`). The connection string has to be passed explicitly
(`os.environ.get("DATABASE_URL")`). Also: `with psycopg.connect(...) as conn:` already
commits/rolls back the whole block on exit, so wrapping it in an extra `conn.transaction()` is a
redundant nested transaction — harmless, just an unnecessary layer.

**Remotive + Adzuna additions (2026-08-01):** `remotive_to_rows`/`adzuna_to_rows` mirror
`thread_to_rows`'s shape, but `raw_text` is `json.dumps(job)`, not verbatim prose — first draft used
`str(job)` (Python repr: single quotes, `None`/`True`), which isn't valid JSON and would have broken
Phase 2 parsing. `thread_month` is deliberately repurposed for both non-HN sources too — derived
from each posting's own date, not just an HN thread reference — even though the schema comment
predates that decision and only literally requires non-null for `hn`.

Adzuna needed real pagination: the bare endpoint only returns page 1 (10 results) by default even
when thousands match, so `results_per_page=50` plus a page loop was required. `category="it-jobs"`
was chosen over a fixed keyword to stay in-domain (tech, matching HN/Remotive) while maximizing
volume — 461k+ available vs. ~18k for a single keyword like `"python developer"`, and unlike a
keyword list it doesn't require enumerating role titles.

Bugs caught along the way: an unaliased `fetch_latest_jobs` import let `load.py` silently call
Remotive's client with Adzuna's kwargs (`TypeError`) — fixed by aliasing both imports
(`fetch_remotive_jobs`, `fetch_adzuna_jobs`); `category="it"` isn't a real Adzuna slug (400) — the
real one is `it-jobs`; the page-exhaustion check must test the `results` list's *content*
(`if not results`), not just key presence — Adzuna always returns a `results` key, even when empty.
Also added retry/backoff (3 attempts, exponential 1s/2s/4s) around `ConnectionError`/`Timeout` in
the page loop, after a real proxy blip (`ProxyError`) killed a 50-page run at page 38 — deliberately
does **not** retry `HTTPError`, since a 4xx/5xx already got a response and retrying a bad `category`
value would just waste time before failing anyway.

**Compose note:** `container_name:` was removed. It is a *global* Docker name, so a stopped container
from an earlier run could own the name and block `up`. Compose now scopes the name itself from the
**directory** name — the directory is still `job-market-agent`, so `docker compose config` reports
project `job-market-agent` and the container will come up as **`job-market-agent-db-1`** (not
`jobmarket-db-1`; only the `pyproject.toml` package name is `jobmarket`). The orphaned
pre-WSL `job-market-agent_pgdata` volume is gone; the current WSL Docker install has its own fresh
`pgdata` volume now (created 2026-08-01, a genuine first boot that ran the `init/` scripts).

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
  - [x] DDL `db/schema/001_raw_postings.sql` — written and previously verified: the guarded upsert
        gave `INSERT 0 1` / `0 0` / `0 1`, `(remotive, test-1)` inserted alongside `(hn, test-1)`,
        and all five constraints rejected bad rows (bad source, mid-month `thread_month`, HN without
        a month, blank text, manual `id`). **Re-applied 2026-08-01** in the new WSL Docker volume —
        same clean result.
        *Schema note:* the table has `ingested_at` + `updated_at` but deliberately **no**
        `posted_at` — `thread_month` carries the temporal signal for HN. Revisit if Remotive turns
        out to expose a real per-posting publish date.
  - [x] loader: idempotent upsert on `(source, external_id)` — done and verified against 276 real
        HN postings (insert → no-op re-run → single-row repair on hand-edited text). See the
        `load.py` flow above for the full verification trail.
- [x] Remotive client — semi-structured JSON, contrasts with HN's pure prose. Free API only ever
      exposes ~34 currently-live postings (no historical/paginated data; `total-job-count` caps out
      regardless of filters), so it couldn't carry the volume target alone.
- [x] Adzuna client — pulled forward from Phase 5 for exactly that reason: real pagination + retry,
      see the `load.py` flow section above for the full build/bug log.
- [x] Target: ~700 raw postings loaded — **2,807 loaded** (276 HN + 34 Remotive + 2,497 Adzuna)
- [~] Collect gold-set candidates — stratified across all three sources (~15 HN / 5 Remotive /
      10 Adzuna, not HN-only as originally scoped: Adzuna's structured fields double as free eval
      labels, and its truncated `description` needs gold examples where a null extraction is
      correct). `evals/test.py` (interactive review CLI) built and verified; HN candidates exported
      (`evals/candidates_hn.json`, 40 postings) but not yet reviewed. Adzuna/Remotive exports and
      the actual review session are next.

## Phase 2 — Extraction + evals

*Known ground: LLM extraction, Pydantic, evals.*

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

*Concept (interview material — don't rush):* what an embedding vector is, cosine similarity, what
the dimension count buys you; why semantic search finds "k8s" for the query "kubernetes"; what
pgvector adds to Postgres and how HNSW/IVF differs from a brute-force scan.

**Open decision — which embedding model, and therefore which `vector(n)`.** The README and the
draft `posting_embeddings` DDL both say `BAAI/bge-small-en-v1.5` via sentence-transformers at
**384-dim**. But the WSL environment already has Ollama serving **`bge-m3` at 1024-dim**, and no
sentence-transformers dependency is declared. These are incompatible: the column type is fixed at
index time and the model must match at query time, so switching later means a re-embed and an
`ALTER TABLE`. Decide **before** writing `embed.py`:

- *Ollama + `bge-m3` (1024)* — already installed and reachable, no new Python deps, GPU-backed on the
  Windows host. Adds a cross-boundary network hop and a runtime dependency on Ollama being up.
- *sentence-transformers + `bge-small-en-v1.5` (384)* — in-process, no network, smaller index, matches
  the documented design. Adds a heavy dep (torch) and runs on WSL CPU.

Whichever wins, update the README stack table, the `posting_embeddings` DDL, and the Phase 3 concept
note together so the three stop disagreeing.

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
- [ ] Cross-source dedup (fuzzy company+title), trend charts

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