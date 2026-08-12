# Roadmap

Building the **service / infrastructure** half of my AI-engineering portfolio one phase at a time:
ingestion → LLM extraction + evals → storage/retrieval → agent → serving. Later phases build on
earlier ones. 

## Working style (for AI-assisted sessions)

- **Short, structured answers.** Numbered flow or bullets, not prose walls. Actionable steps first,
  rationale only where a decision hinges on it.
- I write the code; the assistant guides, reviews, and verifies (read + run before assessing).
- Paste errors, not fixes. No silent edits to project files.

## Build status (updated 2026-08-12)

**Phases 1 and 1b are implemented and verified — all four sources are live.** The corpus is
remote-only and rolling:

| source | rows | oldest | newest |
|---|---|---|---|
| habr | 460 | 2026-07-13 | 2026-08-12 |
| hn | 502 | 2026-07-01 | 2026-08-12 |
| remotive | 36 | 2026-07-02 | 2026-08-08 |
| web3 | 100 | 2026-06-05 | 2026-08-10 |

**1,098 rows**, 0 outside the 90-day window, 0 Adzuna. Toolchain (uv + ruff + mypy) clean.

**Ingestion flow —** `load.py` holds a `SOURCES` dict of four independent pipelines. For each:
read the `external_id`s already stored → fetch → filter to the 90-day window → idempotent upsert on
`(source, external_id)` → commit. A source that fails is logged and skipped; the rest still load.
Per-row savepoints keep one bad row from aborting its source's transaction.

**Still to implement:** `jobmarket_eval` restore + read-only role · offline fixtures · all of
Phase 2 onward.

