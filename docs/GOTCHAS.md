# Gotchas

Traps carried forward because they bite in *later* phases, not because they were hard once.
Symptom → cause → fix. Decisions live in DECISIONS.md; progress lives in ROADMAP.md.

## Postgres

- **A CHECK constraint accepts a row it looks like it should reject.** A CHECK is satisfied by
  `TRUE` *or* `NULL` — only an explicit `FALSE` rejects. `CHECK (salary_max >= salary_min)` already
  accepts a partially-null band, and `CHECK (col <> 'x')` never fires when `col` is NULL. The
  `IS NULL` disjuncts in `005` are documentation, not logic.
- **Inserts start failing at runtime after widening an enum.** The three enum lists are duplicated
  between the `Literal`s at `normalize.py:9-11` and the CHECKs in `005_structured_postings.sql`,
  with nothing keeping them in sync. Widen both together.

## psycopg / Docker

- **`psycopg.connect()` with no argument connects to the wrong database.** It silently falls back to
  a local Unix socket instead of reading `DATABASE_URL`. Always pass the string explicitly.
- **`pg_dump` fails with `FATAL: role "root" does not exist`.** `docker exec ... pg_dump
  "$DATABASE_URL"` expands the variable on the *host*, so an unsourced `.env` passes an empty string
  and `pg_dump` falls back to the container socket as OS user `root`. Run `set -a; . ./.env; set +a`
  first, or pass `-U jobmarket -d jobmarket` explicitly.
- **A `conn.transaction()` block commits when you expected a savepoint.** On an *idle* connection it
  issues a real `BEGIN`/`COMMIT`; it only nests as a savepoint when a transaction is already open, so
  a bare `SELECT` beforehand silently demotes the next block.
- **A concurrent write corrupts the connection.** One psycopg connection is not safe for concurrent
  use, so gathered async tasks must not write. Gather the LLM calls in chunks and write serially from
  the main task; the chunk size doubles as the checkpoint interval.
- **Scripts target a container that doesn't exist.** The name is directory-derived
  (`job-market-agent-db-1`), not the `pyproject.toml` package name.

## Python / pytest

- **`import src` fails at collection.** No `[build-system]`, so nothing is installed, and under the
  default `prepend` import mode pytest puts only the *test file's* directory on `sys.path`. Fixed by
  `pythonpath = ["."]` in `[tool.pytest.ini_options]`. Don't "fix" it with `tests/__init__.py` —
  that makes tests a package and changes rootdir resolution.
- **`fixture 'value' not found`, raised at setup before any assert runs.** A test function's
  parameters are fixture requests, not typed locals — copying the function-under-test's signature
  onto the test asks pytest for fixtures by those names. Parameters come from
  `@pytest.mark.parametrize` or from a fixture.

## Data shape

- **Feeding `raw_text` to the LLM makes extraction a copy job.** For Remotive, Web3 and Habr it is
  the entire API JSON, so structured fields sit *inside* the model's input and quote-grounding is
  trivially satisfiable by quoting JSON. Splitting input from held-out truth is the adapters' job.
- **Habr's `raw_text` is the card dict plus a `description_html` key**, serialized with
  `ensure_ascii=False`. `description_html` is the input; `salary`, `skills`, `qualification` and
  `employment` are held-out truth. 142/459 carry an employer-stated salary.
- **Imputed salaries look like ground truth and aren't.** Web3's `estimated_*` and Habr's
  `predictedSalary` are the sites' own guesses. Only `salary_min_value`/`salary_max_value` and
  `salary.from`/`salary.to` are employer-stated.
- **Habr states currency as `'rur'`, which is not ISO 4217.** `currency_enum()` maps it, plus
  symbols; anything unrecognized returns `None` rather than putting junk in an ISO column.
- **`1С` scores as two different technologies.** It appears with a **Cyrillic С in 33 rows and a
  Latin C in 48**. Fold the Cyrillic→Latin homoglyphs (`СсАаЕеОоРрХх`) with `str.translate` before
  alias lookup.
- **Not every HN row is a job posting.** "One top-level comment = one posting" is a social
  convention, not an enforced rule; at least 16 of 502 are not postings — 11 discussion/self-promo/
  spam/`[flagged]`, 5 résumés in the wrong thread. That count is a **floor**. Verified against
  Algolia: genuine top-level comments, no client bug, nothing to fix at ingest.
- **Re-snapshot deliberately, never in place.** New date-stamped filename, re-run labeling. Labels
  key on `(source, external_id)`, not `raw_postings.id`, so they survive a re-snapshot.

## Extraction

- **Every HN quote fails containment against `raw_text`.** HN raw text holds `&amp;` and `&#x2F;`;
  the model quotes the rendered `&` and `/`. Measured: the same quote is `False` in `raw_text` and
  `True` in the cleaned text. Run containment against `html_to_text(raw_text)`, and feed the LLM
  that same cleaned string or the two drift again.
- **A quote fails containment because the source wrapped mid-sentence.** Prose is hard-wrapped
  (`ERC-7540 (async\nvaults)`) and the model quotes it with a space. Compare `" ".join(q.split())`
  against `" ".join(text.split())` — in the eval script, not in `html_to_text`, which has to keep
  paragraph structure.
- **Every HN salary is silently dropped.** The LLM extracts verbatim, so `"$180k"` and `"1.5M"`
  arrive as written and bare `float()` raises. `to_number` must handle magnitude suffixes.
- **The eval punishes a correct null.** Held-out truth with no evidence in the input is a legitimate
  null, not an extraction miss — score it that way whenever a source's structured field outruns its
  prose.
- **Re-extraction leaves orphan roles.** The unique `(raw_posting_id, role_index)` alone doesn't
  clear roles 2–3 when a re-run finds 2 where it found 4. `persist` must
  `DELETE FROM structured_postings WHERE raw_posting_id = %s` before inserting, in one transaction.
- **A crash drops rows from the resume query forever.** Write `extraction_runs` *last*, in the same
  transaction as the role rows, so a crash mid-write leaves the row unclaimed. Claim-then-work
  silently loses it.
- **`Agent(..., instrument=True)` raises `TypeError: unexpected keyword argument`.** On pydantic-ai
  2.24 `instrument` is not an `__init__` parameter — it is a settable attribute (`agent.instrument =
  True`) or the static `Agent.instrument_all()`. Most tutorials show the kwarg form.
- **Langfuse stays empty and nothing errors.** `BatchSpanProcessor` buffers spans and flushes on a
  background thread, so a short script exits before the last chunk's spans leave the process. Call
  `provider.shutdown()` in a `finally` around the run. Second suspect: the exporter speaks through
  `requests`, so it honors `HTTPS_PROXY` from `~/.proxy.env`.
- **`result.usage()` raises `'RunUsage' object is not callable`.** On `AgentRunResult` (pydantic-ai
  2.24) `usage` is a **property**, not a method. `RunUsage` itself carries `input_tokens`,
  `output_tokens` and `requests` — `requests` counts real API calls, so it is the retry-storm meter.
- **A code bug gets recorded as a DeepSeek failure and claims the row.** `except Exception` around
  `agent.run` swallowed a `TypeError`, `persist` wrote `status='error'`, and `pending()` then
  excluded those postings forever — the LLM calls had already been paid for. Catch
  `(AgentRunError, TimeoutError)` only (see DECISIONS: pipeline).
- **Two rows must short-circuit before any paid call:** the 6 that adapt with `prefilter` set, and
  the 1 whose adapted text is empty (a Habr posting with `description_html = None`). Store
  `model='prefilter'` so the coverage query can tell them from an LLM verdict.
