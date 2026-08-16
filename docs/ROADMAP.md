# Roadmap

The **service / infrastructure** half of my AI-engineering portfolio, built one phase at a time.

## Data flow

```
                     ┌──────────────────────────────────────────────── PHASE 1 — DONE
  HN (Algolia)       │
  Remotive           │  fetch ──► 90-day window filter ──► idempotent upsert (source, external_id)
  Web3.career        │             ▲                        │
  Habr Career        │             └── retention.py ────────┤
                     └──────────────────────────────────────┼─────────────────────────────────────
                                                            ▼
                                            ┌───────────────────────────────┐
                                            │ raw_postings                  │  lossless replay
                                            │ raw_text = verbatim HTML (hn) │  buffer — never
                                            │           | API JSON (others) │  filtered at ingest
                                            └───────────────┬───────────────┘
                          purge.py (db_meta.role='live')    │
                          pg_dump ──► evals/snapshots/*.dump ──► jobmarket_eval (role='eval', RO)
                                                            │
  ┌───────────────────────────────── PHASE 2 ───────────────┼──────────────────────────────────┐
  │                                                         ▼                                  │
  │  source_adapters.py: (source, raw_text) ──► ExtractionInput(text, ground_truth)             │
  │       hn    → whole comment is text;  no ground truth                                       │
  │       habr  → description_html is text; card fields held out                                │
  │       web3  → description is text;     salary/tags held out                                 │
  │       remotive → description is text;  salary/type/location held out                        │
  │                          │                              │                                   │
  │                          ▼ text                         ▼ ground_truth                      │
  │            LLM + JSON mode ──► PostingExtraction ──►┐   │                                   │
  │            (verbatim: amounts, periods, quotes)     │   │                                   │
  │                          │ ValidationError → retry  │   │                                   │
  │                          ▼                          ▼   ▼                                   │
  │                   normalize()  ────────────────►  eval script  ◄──── evals/gold_labeled.json │
  │                   (÷12, alias map, fill-down)      per-field + role-count + quote            │
  │                          │                          containment                             │
  └──────────────────────────┼─────────────────────────────────────────────────────────────────┘
                             ▼
                 structured_postings (1:N with raw_postings, keyed role_index)
                             │
                             ▼ PHASE 3
                 posting_embeddings ──► pgvector search + SQL analytics
                             │
                             ▼ PHASE 4
                 agent loop (sql_query · vector_search · resume_match) ──► FastAPI + SSE
```

Every LLM call is traced to Langfuse from the first one.

## Current state (2026-08-13)

**Corpus** — 1,098 rows, remote-only, all inside the rolling 90-day window:

| source | rows | oldest | newest |
|---|---|---|---|
| habr | 460 | 2026-07-13 | 2026-08-12 |
| hn | 502 | 2026-07-01 | 2026-08-12 |
| remotive | 36 | 2026-07-02 | 2026-08-08 |
| web3 | 100 | 2026-06-05 | 2026-08-10 |

**Eval baseline — frozen and verified.** `evals/snapshots/2026-08-12_raw.dump` (PG custom format,
1.07 MB, all 1,098 rows) is restored into `jobmarket_eval` in the same container, with
`db_meta.role = 'eval'`. `EVAL_DATABASE_URL` connects as `jobmarket_ro`, which `SELECT`s but is
denied `INSERT`/`DELETE`; default privileges cover future tables. That role, not discipline about
which URL is which, is what enforces frozen.

**Gold-set candidates — sampled.** `evals/generate_gold_dataset.py` writes
`evals/gold_40_candidates.json`: 40 rows (hn 16, habr 10, web3 8, remotive 6), seed `20260813`
written into the output, `role='eval'` guard mirroring `purge.py`'s `'live'` guard. HN is deduped
by company prefix (145 of 502 rows are reposts across the July and August threads) and carries 6
hand-picked multi-role postings as a module constant. Reruns are byte-identical.

Toolchain (uv + ruff + mypy) clean.

**Still to build:** offline fixtures · all of Phase 2 onward.

## Durable gotchas

Carried forward because they bite in *later* phases, not because they were hard once.

- **`raw_text` for Remotive, Web3 and Habr is the entire API JSON**, not prose. Correct for a replay
  buffer, but it means structured fields sit **inside** the model's input — feeding `raw_text`
  straight to the LLM makes extraction a copy job and makes quote-grounding trivially satisfiable by
  quoting JSON. Splitting input from held-out truth is exactly the adapters' job.
- **Habr's `raw_text` is the card dict plus a `description_html` key**, serialized with
  `ensure_ascii=False`. `description_html` is the input; `salary`, `skills`, `qualification`,
  `employment` are held-out truth. 142/459 carry an employer-stated salary.
