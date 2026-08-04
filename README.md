# Job Market Intelligence Agent

An agent that ingests tech job postings from heterogeneous sources, extracts structured data from
messy prose with an LLM, stores it in **Postgres + pgvector** (relational *and* embeddings in one
database), and answers analytical questions about the job market — *"what skills are trending for
backend roles"*, *"which postings match this résumé"*. Portfolio project; second after
[cv-tailor-ru](../) (LLM résumé tailoring).

**Status:** Phase 1 (ingestion) **done** — HN, Remotive, and Adzuna clients plus the idempotent
loader are all working and verified. **7,162 postings loaded** (HN 4,452, Adzuna 2,676, Remotive
34). Gold-set candidates selected; Phase 2 (extraction + evals) starts next. See
[docs/ROADMAP.md](docs/ROADMAP.md) for what is built vs. planned, and
[docs/PROMPT.md](docs/PROMPT.md) for the session-kickoff brief.

**Career signals targeted:** structured LLM extraction from unstructured text, RAG over a
self-built corpus, agent tool-calling, eval-driven development, LLM observability, containerized
deployment.

## How it works

```
INGESTION    HN "Who is Hiring" (Algolia) + Remotive + Adzuna APIs ──►  raw_postings (Postgres)
EXTRACTION   LLM + Pydantic schema, grounded by verbatim quotes ──►  structured_postings
STORAGE      Postgres + pgvector; local bge-small-en-v1.5 embeddings ──►  posting_embeddings
AGENT        DeepSeek tool-calling loop: sql_query · vector_search · resume_match
SERVING      FastAPI (SSE streaming) · Langfuse tracing · Docker Compose
```

The design contrast that makes the project a good demo: **HN postings are pure unstructured prose**
(hardest extraction target), **Remotive/Adzuna are semi-structured JSON** — normalizing all three
into one schema is the point, and Adzuna's own structured fields (salary, category) double as free
eval ground truth. Every non-null extracted field carries a **verbatim source quote** so evals can
check grounding and catch fabrication (lesson carried from cv-tailor-ru).

## Tech stack

