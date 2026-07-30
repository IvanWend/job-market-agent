# Job Market Intelligence Agent

An agent that ingests tech job postings from heterogeneous sources, extracts structured data from
messy prose with an LLM, stores it in **Postgres + pgvector** (relational *and* embeddings in one
database), and answers analytical questions about the job market — *"what skills are trending for
backend roles"*, *"which postings match this résumé"*. Portfolio project; second after
[cv-tailor-ru](../) (LLM résumé tailoring).

**Status:** early — Phase 1 (ingestion) in progress. See [docs/ROADMAP.md](docs/ROADMAP.md) for what
is built vs. planned, and [docs/PROMPT.md](docs/PROMPT.md) for the session-kickoff brief.

**Career signals targeted:** structured LLM extraction from unstructured text, RAG over a
self-built corpus, agent tool-calling, eval-driven development, LLM observability, containerized
deployment.

## How it works

```
INGESTION    HN "Who is Hiring" (Algolia API) + Remotive API  ──►  raw_postings (Postgres)
EXTRACTION   LLM + Pydantic schema, grounded by verbatim quotes ──►  structured_postings
STORAGE      Postgres + pgvector; local bge-small-en-v1.5 embeddings ──►  posting_embeddings
AGENT        DeepSeek tool-calling loop: sql_query · vector_search · resume_match
SERVING      FastAPI (SSE streaming) · Langfuse tracing · Docker Compose
```

The design contrast that makes the project a good demo: **HN postings are pure unstructured prose**
(hardest extraction target), **Remotive is semi-structured JSON** — normalizing both into one schema
is the point. Every non-null extracted field carries a **verbatim source quote** so evals can check
grounding and catch fabrication (lesson carried from cv-tailor-ru).

## Tech stack

| Concern | Choice |
|---|---|
| Language | Python 3.12 |
| Agent + extraction LLM | DeepSeek (OpenAI-compatible API); Groq fallback |
| Structured outputs | Pydantic v2 — the schema is the contract for extraction *and* evals |
| Embeddings | `BAAI/bge-small-en-v1.5`, local via sentence-transformers (384-dim) |
| Database | Postgres 17 + pgvector (single DB: relational + vector) |
| API | FastAPI, SSE streaming |
| Tracing | Langfuse (self-hosted, Docker) — every LLM call traced from day one |
| Orchestration | Docker Compose |
| Testing / evals | pytest + custom eval scripts + gold-set JSON |

## Data sources

- **HN "Who is Hiring" (primary)** — monthly threads via the free Algolia HN API
  (`hn.algolia.com/api/v1`); top-level comments are job postings, pure prose. No auth.
- **Remotive (secondary)** — `remotive.com/api/remote-jobs`, free, no auth; semi-structured JSON.
- **Adzuna (v0.3, optional)** — free key, rate-limited; adds volume + salary data.
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
  thread_month DATE, ingested_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ,
  CHECK (source IN ('hn','remotive','adzuna')), UNIQUE (source, external_id)
)
structured_postings ( id, raw_posting_id FK, extracted JSONB, model, prompt_version, extracted_at )
posting_embeddings  ( posting_id FK, embedding vector(384), embedded_text )
```

Ingestion is **idempotent**: the loader upserts on `(source, external_id)` with a guarded
`ON CONFLICT … DO UPDATE … WHERE raw_text IS DISTINCT FROM …`, so re-fetching an unchanged posting
is a true no-op and `updated_at` only moves when the text actually changes.

## Setup

> Most commands below are **planned** — the project is still in Phase 1. Working today: the Docker
> DB, the `raw_postings` schema, and the HN client (thread lookup + comment fetch).

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker Desktop, a DeepSeek API key.

```powershell
# 0. Create the venv and install locked deps
uv sync

# 1. Bring up Postgres + pgvector
docker compose up -d

# 2. Apply the schema (re-runnable)
Get-Content db/schema/001_raw_postings.sql -Raw |
  docker compose exec -T db psql -U jobmarket -d jobmarket -v ON_ERROR_STOP=1 -f -

# 3. .env (git-ignored) — see .env.example
#   POSTGRES_PASSWORD=...
#   DEEPSEEK_API_KEY=sk-...
```

## Project structure

```
pyproject.toml         # deps (uv) + ruff/mypy config; uv.lock is committed
docker-compose.yml     # Postgres 17 + pgvector, healthcheck, pgdata volume
db/schema/             # numbered, re-runnable DDL migrations (001_raw_postings.sql, …)
src/
  ingestion/
    hn_client.py       # Algolia HN client: find thread → fetch top-level comments (HNThread)
    load.py            # upsert raw postings into Postgres (idempotent) — in progress
docs/
  ROADMAP.md           # phased plan with progress checkboxes + decision log
  PROMPT.md            # paste-to-start session kickoff brief
```

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
