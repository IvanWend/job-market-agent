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

**Where we left off (2026-08-21).** `run` is written and the gate is green — ruff, mypy over 17
files, 83 tests. Its final shape: chunk `rows`, build payloads inside a try/except that synthesizes
`Outcome(status="error", model="adapter", …)`, `asyncio.gather` the `extract` calls, then re-pair
with the chunk and `persist` serially; counters for ok/invalid/error plus roles and usage, the
usage ones accumulated *outside* the status branches because an `invalid` outcome still burned up
to three requests. One `logger.info` checkpoint per chunk, `done = i + len(chunk)`.

**`run` has never executed.** No LLM call has been made in this project yet — `extract`'s LLM path
still has not survived a real DeepSeek response, and `transform(result.output)` against real model
output is what the pilot proves. `extraction_runs` and `structured_postings` are still empty;
`pending()` still returns the full 1,098 (502 hn). `persist` remains verified against the live DB
from 2026-08-20 (all three statuses, orphan-clearing re-run, inside a rolled-back transaction).

**Decision locked today** (in DECISIONS.md): tracing is Langfuse Cloud free tier over OTLP, using
the OpenTelemetry SDK already installed transitively via `logfire` — no new dependency.

**Next up — `main`, then tracing, then the pilot.** Strict order: `main` first, because the tracing
setup lives *inside* it and would otherwise be written into a body that gets deleted.

1. `main()`: argparse `--limit`, `--source`, `--model`, `--chunk-size`, `--dry-run` → connect →
   `pending` → guard `if not rows` (log and return *before* `build_agent`) → `--dry-run` returns
   after printing the count and first few ids, also before `build_agent` → `build_agent` →
   `time.perf_counter()` around `await run(...)` → log the summary off the returned `Stats`.
   Wall-clock and tokens are the two numbers the pilot exists to produce. It currently hardcodes
   `sources=["hn"], limit=5` and does its own serial loop; that whole body is what gets replaced.
2. Tracing, wired into `main`. Two `.env` variables and one function:
   `OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel` (US region is
   `us.cloud.langfuse.com`), `OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20<base64>` where the
   base64 is `printf '%s' 'pk-lf-…:sk-lf-…' | base64 -w0`, plus
   `OTEL_SERVICE_NAME=job-market-extraction`. **The `%20` is load-bearing** — the value is parsed as
   URL-encoded `key=value` pairs and a literal space silently 401s every export. Then
   `configure_tracing()` → `TracerProvider` + `BatchSpanProcessor(OTLPSpanExporter())` +
   `trace.set_tracer_provider(...)` + `Agent.instrument_all()`, returning the provider so `main` can
   `provider.shutdown()` in a `finally` (see GOTCHAS: extraction — both traps here bite silently).
   `OTLPSpanExporter()` needs no arguments; it reads the env and appends `/v1/traces`. It must be
   constructed after `load_dotenv()`, which already runs at import.
3. Verify with `--limit 1` that one trace lands in the Langfuse UI. Don't discover a broken auth
   header 20 calls in. The exporter uses `requests`, so it honors `HTTPS_PROXY` from `~/.proxy.env`
   — first place to look if traces never appear and nothing errors.
4. Pilot `--limit 20 --source hn`; measure cost and wall-clock. Then the full 1,098-row pass.

**Still open:** `UsageLimits(request_limit=4)` on the `agent.run` call in `extract`, so a retry storm
can't run away on an unattended 1,098-row pass. `UsageLimitExceeded` subclasses `AgentRunError`, so
the existing except blocks already route it to `status="error"` — no other change needed.

---
