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

## Build status (updated 2026-07-30)

**Working now:** `hn_client.py` is **complete**: `find_latest_hiring_thread()` resolves the newest
thread via `search_by_date`, and `fetch_thread(story_id)` returns a typed `HNThread` with its
top-level comments. Toolchain is uv + ruff + mypy, all three clean. Repo is on git (`main`, level
with `origin/main`).

**Not running:** the database. The dev environment moved to WSL2 (below), which means a **fresh
Docker with no volumes** — `docker compose ps` is empty and the `pgdata` volume from the old
Docker Desktop install is gone. `001_raw_postings.sql` was applied and verified in that old
volume, so the schema must be re-applied before the loader can be tested. Treat the DB as
un-provisioned.

**Environment (2026-07-30) — moved from PowerShell/Docker Desktop to WSL2.** Verified end to end:

| Layer | State |
|---|---|
| Shell / repo | WSL2 Ubuntu, bash. Repo on **ext4** (`~/projects/job-market-agent`), not `/mnt/c` |
| Python | uv 0.11.32, CPython 3.13.14, `.venv` Linux-side (`bin/`, no `Scripts/`), `uv.lock` in sync |
| Docker | **Engine native in WSL** (systemd, `enabled` at boot, user in `docker` group). No Docker Desktop |
| Postgres client | `psql` / `pg_dump` 17.10 installed on the host — no more `docker exec` round-trips |
| Ollama | Stays on the **Windows** host, reached at `localhost:11434` via `networkingMode=mirrored`. Models present: `bge-m3` (1024-dim, embedding), `qwen2.5:3b-instruct`, `qwen2.5:7b-instruct` |
| Proxy | v2rayN `127.0.0.1:10808` (mixed inbound: HTTP **and** SOCKS5). Three independent scopes, all green |

**Decision (2026-07-30) — one proxy definition, not four.** `autoProxy=true` used to mirror the
Windows proxy into WSL, but it injected a **Windows-format** `no_proxy` (`127.*`, `<local>`) that
curl tolerates and `urllib`/`requests`/`httpx` silently do not — so localhost traffic could take the
proxy. Now `autoProxy=false` and `~/.proxy.env` is the single source of truth, sourced from
`~/.profile` (login shells) and `~/.bashrc` (interactive), with `~/.config/environment.d/10-proxy.conf`
for `systemctl --user`. `no_proxy` uses plain hosts and leading-dot suffixes only — **no globs**.
`ALL_PROXY` deliberately stays `http://`: 10808 also speaks SOCKS5, but `socks5h://` makes `requests`
raise `InvalidSchema` unless `pysocks` is installed. The Docker **daemon** is a separate scope —
`/etc/systemd/system/docker.service.d/http-proxy.conf` — and is unaffected by any of the above.

*Residual gap (accepted):* a cold non-interactive, non-login shell (`bash -c` spawned outside a
login session) reads neither `.profile` nor `.bashrc`, so it falls back to whatever the parent
passes. `BASH_ENV` covers the case where the parent *was* a login shell. Not worth chasing further.

**Decision (2026-07-26) — two schema mechanisms, one job each.** Compose mounts `./init` at
`/docker-entrypoint-initdb.d`, whose scripts run **only when the data directory is empty** — first
boot, then silently never again. That makes it *bootstrap*, not migration. So `db/schema/` stays the
re-runnable path applied by hand (the skill worth having), and `init/` is reserved for at most
`CREATE EXTENSION IF NOT EXISTS vector;`. `001_raw_postings.sql` must not live in both.

**Decision (2026-07-27) — `/items/` over paginated search.** Two Algolia routes reach a thread's
comments. `search_by_date?tags=comment,story_<id>` returns every comment at every depth (436 for the
July 2026 thread, of which 276 are top-level), so it needs a client-side `parent_id` filter and
pagination once a thread passes the 1000-hit ceiling. `/api/v1/items/<story_id>` returns the tree in
one request, where `children` *is* the top-level list — no pagination, no depth filter — and carries
the story's own `created_at` and `title` in the same payload. Verified: both routes agree at 276.

**Decision (2026-07-27) — the client speaks HN, the loader speaks SQL.** `fetch_thread` returns
`HNThread`/`HNComment` (frozen dataclasses), *not* dicts shaped like table columns, so that exactly
one module knows `raw_postings`' column names when the Remotive client lands. Consequence: the
client returns `created_at` as the **raw ISO string**; `load.py` owns the truncation to
`thread_month`. The field is deliberately not named `thread_month` in the client — it holds a full
timestamp, and a name that promises a month would read as correct in review while being wrong.
`raw_postings_thread_month_is_month_start` is the backstop if the loader ever forgets.