- **Imputed salaries are not ground truth.** Web3's `estimated_*` and Habr's `predictedSalary` are
  the sites' own guesses; only `salary_min_value`/`salary_max_value` and `salary.from`/`salary.to`
  are employer-stated.
- **Held-out truth with no evidence in the input is a legitimate null**, not an extraction miss —
  the eval must score it that way whenever a source's structured field outruns its prose.
- **Not every HN row is a job posting.** See the Phase 2 decision below.
- **`psycopg.connect()` with no argument silently falls back to a local Unix socket** instead of
  reading `DATABASE_URL` — always pass the string explicitly. Same trap in the shell:
  `docker exec ... pg_dump "$DATABASE_URL"` expands on the *host*, so an unsourced `.env` passes an
  empty string and `pg_dump` falls back to the socket as OS user `root`
  (`FATAL: role "root" does not exist`). Either `set -a; . ./.env; set +a` first, or pass
  `-U jobmarket -d jobmarket` explicitly.
- **`conn.transaction()` on an idle psycopg connection issues a real `BEGIN`/`COMMIT`, not a
  savepoint.** It only nests as a savepoint when a transaction is already open, so a bare `SELECT`
  beforehand silently demotes the next block.
- Docker container name is directory-derived (`job-market-agent-db-1`), not the `pyproject.toml`
  package name — don't hardcode the wrong one when scripting against it.
- **Re-snapshot deliberately, never in place:** new date-stamped filename, re-run labeling. Labels
  key on `(source, external_id)`, not `raw_postings.id`, so they survive a re-snapshot.
- **Inputs live in the dump, labels live in git.** Labels get revised as the schema firms up and
  those revisions must be reviewable diffs, which they are not inside a binary dump.

## Phase 2 — Extraction + evals

**← the current phase.**

*Concept:* the Pydantic schema is the single contract for extraction *and* evals; every non-null
field carries a **verbatim source quote**, and evals check quote-in-text containment — not just
values — to catch fabrication.

- [x] **`src/extraction/normalize.py`** — pure helpers shared by the adapter and the model path.
      Verified over all 40 gold rows. `remote_policy_enum()` still in progress.
- [ ] **Source adapters** (`src/extraction/source_adapters.py`) — `(source, raw_text)` →
      `ExtractionInput(text, ground_truth)`. Lives in the extraction pipeline, **not** the loader:
      keeps `raw_postings` lossless, needs no re-ingest, stays a pure function testable off a
      fixture. The **only** place that knows source-specific JSON shape — if the eval script
      re-parses `raw_text` on its own, the two drift and the scores stop meaning anything.
- [ ] Finalize the Pydantic schema (`src/extraction/schema.py`; layout below, five defects to fix)
- [ ] Extraction pipeline: JSON mode + retry on validation failure
- [ ] Hand-label `evals/gold_labeled.json` from `gold_40_candidates.json`, keyed on
      `(source, external_id)`, committed to git
- [ ] Eval script: per-field accuracy (exact match for enums/numbers, set-F1 for `stack[]`,
      containment for `source_quotes`) + `doc_type` accuracy + role-count accuracy + role alignment
- [ ] Langfuse wired into every extraction call
- [ ] Iterate the prompt until acceptable accuracy (set the threshold after the first run)
- [ ] Cache a fixture response per source so the demo path runs offline — two of four sources are
      undocumented or Cloudflare-guarded, and the demo must not break on presentation day

### Schema decisions (locked)

- **One list, `stack`.** `skills` is dropped. Synonyms normalized in Python via an alias map
  (`postgresql|psql → postgres`, `k8s → kubernetes`), not in the prompt — otherwise set-F1 punishes
  the model for spelling. Needs a stoplist too: the spike emitted `"Open Source"` as a technology.
- **Salary stored monthly.** The LLM extracts **verbatim** (`amount`, `period`, `currency`); Python
  converts: `year ÷ 12`, `hour × 173.33` (2080/12 — pin the constant). Currencies are **not**
  converted. `source_quotes["salary"]` must hold the verbatim `"$150k/year"`, never the derived
  monthly figure, which is unquotable by construction and would fail every containment check.
- **Multi-role postings split into one record per role.** Of the 10 original HN gold rows, 4 were
  clearly multi-role, 2 ambiguous, 4 single. Consequences:
  - Two Pydantic models, deliberately separate: `RoleExtraction` (verbatim, what the LLM emitted)
    → `normalize()` → the stored shape. Keeps *model misread the posting* and *my `÷12` has a bug*
    separately measurable.
  - `company` is posting-level. `title`/`seniority` are role-level. `stack`/`location`/
    `remote_policy`/`employment_type` need **inherit-with-override** — one posting states a single
    stack for four roles while another gives each role its own location and type. Fill down in
    `normalize()` (testable), not in the prompt.
  - **Don't split on location.** One system-engineer role hiring in Sydney *and* Brisbane is one
    role. Without an explicit prompt rule this yields two spurious roles.
  - `structured_postings` is **1:N** with `raw_postings`. Needs `role_index` + a unique
    `(raw_posting_id, role_index)`, or re-extraction duplicates rows instead of updating them.
    Phase 3 embeddings key on the **role** row, not the raw posting.
  - Eval can't compare positionally. Score role *count* first, then greedy-match predicted↔gold on
    normalized title, then per-field score only matched pairs; report unmatched as precision/recall
    loss.

