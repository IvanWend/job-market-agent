# Roadmap

The **service / infrastructure** half of my AI-engineering portfolio, built one phase at a time.

**Maintenance rule.** Current state is rewritten from scratch each session, not appended to.
Decisions go in DECISIONS.md, traps in GOTCHAS.md. Nothing here restates what the code says.

## How it works

INGESTION    HN (Algolia) + Remotive + Web3.career + Habr Career ──►  raw_postings (Postgres)
RETENTION    rolling 90-day window — filtered at ingest, purged on age
EXTRACTION   LLM + Pydantic schema, grounded by verbatim quotes ──►  structured_postings
STORAGE      Postgres + pgvector; local bge-m3 embeddings (1024-dim) ──►  posting_embeddings
AGENT        DeepSeek tool-calling loop: sql_query · vector_search · resume_match
SERVING      FastAPI (SSE streaming) · Langfuse tracing · Docker Compose

## Current state (2026-08-20)

Phase 2, sequenced as a vertical slice (see DECISIONS: pipeline). `pipeline.py` has `pending`,
`build_agent`, `extract` and `persist`; `persist` is verified against the live DB across all three
statuses and the orphan-clearing re-run. **Blocking:** `run` and `main` are unwritten, so nothing has
been extracted at scale yet. `extract`'s LLM path has not survived a real DeepSeek response end to
end — that happens on the pilot.

**Corpus** — 1,098 rows, remote-only, all inside the rolling 90-day window: hn 502, habr 460,
web3 100, remotive 36.

## Phase 1 — Ingestion

- [x] Four board clients: HN (Algolia), Remotive, Web3.career, Habr Career
- [x] 90-day rolling window filter + idempotent upsert on `(source, external_id)` — `load.py`
- [x] `retention.py` + `purge.py`, guarded by `db_meta.role='live'` (see GOTCHAS: psycopg / Docker)
- [x] Frozen eval baseline: `evals/snapshots/2026-08-12_raw.dump` → `jobmarket_eval`, `jobmarket_ro`
- [x] `evals/generate_gold_dataset.py` → `gold_40_candidates.json`, seeded, reruns byte-identical

## Phase 2 — Extraction + evals

- [x] `src/extraction/normalize.py` — pure helpers, model-free
- [x] `src/extraction/source_adapters.py` — `(source, external_id, raw_text)` → `ExtractionInput`
- [x] `src/extraction/schema.py` — four Pydantic models, five grounding validators
- [x] `src/extraction/transform.py` — fill-down + conversion (see DECISIONS: schema)
- [x] `tests/test_normalize.py` — parametrized cases over every public function
- [x] `db/schema/005_structured_postings.sql` (see DECISIONS: storage)
- [x] `src/extraction/prompt.py` — `SYSTEM_PROMPT`, injected so prompt edits stay a clean diff
- [x] `src/extraction/pipeline.py` — `pending`, `build_agent`, `extract`, `persist`
- [ ] `src/extraction/pipeline.py` — `run` (chunked gather, serial writes), `main` (argparse)
- [ ] Pilot `--limit 20 --source hn` to measure cost and wall-clock, then the full corpus pass
- [ ] Tests for `schema.py`, `source_adapters.py`, `transform.py` — need the offline fixtures below
- [ ] Hand-label `evals/gold_labeled.json`, keyed on `(source, external_id)` (see DECISIONS)
- [ ] Eval script: per-field accuracy, `doc_type`, role count, role alignment (see DECISIONS)
- [ ] Langfuse wired into every extraction call
- [ ] Iterate the prompt until acceptable accuracy (set the threshold after the first run)
- [ ] Cache a fixture response per source so the demo path runs offline

## Phase 3 — Storage + retrieval

- [ ] Model - bge-m3` at 1024-dim
- [ ] Embedding pipeline — decide what text gets embedded and document why
- [ ] pgvector search + basic metadata filters (seniority, remote)
- [ ] SQL analytics queries (skill frequency, salary distributions) — hand-written
- [ ] Monthly rollups so trends survive the purge (see DECISIONS: storage)

## Phase 4 — Agent

- [ ] Tools: `sql_query` (whitelisted), `vector_search`, `resume_match`
- [ ] Agent loop with DeepSeek tool-calling
- [ ] Agent eval suite (~15 canned questions) — must run against the snapshot
- [ ] FastAPI endpoint with SSE streaming

## Phase 5 — Polish

- [ ] README with architecture diagram, eval-results table, demo GIF
- [ ] Cross-source dedup (fuzzy company+title), trend charts
- [ ] Hand-roll the validate-and-retry loop to see what `pydantic-ai` hides (see DECISIONS)

## Next

1. `pipeline.py` — `run` → `main`
2. Pilot 20 HN rows; measure cost and wall-clock
3. Full corpus extraction pass — accept bad output, store it
4. `embed.py` + the `posting_embeddings` DDL at `vector(1024)`
5. pgvector `vector_search`
6. DeepSeek tool-calling loop, three tools
7. FastAPI + SSE
8. Then label the gold set and write the eval script
