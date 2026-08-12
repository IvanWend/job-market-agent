# Roadmap

Building the **service / infrastructure** half of my AI-engineering portfolio one phase at a time:
ingestion → LLM extraction + evals → storage/retrieval → agent → serving. Later phases build on
earlier ones. 

## Working style (for AI-assisted sessions)

- **Short, structured answers.** Numbered flow or bullets, not prose walls. Actionable steps first,
  rationale only where a decision hinges on it.
- I write the code; the assistant guides, reviews, and verifies (read + run before assessing).
- Paste errors, not fixes. No silent edits to project files.

## Build status (updated 2026-08-11)

Phase 1 is **done and committed**. All three ingestion clients (`hn_client.py`, `remotive_client.py`,
`adzuna_client.py`) plus `load.py` (fetch all three → rows → idempotent upsert on
`(source, external_id)`) are working and verified against real data. Toolchain is uv + ruff + mypy,
all clean.

**The working tree is currently broken and uncommitted** — `hn_client.py` has had
`find_hiring_threads()` deleted while `load.py:12` still imports it, so `import src.ingestion.load`
raises `ImportError`. `ruff check src/` reports 8 errors. `web3_client.py` is new and untracked.
`pyproject.toml` gained `jupyterlab` + `pydantic-ai`. Fix the import before anything else runs.

Phase 1b (below) **repoints the project at remote-only sources with a 90-day freshness window**.
Decided 2026-08-11, not yet implemented.

Phase 2 is **designed, not yet implemented**. Schema decisions are locked (see below), the first
`pydantic-ai` spike ran end-to-end against a real HN posting in `experiments/`, and the five defects
it exposed are logged as the first implementation tasks.