### Not every HN row is a job posting — locked 2026-08-13

HN's "one top-level comment = one job posting" is a **social convention, not an enforced rule**.
`fetch_thread` keeps every top-level child with non-empty text, which is correct for a replay
buffer. Verified against Algolia: the off-topic rows are genuine top-level comments on the correct
`Ask HN: Who is hiring?` threads — no client bug, nothing to fix at ingest.

At least 16 of 502 HN rows are not postings: 11 discussion/self-promo/spam/`[flagged]`, and 5
**"Who wants to be hired" résumés** posted in the wrong thread. That count is a **floor** — it came
from reviewing the rows with no `|` header plus everything under 450 chars, not all 502.

**Decision: classify in the extraction layer, never filter at ingest.**

1. A hard prefilter in the HN adapter for the unambiguous cases only — `[flagged]`, `[dead]`, text
   under ~120 chars. No judgment required, no false positives.
2. **`doc_type: Literal["posting", "candidate", "other"]` on the extraction schema.** An enum, not a
   bool: `candidate` is a coherent, recognizable class, not noise. When `doc_type != "posting"`,
   roles is empty and every other field is `None`. Retrieval filters on `doc_type = 'posting'`;
   storing the decision means re-extraction doesn't re-litigate it.

Why classification beats a regex: **a regex's mistakes are invisible.** The obvious rule — header
must contain `|` — drops ~35 *legitimate* free-form postings (Tether, PrairieLearn, Proton), which
are the hardest and most valuable extraction targets. `doc_type` is instead a scored field, so
errors surface. It also handles rows no heuristic can: one opens `"Can you change this to the
following:"` and then contains a complete posting.

**Open:** the gold set contains **zero** non-postings, so it cannot score `doc_type` at all. Add 2–3
known junk ids as a deliberate hand-picked group, or accept the field is unmeasured.
`EXCLUDED_HN` in the sampler stays regardless — spending gold-set budget on junk isn't worth it
even once the extractor can handle it.

### Habr labeling language — locked

Normalize the enums, not the whole record.

| field | rule | why |
|---|---|---|
| `seniority` | normalize → English enum | Genuinely mixed: 195 rows senior/синьор, 160 middle/миддл, 82 lead/ведущий/тимлид, 38 junior/стажёр. The RU alias map earns its keep here. |
| `stack` | already Latin — no translation layer | 190 rows carry Latin `Python`/`Docker`/`Kubernetes` vs **1** Cyrillic; PostgreSQL is 128 Latin vs 0 Cyrillic. Habr writes prose in Russian, tech names in Latin. |
| `title` | keep **verbatim Russian** | Free text, not an enum. Translating adds an unmeasurable noise source and is unquotable. Habr is 1-role, so greedy-match never needs it cross-lingual. |
| `source_quotes` | keep **verbatim Russian**, always | Containment runs against `raw_text`. Translate a quote and every Habr row fails for a reason unrelated to extraction quality. |

Same shape as the salary rule — verbatim quote, derived value. Write it into the prompt and the
labeling notes in those terms, so it reads as one principle rather than two exceptions.

**Homoglyph trap:** `1С` appears with a **Cyrillic С in 33 rows and a Latin C in 48**. Without
folding, the alias map scores two different technologies. Cheapest fix is a `str.translate` of the
Cyrillic→Latin homoglyphs (`СсАаЕеОоРрХх`) before alias lookup.

### Five defects from the `experiments/` spike — fix these first

1. Spike passed `output_type=RoleExtraction`, so `PostingExtraction` went unused and the role split
   was never exercised. The postings originally named as replacements are 2023–24 HN ids, far
   outside the 90-day window and in neither the snapshot nor any surviving file. Exercise it against
   the 6 hand-picked multi-role ids now in `HAND_PICKED_HN`.
2. `salary_currency='null'` — the **string**, which validates clean against `str | None` and lands
   in the DB as data. Needs a validator coercing `"null"|"none"|"N/A"|""` → `None` on every optional
   string field.
3. `salary_period='year'` with both amounts `None`, on a posting stating no salary at all. Needs a
   model-level validator: both amounts `None` ⇒ period and currency `None`.
4. `source_quotes` keys were invented (`services`, `team_and_culture`, `work_policy`) — none are
   field names, so no containment check can run. Validate keys against `model_fields`.