**Durable gotchas worth remembering in later phases:**
- **`raw_text` for Remotive, Web3 and Habr is the entire API JSON**, not prose — `load.py` stores
  `json.dumps(job)`. This is *correct* (same replay-buffer rule as HN's verbatim HTML), but it means
  structured fields sit **inside the model's input**. Feeding `raw_text` straight to the LLM makes
  extraction a copy job and makes quote-grounding trivially satisfiable by quoting JSON. Phase 2
  must split input text from held-out ground truth (see source adapters below).
- **Habr's `raw_text` is the card dict plus a `description_html` key** the loader merges in from the
  detail page, serialized with `ensure_ascii=False` so the Cyrillic stays readable in the column.
  The adapter's job for this source is exactly that split: `description_html` is the model's input,
  everything else on the card (`salary`, `skills`, `qualification`, `employment`) is held-out ground
  truth. 142/459 carry an employer-stated salary; `predictedSalary` is imputed and is **not**.
- **Only Habr uses the `known_ids` argument** every fetcher now receives. Its prose costs one HTTP
  request per posting, so refetching what is already stored would mean ~460 requests and ~15 minutes
  every run. The cost: a stored Habr posting is never re-read, so an edited one keeps its original
  text and the `updated` path is dead for that source. Verified — a warm re-run took 35s.
- **Reading `known_ids` must be wrapped in `conn.transaction()`.** A bare `SELECT` leaves the
  connection `INTRANS`, which holds it idle-in-transaction across minutes of network I/O *and*
  demotes `upsert_posting`'s `conn.transaction()` to a savepoint. Confirmed against
  `pgconn.transaction_status`: wrapped returns to `IDLE`, bare does not.
- **Habr's list pagination is racy.** Offset paging over a live, date-desc feed means a posting
  published mid-run shifts everything down a page, so a card on a page boundary arrives twice — the
  first run returned 459 cards for 458 distinct ids. `fetch_habr_rows` dedupes by id before the
  detail fetch. The mirror case (a card skipped entirely) is not fixable at read time but self-heals
  on the next run, when it shows up as an unknown id.
- **Imputed salaries are not ground truth.** Web3's `estimated_min_salary`/`estimated_max_salary`
  and Habr's `predictedSalary` are the sites' own guesses; only `salary_min_value`/
  `salary_max_value` and `salary.from`/`salary.to` are employer-stated.
- **Held-out ground truth with no evidence in the input is a legitimate null**, not an extraction
  miss — the eval must score it that way whenever a source's structured field outruns its prose.
- `psycopg.connect()` with no argument silently falls back to a local Unix socket instead of reading
  `DATABASE_URL` — always pass the connection string explicitly. **Same trap in the shell:**
  `docker exec ... pg_dump "$DATABASE_URL"` expands `$DATABASE_URL` on the *host*, so if `.env`
  wasn't sourced it passes an empty string and `pg_dump` falls back to the socket as OS user `root`
  (`FATAL: role "root" does not exist`). Either `set -a; . ./.env; set +a` first, or pass explicit
  flags: `docker exec job-market-agent-db-1 pg_dump -U jobmarket -d jobmarket ...`.
- **`conn.transaction()` on an idle psycopg connection issues a real `BEGIN`/`COMMIT`, not a
  savepoint.** It only nests as a savepoint when a transaction is already open. `upsert_posting`
  therefore opens an explicit outer block; without it every row committed individually.
- Docker container name is directory-derived (`job-market-agent-db-1`), not the `pyproject.toml`
  package name (`jobmarket`) — don't hardcode the wrong one when scripting against it.

## Phase 1 — Ingestion (no LLM calls) ← DONE

- [x] Docker Compose: Postgres 17 + pgvector (healthcheck, named volume, `init/` entrypoint)
- [x] Algolia HN client — `find_latest_hiring_thread()` + `fetch_thread(story_id)` → `HNThread` with
      all top-level comments (one `/items/` call, no pagination). Comment `id` → `str` (it is the
      `external_id` dedup key; the API returns an int). Text kept as **verbatim HTML** — the table is
      a replay buffer, and stripping is a lossy parse that Phase 2 should do instead. Drops unusable
      comments via `(child.get("text") or "").strip()`, which covers absent, null (deleted) and
      whitespace-only; `.get("text", "")` does **not** — a default only fires on a missing key.
      `find_hiring_threads(since, until)` was removed with the 90-day pivot: every row it backfilled
      is now outside the window.
- [x] `raw_postings` schema + loader with dedup — DDL `001`–`004`, guarded upsert on
      `(source, external_id)`, verified idempotent (insert → no-op re-run → single-row repair on
      hand-edited text).
- [x] Remotive client — semi-structured JSON. Free API only ever exposes ~34 currently-live postings.
- [x] Adzuna client — **deleted 2026-08-12** with the pivot.
- [x] Collect gold-set candidates — 10 each from HN/Adzuna/Remotive via
      `evals/generate_gold_dataset.py`, random per source rather than hand-curated for messiness.
      **Superseded:** the set is resampled from the four-source snapshot. The old rows survive with
      full `raw_text` in `evals/gold_30_candidates.json` (gitignored) if any are worth keeping.

## Phase 1b — Remote-source pivot + 90-day window ← DONE (except Habr)

Sources the project actually targets, all probed live:

| Source | Status | Notes |
|---|---|---|
| **HN** | live | The only pure-prose source. One thread per run; 90 days holds ~3 threads and the upsert makes repeat runs free. |
| **Remotive** | live | Semi-structured JSON, ~17–34 live postings, no history. |
| **Web3.career** | live | Token-gated. Payload is a 3-element array `[docs, tos, jobs]` served as `text/html`. Hard cap 100 jobs/call — `page` and `offset` are **ignored**, so more volume comes from repeating per `tag`, not paging. Without a valid token it **302s to the sales page** instead of erroring, hence `allow_redirects=False`. Dates are RFC 2822; use `date_epoch`. ToS requires linking back via `apply_url` and crediting web3.career. |
| **Habr Career** | live | Needs no key. `GET career.habr.com/api/frontend/vacancies?type=all&remote=true&per_page=50&page=N` → `{list, meta:{totalResults, perPage, currentPage, totalPages}}`. **`per_page=50` is the real cap** — a larger value is echoed back in `meta.perPage` but still returns 50 rows, so page off `totalPages`, never `perPage`. **List endpoint has no description text** — cards only; the prose comes from an HTML parse of `/vacancies/{id}`, selector `div.vacancy-description__text` (the JSON detail endpoint serves the SPA shell). Archived postings 404 → `None`, not an error. ~460 live remote postings spanning ~30 days, so nothing to backfill. Postings are Russian — affects the `stack` alias map, seniority enums, and gold labeling. |
| **CryptoJobsList** | parked | No usable public feed: `/rss` returns valid RSS with zero `<item>`s, the API is Cloudflare-guarded. |

**Keeping extraction non-trivial is the standing risk of this pivot.** Three of four sources hand
over clean JSON. The defense is now in place on two of three counts: HN keeps rolling, and Habr's
HTML body **is** stored (`description_html`, avg 2,786 chars of real prose). The third — holding
structured fields out as ground truth — is Phase 2's source adapters.

### Retention — implemented

- **90 days, enforced in two places:** `purge.py` deletes what aged out, `load.py` drops aged-out
  rows before insert. Age-purge alone means every run re-inserts the same expired postings the
  boards still serve, which the next purge deletes again. `WINDOW_DAYS` lives in `retention.py` so
  the two cannot disagree.
- **`db_meta` guard.** One row, `'live'` or `'eval'`. `purge.py` refuses unless `role = 'live'`, and
  refuses outright if the table or row is missing. Verified: flipping the row to `'eval'` makes
  `--apply` abort before deleting anything.
- `purge.py` is **dry-run by default**; `--apply` deletes.
- `posted_at` is `NOT NULL` — `WHERE posted_at < now() - interval '90 days'` silently skips NULLs
  and those rows would live forever.
- **Time-series analytics lose their substrate.** A rolling window can't answer "how did Rust demand
  change over the year". Fix when Phase 3/5 need it: monthly rollups (skill frequency, salary
  percentiles) to an aggregate table the purge doesn't touch. Aggregates aren't postings.