**In progress — `load.py` flow** (skeleton written 2026-07-28; runs end-to-end, DB half unwired):

1. [ ] Pre-flight: `docker compose up -d`, re-apply `001_raw_postings.sql` (the old volume is gone),
   `DATABASE_URL` in `.env`, work on a branch.
2. [x] `to_thread_month(created_at: str) -> date` — `fromisoformat` (handles the `Z`), stay in UTC,
   `.date().replace(day=1)`. Returns `date(2026, 7, 1)`; mypy clean.
3. [x] `thread_to_rows(thread) -> list[tuple]` — emits `(source, external_id, raw_text,
   thread_month)`, month derived once outside the loop; mypy clean. The `"HN"`/`"hn"` case bug is
   **fixed** (`load.py:33` emits `"hn"`). Throwaway when Remotive lands.
4. [ ] `UPSERT_SQL` — write it in psql by hand first. *Current draft conflicts on `(external_id)`
   where the only unique constraint is `(source, external_id)`, so Postgres raises*
   `42P10 there is no unique or exclusion constraint matching the ON CONFLICT specification`
   *— it cannot execute at all. It also never sets `updated_at = now()` and has no `WHERE` guard,
   so even with the conflict target fixed, (b) "identical row is a no-op" and (c) "changed field
   bumps `updated_at`" would both still fail.*
5. [ ] `upsert_postings(conn, rows) -> LoadStats` — source-agnostic, reused by Remotive. Caller
   owns the transaction. Returns counts; does not print.
6. [x] `__main__`: find thread → fetch → rows → print. Verified: 276 rows off the July 2026 thread.
   Still needs the upsert + count output wired in.
7. [ ] Verify: run twice → `N/0/0` then `0/0/N`. Then hand-edit one `raw_text` in psql → `0/1/N-1`.

Gotchas: `DO UPDATE` must set `updated_at = now()` (no trigger exists); count via
`RETURNING (xmax = 0)` — a suppressed guarded update returns *no row*, so `unchanged = len(rows) -
returned`; `with psycopg.connect()` commits on clean exit (not autocommit); `%s` placeholders only.

**Compose note:** `container_name:` was removed. It is a *global* Docker name, so a stopped container
from an earlier run could own the name and block `up`. Compose now scopes the name itself from the
**directory** name — the directory is still `job-market-agent`, so `docker compose config` reports
project `job-market-agent` and the container will come up as **`job-market-agent-db-1`** (not
`jobmarket-db-1`; only the `pyproject.toml` package name is `jobmarket`). The orphaned
`job-market-agent_pgdata` volume is no longer a concern — the WSL Docker install has **no volumes
at all**.

**Housekeeping / tech debt:**
- [x] Consolidated the HN client into `src/ingestion/`; fixed both package `__init__.py` files.
- [x] Dropped `requirements.txt` (UTF-16 `pip freeze`, ~90 stale transitive deps) for `uv` +
      `pyproject.toml` + committed `uv.lock`. Direct deps only: `requests`, `psycopg[binary]`,
      `python-dotenv`. `uv sync` prunes anything undeclared — it removed a leftover `httpx`.
- [x] Git repo bootstrapped: `main` branch, baseline commit, `.gitignore`, `.env.example` committed.
- [x] `.gitattributes` forces LF. Original reason: `core.autocrlf=true` was set globally on Windows
      and CRLF files break once mounted into the Linux Postgres container. Since the WSL move,
      `~/.gitconfig` has `core.autocrlf=input` (correct for Linux), so this is now belt-and-braces
      rather than load-bearing — keep it, since the repo is still cloned on Windows sometimes.
- [x] `.env` has `POSTGRES_PASSWORD`; `DEEPSEEK_API_KEY` placeholder in `.env.example` for Phase 2.
- [x] `hn_client.py` split string literal (`"objec" "tID"`) rejoined; still resolves the thread.
- [x] ruff + mypy in the `dev` dependency group (ruff excludes `*.md` so it leaves the aligned
      comments in the doc fences alone).
