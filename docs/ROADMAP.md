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

## Build status (updated 2026-08-04)

Phase 1 is **done and committed**. All three ingestion clients (`hn_client.py`, `remotive_client.py`,
`adzuna_client.py`) plus `load.py` (fetch all three → rows → idempotent upsert on
`(source, external_id)`) are working and verified against real data. Toolchain is uv + ruff + mypy,
all clean.

**Durable gotchas worth remembering in later phases:**
- `psycopg.connect()` with no argument silently falls back to a local Unix socket instead of reading
  `DATABASE_URL` — always pass the connection string explicitly.
- Adzuna's bare endpoint only returns page 1 by default even with thousands of matches; needs
  `results_per_page` + a page loop. Its retry/backoff covers `ConnectionError`/`Timeout` but not
  `HTTPError` (429/5xx) — a rate limit still kills the run. Not yet fixed.
- Docker container name is directory-derived (`job-market-agent-db-1`), not the `pyproject.toml`
  package name (`jobmarket`) — don't hardcode the wrong one when scripting against it.

## Phase 1 — Ingestion (no LLM calls) ← DONE

- [x] Docker Compose: Postgres 17 + pgvector (healthcheck, named volume, `init/` entrypoint)
- [x] Algolia HN client
  - [x] `find_latest_hiring_thread()` → newest thread `story_id` + title
  - [x] `find_hiring_threads(since, until)` → all matching threads in a date range, for backfill
        beyond just the latest month. Verified against the live API across multiple ranges,
        including a multi-page pagination boundary.
  - [x] `fetch_thread(story_id)` → `HNThread` with all **top-level** comments. One `/items/` call,
        so no pagination. Comment `id` → `str` (it is the `external_id` dedup key; the API returns
        an int). Text kept as **verbatim HTML** — the table is a replay buffer, and stripping is a
        lossy parse that Phase 2 should do instead. Drops unusable comments via
        `(child.get("text") or "").strip()`, which covers all three shapes: absent key, present-but-
        null (deleted), and whitespace-only. `.get("text", "")` does **not** — a default only fires
        on a missing key, never on a present `null`.
- [x] `raw_postings` schema + loader with dedup
  - [x] DDL `db/schema/001_raw_postings.sql` + `002_posted_at.sql` — guarded upsert on
        `(source, external_id)`, five constraints (bad source, mid-month `thread_month`, HN without
        a month, blank text, manual `id`), all verified.
  - [x] loader: idempotent upsert — verified (insert → no-op re-run → single-row repair on
        hand-edited text).
- [x] Remotive client — semi-structured JSON, contrasts with HN's pure prose. Free API only ever
      exposes ~34 currently-live postings (no historical/paginated data), couldn't carry the volume
      target alone.
- [x] Adzuna client — pulled forward from Phase 5 for exactly that reason: real pagination + retry
      (429/5xx not yet covered — see gotchas above).
- [x] Target: ~700 raw postings loaded — **7,162 loaded** (HN 4,452 / Adzuna 2,676 / Remotive 34).
      Started at 2,807 (89.6% Adzuna / 9.2% HN / 1.1% Remotive), which inverted the project's premise
      (messy prose was a tenth of the corpus). Fixed by backfilling 12 months of HN threads instead
      of just the latest one.
- [x] Collect gold-set candidates — stratified across all three sources, 10 each (HN/Adzuna/
      Remotive). Selected via random sampling per source (`evals/generate_gold_dataset.py`), not
      hand-curated for messiness/edge cases — a known quality tradeoff to keep in mind once Phase 2
      eval accuracy is measured. Sits in `evals/gold_30_candidates.json` (gitignored, regenerable),
      ready for hand-labeling once the schema exists.

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