### Frozen eval DB

The live DB rolls; evals run against a frozen snapshot — `evals/snapshots/YYYY-MM-DD_raw.dump`,
a versioned dump file rather than a second live database, which would drift the first time something
pointed `load.py` at it.

- **No snapshot exists.** The pre-pivot dump was deleted — it predated web3 and habr, so it could
  only ever label two of the four live sources. The replacement is taken from the current corpus
  (all four sources, 1,098 rows) and the gold set is resampled per source from it.
- Restore into a separate database `jobmarket_eval` in the same container, then
  `UPDATE db_meta SET role = 'eval'`. `EVAL_DATABASE_URL` in `.env` + `.env.example`. No second
  service, no second port. **Not done yet**, along with its `SELECT`-only role — that role, not
  discipline about which URL is which, is what actually enforces frozen.
- **Inputs in the dump, labels in git.** Labels get revised as the schema firms up and those
  revisions must be reviewable diffs, which they aren't inside a binary dump. Key labels on
  `(source, external_id)`, not `raw_postings.id`, so they survive a re-snapshot. `.gitignore`
  excludes `evals/gold_30_candidates.json` — `gold_labeled.json` must not get caught by that.
- **Re-snapshot deliberately, never in place:** new date-stamped filename, re-run labeling.
- **Don't put embeddings in the dump** once Phase 3 lands — float noise that won't compress.
  Snapshot the tables, regenerate embeddings on restore: that makes the eval DB a test of the
  embedding pipeline instead of a fossil of it.
- **Agent evals must run against the snapshot.** Phase 4's canned questions asserted against SQL
  ground truth would otherwise fail every week for reasons unrelated to the agent.

### Remaining tasks

- [x] Habr client — `habr_client.py` (paginated cards + per-posting HTML description), wired into
      `SOURCES`. 460 rows loaded, 0 missing descriptions, avg 2,786 chars.
- [ ] Snapshot the current four-source corpus, then resample the gold set per source from it.
- [ ] Restore `jobmarket_eval` from that snapshot, create the read-only role, set `role = 'eval'`.
- [ ] Cache a fixture response per source. Two of four sources are undocumented or Cloudflare-
      guarded; the demo path must run offline or it will break on presentation day.

**Framing:** with web3.career + Habr the corpus skews crypto and RU-market. "Job-market intelligence"
overclaims — call it a remote job search agent over heterogeneous boards, and the niche sourcing
reads as a scope decision instead of a sampling flaw.

## Phase 2 — Extraction + evals

*Known ground: LLM extraction, Pydantic, evals.*

*Concept:* the Pydantic schema is the single contract for extraction and evals; every non-null field
carries a **verbatim source quote**, and evals check quote-in-text containment — not just values — to
catch fabrication.

- [ ] **Source adapters** (`src/extraction/source_adapters.py`) — `(source, raw_text)` →
      `ExtractionInput(text, ground_truth)`. Lives in the extraction pipeline, **not** the loader:
      keeps `raw_postings` a lossless replay buffer, needs no re-ingest, and stays a pure function
      that's testable off a fixture while the parse rules churn. This module is the **only** place
      that knows source-specific JSON shape — if the eval script re-parses `raw_text` on its own,
      the two drift and the scores stop meaning anything.
- [ ] Finalize the Pydantic schema (decisions locked below; five known defects to fix)
- [ ] Extraction pipeline: JSON mode + retry on validation failure
- [ ] Hand-label `evals/gold_labeled.json` — against the **frozen snapshot** (Phase 1b), keyed on
      `(source, external_id)`, committed to git. Never label against the live rolling DB. Sample
      across all four sources so every adapter has coverage.