- [x] Closed the mypy `params` error: annotated `dict[str, str | int]`. Mixed `str`+`int` values
      infer as `dict[str, object]`, and `object` isn't in the union `requests.get` accepts — so the
      fix is an annotation, not a value change. `mypy src` is now clean; consider flipping
      `disallow_untyped_defs = true`.
- [x] `ruff format` applied to `hn_client.py`; all four files now report "already formatted".
      Adopting it repo-wide is therefore free — no reformat churn pending.
- [x] **Tooling gotcha (resolved by the WSL move):** `.venv/Scripts/mypy.exe` was a broken uv
      trampoline (`failed to canonicalize script path`). That was a Windows-only uv bug; the venv is
      now Linux-side and plain `uv run mypy src` works. No workaround needed.
- [ ] `init/` is empty, and git does not track empty directories — so a fresh clone has no `init/`,
      Docker auto-creates it empty, and `CREATE EXTENSION vector` runs nowhere. Add
      `init/001_extensions.sql` with `CREATE EXTENSION IF NOT EXISTS vector;` before Phase 3 or
      pgvector will fail confusingly. **Now is the cheap moment:** there is no `pgdata` volume, so
      the next `docker compose up -d` is a genuine first boot and the entrypoint *will* run it.
      Once the volume exists it silently never runs again.
- [ ] No `tests/` directory and `pytest` is not a declared dep. Phase 2 needs both — `uv add --dev
      pytest` when the loader lands.
- [ ] Config is not centralized: `load.py` imports `os` and `load_dotenv` but never calls either,
      and nothing anywhere reads `DATABASE_URL`. All three `.env.example` keys are currently unread
      by Python (`POSTGRES_PASSWORD` is consumed only by `docker-compose.yml`). Fold into a
      `config.py` when the psycopg half lands, rather than sprinkling `os.getenv`.

**Git — ongoing across every phase:**
- [ ] Every feature: branch → PR → self-review → merge (no direct commits to `main`)
      — **still not honoured**: all **five** commits went straight to `main`, and there is no
      `feat/loader` branch (it was never created). Start with the loader on a branch.
- [ ] Commit early and often (lesson: mid-session revert on cv-tailor-ru)

## Phase 1 — Ingestion (no LLM calls) ← IN PROGRESS

- [x] Docker Compose: Postgres 17 + pgvector (healthcheck, named volume, `init/` entrypoint)
- [x] Algolia HN client
  - [x] `find_latest_hiring_thread()` → newest thread `story_id` + title
  - [x] `fetch_thread(story_id)` → `HNThread` with all **top-level** comments. One `/items/` call,
        so no pagination. Comment `id` → `str` (it is the `external_id` dedup key; the API returns
        an int). Text kept as **verbatim HTML** — the table is a replay buffer, and stripping is a
        lossy parse that Phase 2 should do instead. Drops unusable comments via
        `(child.get("text") or "").strip()`, which covers all three shapes: absent key, present-but-
        null (deleted), and whitespace-only. `.get("text", "")` does **not** — a default only fires
        on a missing key, never on a present `null`.
- [ ] Remotive client
- [~] `raw_postings` schema + loader with dedup
  - [x] DDL `db/schema/001_raw_postings.sql` — written and previously verified: the guarded upsert
        gave `INSERT 0 1` / `0 0` / `0 1`, `(remotive, test-1)` inserted alongside `(hn, test-1)`,
        and all five constraints rejected bad rows (bad source, mid-month `thread_month`, HN without
        a month, blank text, manual `id`). **Re-apply needed** — that verification lived in the
        pre-WSL `pgdata` volume, which no longer exists. The DDL itself is sound; re-applying is
        a no-op by design.
        *Schema note:* the table has `ingested_at` + `updated_at` but deliberately **no**
        `posted_at` — `thread_month` carries the temporal signal for HN. Revisit if Remotive turns
        out to expose a real per-posting publish date.
  - [~] loader: idempotent upsert on `(source, external_id)` — SQL verified by hand in psql;
        `load.py` skeleton written (fetch → rows → print works, 276 rows). The `psycopg` half is
        unwired: `UPSERT_SQL` is defined but never executed, there is no `connect()` call, and
        `psycopg` is an unused import. See the numbered flow above for the `42P10` conflict-target
        bug. Also `load.py:40` rebinds `thread_to_rows` over the function it just called (5 mypy
        errors), and `thread_to_rows[2]` will `IndexError` on a thread with fewer than 3 comments.
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