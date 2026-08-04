# Session kickoff prompt

Paste this to start the next Claude Code session:

---

Read README.md and docs/ROADMAP.md first — a job-market intelligence agent: ingest HN "Who is
Hiring" + Remotive + Adzuna postings → LLM structured extraction (Pydantic, quote-grounded) →
Postgres + pgvector → DeepSeek agent with tools → FastAPI. This is the **service/infra** portfolio
project; the retrieval/agent lab is the separate **product-search** repo. Built skill-by-skill, to
learn.

**How to work with me:**
- **Short, structured answers.** Numbered steps or bullets, not prose walls. Actionable first,
  rationale only where a decision hinges on it. Long detailed messages are the wrong format for me.
- I write the code by default. Your job is guidance, review, and feedback — don't edit project
  files unless I ask. Docs (README / ROADMAP / PROMPT) are fair game on a wrap-up.
- When I say I've implemented something, verify it: read the code and run it before assessing.
  Paste-errors-not-fixes — explain the error, don't silently patch.
- I'm doing this to learn — explain the concept when I ask, not by default. Every file must pass
  the explain-back test before we call a step done.
- Watch my token budget: prefer a fresh session per phase over dragging a long context around, and
  say so when a wrap-up + new session is the cheaper move.

**Where we left off (2026-08-03):** Phase 1 (ingestion) is **done end-to-end**, the corpus
composition problem is **fixed**, and all of that is **committed** (`6c83bc1`). **7,162 postings
loaded** — HN 4,452 (62.2%), Adzuna 2,676 (37.4%), Remotive 34 (0.5%). That ratio was 89.6% Adzuna /
9.2% HN / 1.1% Remotive two sessions ago; it inverted the project's premise (Phase 2 exists to prove
LLM extraction from messy prose, and messy prose was a tenth of the data). Fixed by adding
`find_hiring_threads(since, until)` to `hn_client.py` and backfilling all of 2023's HN threads (12
months, 4,176 rows) — Remotive's free API only ever exposes ~34 live postings so it can't carry
volume, and Adzuna's growth was capped (`max_pages` 50→10) so it stops dominating every re-run.

Also committed: a `posted_at TIMESTAMPTZ` column (`002_posted_at.sql`) — `thread_month` was
overloaded as the only temporal signal for all three sources. Adzuna/Remotive backfilled from their
own JSON via SQL; HN captures `posted_at` per-comment going forward (`HNComment.created_at`). **276
old HN rows (from before this column existed) still have `posted_at IS NULL`** — recoverable
(Algolia's item API returns `created_at` per comment ID; sketch exists), not yet run. And `load.py`/
`adzuna_client.py` now use stdlib `logging` instead of `print`, with `upsert_posting` logging-and-
continuing on a bad row instead of the whole batch dying blind.

**Gold-set tooling started, not yet run for real.** `evals/test.py` is an interactive CLI: loads a
candidates JSON, shows each posting's `raw_text`, `y`/`n`/`q` to accept, saves incrementally to
`evals/gold_30.json`, dedupes on `(source, external_id)` (not `external_id` alone — sources can
collide there per the schema's own uniqueness constraint). `evals/candidates_hn.json` (40 random HN
postings, exported with `source` field included) already exists. **`evals/` is untracked — nothing
committed yet, including `test.py` itself.** Next session: run the review (`uv run python
evals/test.py evals/candidates_hn.json`), pick ~15 messy ones, then export+review Adzuna (~10) and
Remotive (~5) candidates the same way (SQL pattern for cross-source-safe exports is in chat history
if not restated below). Decide then whether `candidates_*.json` should be gitignored (regenerable
from SQL) while `test.py` gets committed for real.

**Next up (in order):**
1. Run the gold-set review session (`evals/test.py`) across all three sources — the actual labeling
   still can't happen until the schema exists (next item), but candidate *selection* can finish now.
2. Phase 2: finalize the Pydantic extraction schema (open questions logged in ROADMAP.md) — unblocks
   hand-labeling `evals/gold_30.json`.
3. Optional, low priority: backfill `posted_at` for the 276 old HN rows.

**Watch out:**
- Docker needs no babysitting — it is a systemd service, `enabled` at boot, and the user is in the
  `docker` group (no `sudo`) — but stopping the rogue Windows Postgres service *did* need an
  elevated PowerShell (`Start-Process -Verb RunAs`).
- `uv run mypy src` works directly; the broken `.venv/Scripts/mypy.exe` trampoline was a
  Windows-only uv bug and no longer applies.
- Proxy: `~/.proxy.env` is the single source of truth (`autoProxy=false`). Never put globs (`127.*`,
  `<local>`) in `no_proxy` — curl tolerates them, `requests`/`httpx` do not, and localhost calls
  then silently route through the proxy. The Docker **daemon** proxy is a separate scope in
  `/etc/systemd/system/docker.service.d/`. It's also flaky on long-running loops against external
  hosts — a real run died mid-`adzuna_client.py` page loop on a dropped proxy connection; retry/
  backoff there now absorbs it.
- `adzuna_client.py`'s retry logic still only catches `ConnectionError`/`Timeout` — a 429 or 5xx
  raises `HTTPError` uncaught and kills the whole `load.py` run (HN/Remotive rows included, since
  they're inserted after Adzuna's fetch completes). Flagged, not fixed.
- Checked cross-source dedup (Adzuna/Remotive overlap) via `pg_trgm` — zero matches found. Not worth
  building dedup logic on current evidence; re-check post-Phase-2 with real embeddings instead of
  trusting this as final.
- ROADMAP.md has stale/contradictory notes: "Remotive client" checked off in one place, unchecked in
  another; a note about revisiting Remotive's publish date that's already resolved. Not cleaned up.
- `hn_client.py`, `remotive_client.py`, and `adzuna_client.py` docstrings/comments were removed
  deliberately across all three; don't flag it again.
- Untracked junk in the tree: `.claude/settings.json` (`.gitignore` only covers
  `.claude/settings.local.json`).

Start by checking the current state of the repo in case I've changed things since.

---
