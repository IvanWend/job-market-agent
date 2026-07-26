# Roadmap

Building the **service / infrastructure** half of my AI-engineering portfolio one phase at a time:
ingestion → LLM extraction + evals → storage/retrieval → agent → serving. Later phases build on
earlier ones. The pure retrieval + agent lab lives in **product-search**; see
[out of scope](#deliberately-out-of-scope-lives-in-product-search).

## Build status (updated 2026-07-26)

**Working now:** `docker-compose.yml` (Postgres 17 + pgvector, healthcheck, `pgdata` volume,
`init/` mounted). `src/ingestion/hn_client.py::find_latest_hiring_thread()` resolves the newest HN
"Who is Hiring" thread's `story_id` + title via the Algolia `search_by_date` endpoint. Toolchain is
uv + ruff + mypy; repo is on git (`main`).

**Decision (2026-07-26) — two schema mechanisms, one job each.** Compose mounts `./init` at
`/docker-entrypoint-initdb.d`, whose scripts run **only when the data directory is empty** — first
boot, then silently never again. That makes it *bootstrap*, not migration. So `db/schema/` stays the
re-runnable path applied by hand (the skill worth having), and `init/` is reserved for at most
`CREATE EXTENSION IF NOT EXISTS vector;`. `001_raw_postings.sql` must not live in both.

**Designed, not yet on disk:** `db/schema/001_raw_postings.sql` — DDL with `CHECK`, composite
`UNIQUE`, and the guarded upsert. Needs to be written, applied from a clean `down -v`, and its three
conflict behaviors verified.

**Next step:** write + verify the DDL, then fetch top-level comments and write the idempotent loader.

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
- [ ] **Open, found by mypy:** `hn_client.py:11` — the `params` dict infers as `dict[str, object]`
      (mixed `str` + `int` values), which `requests.get` rejects. Needs a type annotation, not a
      value change. Then consider flipping `disallow_untyped_defs = true`.
- [ ] Optional: `ruff format` would reformat `hn_client.py` (blank line + collapse the
      `RuntimeError` call). Not applied — decide whether to adopt the formatter.

**Git — ongoing across every phase:**
- [ ] Every feature: branch → PR → self-review → merge (no direct commits to `main`)
- [ ] Commit early and often (lesson: mid-session revert on cv-tailor-ru)

## Phase 1 — Ingestion (no LLM calls) ← IN PROGRESS

- [x] Docker Compose: Postgres 17 + pgvector (healthcheck, named volume, `init/` entrypoint)
- [~] Algolia HN client
  - [x] `find_latest_hiring_thread()` → newest thread `story_id` + title
  - [ ] fetch all **top-level** comments for that `story_id` (paginate; HTML text; drop deleted/empty)
- [ ] Remotive client
- [~] `raw_postings` schema + loader with dedup
  - [~] DDL `db/schema/001_raw_postings.sql` — designed (CHECK + composite unique + guarded upsert);
        pending clean-apply + dedup verification
  - [ ] loader: idempotent upsert on `(source, external_id)`
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