# Session state

Volatile half only — where the work stands right now. The stable half (project brief, working
style, conventions, environment gotchas) lives in a local, git-ignored `CLAUDE.md` that loads
automatically; don't paste it and don't duplicate it back here.

Paste this to start the next session:

---

**Vertical slice, step 1 of 4** (locked 2026-08-19 in DECISIONS.md under "Pipeline"): full
extraction pass → embeddings + `vector_search` → agent loop + FastAPI/SSE → *then* label. Labeling,
the eval script and the remaining extraction tests stay deferred. Don't re-litigate it into eval
work.

**Where we left off (2026-08-20).** `pipeline.py` has `pending`, `build_agent`, `extract` and
`persist`. `persist` is verified against the live DB — all three statuses, every column landing in
the right place, and a re-run with fewer roles clearing the orphans — inside a rolled-back
transaction, so `extraction_runs` and `structured_postings` are both still empty and `pending()`
returns the full 1,098 (502 hn). Gate green: ruff, mypy over 17 files, 83 tests.

`extract`'s LLM path has **not** survived a real DeepSeek response end to end. Everything up to
`agent.run` is exercised; `transform(result.output)` against real model output is what the pilot
proves.

**Two decisions locked today**, both in DECISIONS.md:

- Embeddings are `bge-m3` via Ollama at `vector(1024)`. 42% of the corpus is Russian; measured RU/EN
  paraphrase cosine 0.824 on the local instance, and 8192-token context vs `bge-small`'s 512.
  README, ROADMAP and DECISIONS are already updated together; the `posting_embeddings` DDL is not
  written yet and must use 1024.
- `extract` catches `(AgentRunError, TimeoutError)` only, never bare `Exception`.

**Next up — `run` and `main`, then the pilot** (`--limit 20 --source hn`) to measure cost and
wall-clock, then the full 1,098-row pass.

`run(conn, agent, rows, model, chunk_size)`:

- Chunk `rows`; per chunk build payloads with `to_extraction_input`, `asyncio.gather` the `extract`
  calls, then loop the results and `persist` **serially**. One psycopg connection is not safe for
  concurrent use — no DB access inside a gathered task.
- `persist` opens its own `conn.transaction()`, so don't wrap the loop in another one: on an
  already-open transaction the inner block demotes to a savepoint and the chunk stops being
  independently committed.
- Wrap `to_extraction_input` in try/except — a malformed Habr blob would otherwise kill the chunk.
  Synthesize `Outcome(status="error", model="adapter", ...)` so the row is still claimed.
- Accumulate ok/invalid/error, roles, `tokens_in`/`tokens_out`/`requests`; print one checkpoint line
  per chunk. Return a small `Stats` NamedTuple. Chunk size doubles as the checkpoint interval —
  start at 5, since `retries=2` means one row can be three calls.

`main()`: argparse `--limit`, `--source`, `--model`, `--chunk-size`, `--dry-run` → connect →
`pending` → `build_agent` → `run` → print the summary. It currently hardcodes `sources=["hn"],
limit=5` and does its own serial loop; that whole body is what gets replaced.

**Still open before the full pass:** Langfuse. DECISIONS says every LLM call is traced from the
first one, but no `langfuse` dependency is installed — `logfire` 4.40.0 is. Cheapest route is
`Agent(..., instrument=True)` + OTLP export. Decide before the pilot or amend the decision.
Also consider `UsageLimits` on the agent so a retry storm can't run away unattended.

**Concept I want explained tomorrow:** async/await — what `asyncio.gather` actually does, why the
chunked-gather-then-write-serially shape is required here, and what `await` is really yielding to.

---