| Concern | Choice |
|---|---|
| Language | Python 3.13 (pinned via `.python-version`; `requires-python >=3.12`) |
| Agent + extraction LLM | DeepSeek (OpenAI-compatible API); Groq fallback |
| Structured outputs | Pydantic v2 — the schema is the contract for extraction *and* evals |
| Embeddings | **Undecided** — `BAAI/bge-small-en-v1.5` via sentence-transformers (384-dim) as designed, vs. `bge-m3` via the already-installed local Ollama (1024-dim). Fixes `vector(n)`, so decide before Phase 3 ([ROADMAP](docs/ROADMAP.md#phase-3--storage--retrieval)) |
| Database | Postgres 17 + pgvector (single DB: relational + vector) |
| API | FastAPI, SSE streaming |
| Tracing | Langfuse (self-hosted, Docker) — every LLM call traced from day one |
| Orchestration | Docker Compose |
| Testing / evals | pytest + custom eval scripts + gold-set JSON |

## Data sources

- **HN "Who is Hiring" (primary)** — monthly threads via the free Algolia HN API
  (`hn.algolia.com/api/v1`); top-level comments are job postings, pure prose. No auth. Backfilled
  across multiple months, not just the latest thread.
- **Adzuna (volume)** — free key, rate-limited, paginated; carries most of the row count. Its
  `description` field is truncated to a snippet (~1.5KB cap) by the free tier — extraction on these
  rows legitimately nulls out fields whose evidence was in the cut-off text.
- **Remotive (secondary)** — `remotive.com/api/remote-jobs`, free, no auth; semi-structured JSON.
  The free API only ever exposes ~34 currently-live postings, no history — can't carry volume alone.
- **Ruled out:** hh.ru (API closed Dec 2025; ToS forbids derivative DBs — do not scrape),
  LinkedIn (ToS / auth walls).

## Data model

**Extraction schema** (Pydantic v2, draft — open questions tracked in the roadmap):

```python
class Posting(BaseModel):
    company: str | None
    title: str | None
    seniority: Literal["intern", "junior", "mid", "senior", "staff+", "unknown"]
    skills: list[str]                 # normalized lowercase, e.g. "python", "kubernetes"
    stack: list[str]                  # frameworks/infra (skills-vs-stack boundary TBD)
    salary_min: int | None            # annualized
    salary_max: int | None
    salary_currency: str | None       # ISO 4217
    remote_policy: Literal["remote", "hybrid", "onsite", "unknown"]
    location: str | None
    employment_type: Literal["full-time", "part-time", "contract", "unknown"]
    source_quotes: dict[str, str]     # field -> verbatim quote grounding the value
```

**Database schema** (Postgres — `raw_postings` finalized, others draft):

```sql
raw_postings (
  id BIGINT IDENTITY PK, source TEXT, external_id TEXT, raw_text TEXT,
  thread_month DATE, posted_at TIMESTAMPTZ, ingested_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ,
  CHECK (source IN ('hn','remotive','adzuna')), UNIQUE (source, external_id)
)
structured_postings ( id, raw_posting_id FK, extracted JSONB, model, prompt_version, extracted_at )
posting_embeddings  ( posting_id FK, embedding vector(384|1024), embedded_text )  -- dim TBD
```

Ingestion is **idempotent, verified end-to-end**: the loader upserts on `(source, external_id)` with
a guarded `ON CONFLICT … DO UPDATE … SET updated_at = now() WHERE raw_text IS DISTINCT FROM …`, so
re-fetching an unchanged posting is a true no-op and `updated_at` only moves when the text actually
changes. Verified against 276 real HN postings: the first load inserts all 276, a repeat run reports
all 276 `unchanged` with `updated_at` untouched, and hand-editing one row's text before a third run
produces exactly one `updated` row with a fresh `updated_at`.

## Setup

> Phase 1 is done — everything below is working today: `raw_postings` DDL, all three ingestion
> clients (HN, Remotive, Adzuna), and the loader (idempotent upsert, verified end-to-end).

Developed on **WSL2 Ubuntu** with Docker Engine running natively in WSL (systemd) — *not* Docker
Desktop. Requirements: Python 3.12+ (3.13 pinned via `.python-version`),
[uv](https://docs.astral.sh/uv/), Docker Engine + Compose, `postgresql-client`, a DeepSeek API key.

```bash
# 0. Create the venv and install locked deps
uv sync

# 1. Bootstrap the pgvector extension BEFORE first boot.
#    ./init is mounted at /docker-entrypoint-initdb.d, which runs only when the
#    data directory is empty — first boot, then silently never again.
mkdir -p init
printf 'CREATE EXTENSION IF NOT EXISTS vector;\n' > init/001_extensions.sql

# 2. Bring up Postgres + pgvector
docker compose up -d
docker compose ps                       # wait for "healthy"

# 3. Apply the schema (each file is re-runnable, so safe to repeat)
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/schema/001_raw_postings.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/schema/002_posted_at.sql

# 4. .env (git-ignored) — see .env.example
#   POSTGRES_PASSWORD=...
#   DATABASE_URL=postgresql://jobmarket:...@localhost:5432/jobmarket
#   DEEPSEEK_API_KEY=sk-...
#   (POSTGRES_PASSWORD and the password embedded in DATABASE_URL must match, or step 3+ fails
#   with "password authentication failed")
```

**WSL2 + mirrored networking gotcha:** if step 2 fails with `failed to bind host port ... address
already in use`, something on the **Windows host** already owns 5432 — `networkingMode=mirrored`
means Windows and WSL share the port space. Check `Get-Service *postgres*` in PowerShell; a native
Postgres install (even one not obviously running as "a service" at a glance) is the likely culprit.
Also: if that first `up` fails mid-bind, the container can be left with a broken network sandbox
even after a *later* `docker compose up -d` reports success and the healthcheck goes green —
`NetworkSettings.Networks`/`.Ports` end up empty and the host can't reach it at all. Fix with
`docker compose down && docker compose up -d` to force a real recreate, not a `start` of the
already-broken container.

Step 3 uses the host `psql` directly rather than `docker compose exec` — one less indirection, and
it proves `DATABASE_URL` actually works before the loader depends on it.

**If Ollama is on a Windows host** (the current setup), reach it from WSL at `localhost:11434` with
`networkingMode=mirrored` in `.wslconfig`. Keep `no_proxy` free of glob patterns — `curl` tolerates
`127.*` and `<local>`, but `urllib`/`requests`/`httpx` do not, and localhost calls will silently
take the proxy. See the environment table in [docs/ROADMAP.md](docs/ROADMAP.md).

## Project structure

```
pyproject.toml         # deps (uv) + ruff/mypy config; uv.lock is committed
.python-version        # 3.13 — uv reads this
.env.example           # committed key names, no values; .env is git-ignored
.gitattributes         # force LF (files cross into the Linux Postgres container)
docker-compose.yml     # Postgres 17 + pgvector, healthcheck, pgdata volume, ./init mount
db/schema/             # numbered, re-runnable DDL (001_raw_postings.sql, 002_posted_at.sql)
init/                  # first-boot bootstrap only — vector + pg_trgm
src/
  ingestion/
    hn_client.py       # Algolia HN client: find thread(s) → fetch top-level comments (HNThread)
    remotive_client.py # Remotive API client
    adzuna_client.py   # Adzuna API client — pagination + retry/backoff
    load.py            # fetch all three, convert to rows, idempotent upsert into Postgres
evals/
  generate_gold_dataset.py  # pulls gold-set candidate rows from raw_postings
docs/
  ROADMAP.md           # phased plan with progress checkboxes + decision log
  PROMPT.md            # paste-to-start session kickoff brief
```

Two schema mechanisms, one job each: `init/` is **bootstrap** (runs once, only when the data
directory is empty) and `db/schema/` is the **re-runnable** path applied by hand. No file belongs in
both — see the 2026-07-26 decision in the roadmap. There is no `tests/` yet, and the project is
intentionally not an installable package (no `[build-system]`), so imports are `src.ingestion.…`
from the repo root.

## Scope

This is the **service / infrastructure** project: Postgres, pgvector, a live paginated ingestion
API, FastAPI, Docker, and observability are all **load-bearing** here. The pure retrieval + agent
lab (hybrid search, reranking, hand-rolled agent loop on ChromaDB) lives in the companion
**product-search** project. Together they cover the AI-engineering checklist without duplicating a
skill across both repos.

## Notes

- English-only, international sources — author consumes content in English; portfolio reads
  internationally.
- The embedding model must match at index and query time; changing it means re-embedding.