5. `title='System Engineer - Linux Cloud'` was reconstructed from a **truncated URL** and appears
   nowhere in the visible text, with no quote backing it. Argues for requiring a quote per non-null
   field.

### Still open

- **Header-vs-body conflicts.** One spike posting's header said `Onsite` while its body said 3
  days/week in office (the spike chose hybrid — the better read). This recurs across HN; pick a
  tiebreak rule and put it in *both* the prompt and the labeling notes, or gold and model will
  disagree for reasons that aren't extraction quality.
- **Compound seniority.** `"Mid-Senior/Senior"` (HN `48749201`) matches no alias key and falls to
  `unknown`. Add compound keys, or rule that a range rounds up.
- **Whether to keep `pydantic-ai`.** It handles validate-and-retry natively — write the manual loop
  once first (~20 lines: call → `model_validate_json()` → catch `ValidationError` → feed the error
  back → retry), then adopt the framework knowing what it hides.

## Phase 3 — Storage + retrieval

*Concept (interview material — don't rush):* what an embedding vector is, cosine similarity, what
the dimension count buys you; why semantic search finds "k8s" for the query "kubernetes"; what
pgvector adds to Postgres and how HNSW/IVF differs from a brute-force scan.

**Open decision — which embedding model, and therefore which `vector(n)`.** The README and the draft
`posting_embeddings` DDL say `BAAI/bge-small-en-v1.5` at **384-dim**, but the WSL environment already
runs Ollama serving **`bge-m3` at 1024-dim**, and no sentence-transformers dependency is declared.
These are incompatible: the column type is fixed at index time and the model must match at query
time, so switching later means a re-embed and an `ALTER TABLE`. Decide **before** writing `embed.py`:

- *Ollama + `bge-m3` (1024)* — already installed and reachable, no new Python deps, GPU-backed on the
  Windows host. Adds a cross-boundary network hop and a runtime dependency on Ollama being up.
- *sentence-transformers + `bge-small-en-v1.5` (384)* — in-process, no network, smaller index,
  matches the documented design. Adds a heavy dep (torch) and runs on WSL CPU.

Whichever wins, update the README stack table, the `posting_embeddings` DDL, and this note together
so the three stop disagreeing.

- [ ] Embedding pipeline — decide what text gets embedded (raw vs. structured summary; likely the
      structured summary) and document why
- [ ] pgvector search + basic metadata filters (seniority, remote)
- [ ] SQL analytics queries (skill frequency, salary distributions) — hand-written

**Don't put embeddings in the snapshot.** Float noise that won't compress. Snapshot the tables and
regenerate embeddings on restore: that makes the eval DB a test of the embedding pipeline instead of
a fossil of it.

**Time-series analytics have no substrate.** A rolling 90-day window can't answer "how did Rust
demand change over the year". Fix when Phase 3/5 need it: monthly rollups (skill frequency, salary
percentiles) into an aggregate table the purge doesn't touch. Aggregates aren't postings.

## Phase 4 — Agent

*Concept:* a hand-rolled DeepSeek tool-calling loop; `sql_query` uses **whitelisted templates, not
raw SQL**. Then endpoints, dependency injection, SSE streaming — trace one request end-to-end
(HTTP in → agent loop → tool calls → streamed response).

- [ ] Tools: `sql_query` (whitelisted), `vector_search`, `resume_match`
- [ ] Agent loop with DeepSeek tool-calling
- [ ] Agent eval suite (~15 canned questions with expected-answer assertions vs. SQL ground truth) —
      **must run against the snapshot**, or canned questions asserted against SQL ground truth fail
      every week for reasons unrelated to the agent
- [ ] FastAPI endpoint with SSE streaming

## Phase 5 — Polish

- [ ] README with architecture diagram, eval-results table, demo GIF
- [ ] Cross-source dedup (fuzzy company+title), trend charts

## Working style (for AI-assisted sessions)

- **Short, structured answers.** Numbered flow or bullets, not prose walls. Actionable steps first,
  rationale only where a decision hinges on it.
- I write the code; the assistant guides, reviews, and verifies (read + run before assessing).
- Paste errors, not fixes. No silent edits to project files.

| Written by hand (learning targets) | Delegated to Claude Code (plumbing) |
|---|---|
| Extraction prompt + Pydantic schema | Docker Compose, scaffolding, config |
| Eval scripts + gold-set labeling | API clients, pagination |
| Agent loop + tool definitions | FastAPI boilerplate, DB migrations |
| SQL analytics queries | Test scaffolding, refactors |
| Embedding + vector-search logic (v1) | |

**Explain-back test:** every generated file must pass *"could I walk an interviewer through this
file — why each part exists?"* before its phase is marked done. If not, ask for an explanation;
don't move on.