**Durable gotchas worth remembering in later phases:**
- **`raw_text` for Adzuna and Remotive is the entire API JSON**, not prose — `load.py` stores
  `json.dumps(job)`. This is *correct* (same replay-buffer rule as HN's verbatim HTML), but it means
  the structured fields — Adzuna's `salary_min/max`, `title`, `company`, `contract_time`; Remotive's
  `tags`, `job_type`, `category` — sit **inside the model's input**. Feeding `raw_text` straight to
  the LLM makes extraction a copy job and makes quote-grounding trivially satisfiable by quoting
  JSON. Phase 2 must split input text from held-out ground truth (see source adapters below).
- **Adzuna salaries are mostly imputed.** 9 of 10 gold rows carry `"salary_is_predicted": "1"` —
  Adzuna's own ML guess, not employer-stated. Tell: `salary_min == salary_max` exactly. Only rows
  with `"0"` are usable as salary ground truth.
- Adzuna's `description` is **truncated** (~1.5KB, ends in `…`), so its held-out ground truth
  often has no supporting evidence in the input text. Those are legitimate nulls, not extraction
  misses — the eval must score them that way.
- `psycopg.connect()` with no argument silently falls back to a local Unix socket instead of reading
  `DATABASE_URL` — always pass the connection string explicitly. **Same trap in the shell:**
  `docker exec ... pg_dump "$DATABASE_URL"` expands `$DATABASE_URL` on the *host*, so if `.env`
  wasn't sourced it passes an empty string and `pg_dump` falls back to the socket as OS user `root`
  (`FATAL: role "root" does not exist`). Either `set -a; . ./.env; set +a` first, or pass explicit
  flags: `docker exec job-market-agent-db-1 pg_dump -U jobmarket -d jobmarket ...` (local socket
  connections in that container are not password-gated).
- `.env` has `WEB3_API_KEY =` with a space before `=`. Bash reads that line as a command, so
  sourcing `.env` prints `WEB3_API_KEY: command not found`, and python-dotenv doesn't give the key
  name you expect either. Fix the line.
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
      eval accuracy is measured. Sits in `evals/gold_30_candidates.json` (gitignored), ready for
      hand-labeling once the schema exists. **No longer regenerable after the 90-day purge** — it was
      sampled from rows that the purge deletes, which is why the frozen snapshot has to be taken
      first (Phase 1b). Ten of these rows are Adzuna, now a cut source; they stay valid as *eval
      inputs* out of the frozen DB even though nothing new arrives from there.

## Phase 1b — Remote-source pivot + 90-day window (decided 2026-08-11)

**Why:** the project is being repointed at sources I'd actually use to find remote work. Corpus
*size* is explicitly no longer a goal; freshness is. Postings older than 90 days are mostly filled
and only add noise to retrieval.

### Source lineup — all four probed live on 2026-08-11

| Source | Verdict | Detail |
|---|---|---|
| **HN** | keep, rolling | The only pure-prose source. A 90-day window still holds ~3 monthly threads, so prose keeps flowing — only the 2023 backfill dies. |
| **Remotive** | keep | Works. Still only ~34 live postings; no volume on its own. |
| **Habr Career** | add | Undocumented frontend API: `GET career.habr.com/api/frontend/vacancies?type=all&remote=true&q=…` → 200 JSON, `{list, meta:{totalResults, perPage:25, currentPage, totalPages}}`. Real pagination. |
| **Web3.career** | add, blocked on key | Free but email-gated. Without a token the endpoint **302s to the sales page** — which is what `web3_client.py`'s catch-all `except` currently swallows. Key applied for 2026-08-10, expected 2026-08-11. |
| **CryptoJobsList** | parked | No usable public feed. `/api/jobs` returns the Next.js HTML shell; unauthenticated hits get a Cloudflare interstitial (403). The only real feed, `cryptojobslist.com/rss` → 308 → `api.cryptojobslist.com/jobs.rss`, returns **valid RSS with zero `<item>` elements**. `api.cryptojobslist.com/jobs{,.json}` → 404. Revisit if their feed ever has items; ingesting it today means scraping against Cloudflare. |
| **Adzuna** | cut | Imputed salaries, truncated descriptions, not remote-focused. |

**Habr caveat:** the list endpoint returns card data only — `title`, `skills[]`,
`salary{from,to,currency}`, `employment`, `remoteWork`, `publishedDate.date` (ISO, `+03:00`) — and
**no description text**. `api/frontend/vacancies/{id}` serves the SPA HTML shell, so the actual
posting prose requires an HTML parse of `/vacancies/{id}`. Store that body, not just the card:
the card is pre-parsed, and pre-parsed input is what makes extraction a copy job. Postings are
Russian — that lands on the `stack` alias map, the seniority enums, and gold labeling.

**Keeping extraction non-trivial is the whole risk of this pivot.** Three of four sources hand over
clean JSON; if that's all the model ever sees, "why is there an LLM here?" has no good answer. The
defense: keep HN rolling, store Habr's HTML body, and hold structured fields out as ground truth in
the source adapters (already the Phase 2 design — it just matters more now).

### Retention rules

- **≤ 90 days, enforced in two places.** Purge on age *and* filter at ingest. Age-purge alone means
  every `load.py` run re-inserts the same expired postings the boards still serve, which the next
  purge deletes again — insert/delete churn forever, and `LoadStats` stops meaning anything.
- **Purge on `posted_at` needs a NULL guard.** `WHERE posted_at < now() - interval '90 days'`
  silently skips NULLs and those rows live forever. Currently 0 NULLs, so make the column
  `NOT NULL` now. (The old PROMPT.md note about 276 NULL HN rows is **stale** — verified all
  populated on 2026-08-11. The 276 is a coincidence: it's the HN row count inside the 90-day window.)
- **`db_meta(role)` guard.** One row, `'live'` or `'eval'`; the purge asserts `role = 'live'` before
  deleting. Two lines, and it removes the one mistake in this design that costs the eval baseline.
- **Time-series analytics lose their substrate.** A rolling 90-day window can't answer "how did Rust
  demand change over the year" — Phase 3 salary distributions and Phase 5 trend charts. Fix: write
  monthly rollups (skill frequency, salary percentiles by seniority) to an aggregate table the purge
  doesn't touch. Aggregates aren't postings, so they can be kept forever.

### Frozen eval DB

Decided: keep a **frozen snapshot DB, used for evals only**; the live DB is the 90-day rolling one.

- **"Frozen" means a versioned dump file, not a database nobody touches.** A second live DB drifts
  the first time something points `load.py` at it. Artifact of record is
  `evals/snapshots/YYYY-MM-DD_raw.dump`, committed; the running eval DB is a disposable restore.
- Full 7,162-row dump measured at **2.9 MB** compressed (12 MB table, 1,410-byte average
  `raw_text`) — commit it directly, git-lfs is not installed and not needed.
- Restore into a separate database `jobmarket_eval` in the same container. `EVAL_DATABASE_URL` in
  `.env` + `.env.example`. No second service, no second port.
- **Read-only role** (`SELECT` only) on the eval DB. That, not discipline about which URL is which,
  is what actually enforces frozen.
- **Inputs in the dump, labels in git.** Hand-written labels get revised as the schema firms up and
  those revisions must show up as reviewable diffs — invisible inside a binary dump. Key labels on
  `(source, external_id)`, not `raw_postings.id`, so they survive a re-snapshot. Name the labeled
  file `evals/gold_30_labeled.json`; `.gitignore` already excludes
  `evals/gold_30_candidates.json`, and the labeled file must not get caught by that or a future glob.
- **Re-snapshot deliberately, never in place:** new date-stamped filename, re-run labeling against
  it. Each re-snapshot is another ~3 MB blob — fine at the two or three times it'll actually happen,
  which is the natural brake on doing it casually.
- **Don't put embeddings in the dump** once Phase 3 lands: 7k × 1024 dims × 4 bytes ≈ 29 MB of float
  noise that won't compress. Snapshot `raw_postings` + `structured_postings`, regenerate embeddings
  on restore — that makes the eval DB a test of the embedding pipeline instead of a fossil of it.
- **Agent evals must run against the frozen snapshot.** Phase 4's ~15 canned questions asserted
  against SQL ground truth would otherwise fail every week for reasons unrelated to the agent, since
  the live corpus purges and refills underneath them.

### Tasks (in order — 1 has a deadline, the rest don't)

- [ ] **Snapshot before the first purge.** 4,176 HN rows are unrecoverable once deleted. Row counts
      at decision time: hn 4,452 total / **276** within 90d; adzuna 2,676 / 2,374; remotive 34 / 34.
- [ ] Fix `find_hiring_threads` import so `load.py` runs again; clear the 8 ruff errors.
- [ ] `003_*.sql` — widen the `source` CHECK (`hn`, `remotive`, `web3`, `habr`), `posted_at NOT NULL`,
      add `db_meta`.
- [ ] Restore `jobmarket_eval`, create the read-only role.
- [ ] Purge + ingest-side age filter, behind the `db_meta` guard.
- [ ] Habr client — needs no key, so it's unblocked regardless of what arrives tomorrow.
- [ ] Web3.career client — rewrite once a real response can be inspected (see defects below).
- [ ] Cache a fixture response per source. Two of four sources are undocumented or Cloudflare-guarded;
      the demo path must run offline or it will break on presentation day.

**`web3_client.py` defects (written before a token existed — field names are guesses):**
1. No `timeout=`; the other clients use 10s. A hung socket hangs the whole load.
2. Catch-all `except` → `return []`, so a dead API logs "Fetched 0 postings" and exits 0. Remotive
   and Adzuna raise; this should too.
3. Flattens jobs into `{title, company, url, …}`, but `load.py` stores `json.dumps(job)` verbatim.
   Pre-flattening breaks the replay-buffer rule — return raw dicts, flatten in the Phase 2 adapter.
4. `company_name` / `apply_url` / `salary_range` are unverified guesses. Dump one real response first.
5. `limit: 5` hardcoded, no pagination.

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
- [ ] Hand-label `evals/gold_30_labeled.json` — against the **frozen snapshot** (Phase 1b), keyed on
      `(source, external_id)`, committed to git. Never label against the live rolling DB.
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
- The gold set's role-split signal rests **entirely on the 10 HN rows** — Adzuna and Remotive are
  1-posting-1-role by construction, so their role-count ground truth is trivially `1`. Consider
  hand-picking a few more multi-role HN postings before labeling.

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