- [ ] Eval script: per-field accuracy (exact match for enums/numbers, set-F1 for `stack[]`,
      containment for `source_quotes`) + role-count accuracy + role alignment
- [ ] Langfuse wired into every extraction call
- [ ] Iterate the prompt until acceptable accuracy (set the threshold after the first run)

**Schema decisions (locked 2026-08-05):**
- **One list, `stack`.** `skills` is dropped. Synonyms normalized in Python via an alias map
  (`postgresql|psql → postgres`, `k8s → kubernetes`), not in the prompt — otherwise set-F1 punishes
  the model for spelling. Needs a stoplist too: the spike emitted `"Open Source"` as a technology.
- **Salary stored monthly.** The LLM extracts **verbatim** (`amount`, `period`, `currency`); Python
  converts: `year ÷ 12`, `hour × 173.33` (2080/12 — pin the constant). Currencies are **not**
  converted; `currency` is stored alongside. `source_quotes["salary"]` must hold the verbatim
  `"$150k/year"` — never the derived monthly figure, which is unquotable by construction and would
  fail every containment check.
- **Multi-role postings split into one record per role.** Not an edge case: of the 10 HN gold rows,
  **4 are clearly multi-role** (Aurora 2, Playboy 4, Faithlife 2, Sourcegraph **9**), 2 are
  ambiguous, 4 are single. Consequences:
  - Two Pydantic models, deliberately separate: `RoleExtraction` (verbatim, what the LLM emitted)
    → `normalize()` → the stored shape. Keeps *model misread the posting* and *my `÷12` has a bug*
    separately measurable.
  - `company` is posting-level. `title`/`seniority` are role-level. `stack`/`location`/
    `remote_policy`/`employment_type` need **inherit-with-override** — Playboy states one stack for
    four roles; Faithlife gives each role its own location and type. Fill down in `normalize()`
    (testable), not in the prompt.
  - **Don't split on location.** Adfinis is *one* system-engineer role hiring in Sydney and
    Brisbane. Without an explicit prompt rule this yields two spurious roles.
  - `structured_postings` becomes **1:N** with `raw_postings`. Needs `role_index` + a unique
    `(raw_posting_id, role_index)`, or re-extraction duplicates rows instead of updating them.
    Phase 3 embeddings key on the **role** row, not the raw posting.
  - Eval can't compare positionally. Score role *count* first, then greedy-match predicted↔gold on
    normalized title, then per-field score only matched pairs; report unmatched as precision/recall
    loss.

**Five defects from the `experiments/` spike — fix these first:**
1. Spike passed `output_type=RoleExtraction`, so `PostingExtraction` went unused and the role split
   was never exercised. Adfinis (1 role, 2 cities) was the wrong posting to prove it on — run
   Playboy `38107028`, Faithlife `34614439`, Sourcegraph `36153615`.
2. `salary_currency='null'` — the **string**, which validates clean against `str | None` and lands
   in the DB as data. Needs a validator coercing `"null"|"none"|"N/A"|""` → `None` on every
   optional string field.
3. `salary_period='year'` with both amounts `None`, on a posting that states no salary at all.
   Needs a model-level validator: both amounts `None` ⇒ period and currency `None`.
4. `source_quotes` keys were invented (`services`, `team_and_culture`, `work_policy`) — none are
   field names, so no containment check can run. Validate keys against `model_fields`.
5. `title='System Engineer - Linux Cloud'` was reconstructed from a **truncated URL** and appears
   nowhere in the visible text, with no quote backing it. Argues for requiring a quote per non-null
   field.

**Open, not yet decided:**
- Header-vs-body conflicts. Adfinis's header says `Onsite`, its body says 3 days/week in office
  (the spike chose hybrid — the better read). This recurs across HN; pick a tiebreak rule and put
  it in *both* the prompt and the labeling notes, or gold and model will disagree for reasons that
  aren't extraction quality.
- Whether to keep `pydantic-ai`. It handles validate-and-retry natively — write the manual loop
  once first (~20 lines: call → `model_validate_json()` → catch `ValidationError` → feed the error
  text back → retry), then adopt the framework knowing what it hides.
- The gold set's role-split signal rests **entirely on the HN rows** — Remotive, Web3 and Habr are
  1-posting-1-role by construction, so their role-count ground truth is trivially `1`. Weight the
  resampled set toward HN, and hand-pick a few multi-role postings rather than sampling at random.

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