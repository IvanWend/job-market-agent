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

**Where we left off (2026-08-04):** Phase 1 (ingestion) is **done, committed, and pushed**.
**7,162 postings loaded** (HN 4,452 / Adzuna 2,676 / Remotive 34) across all three sources, with a
`posted_at` timestamp per row. Gold-set candidates are selected: 10 each from HN/Adzuna/Remotive,
picked via random sampling (`evals/generate_gold_dataset.py`, parameterized `psycopg` queries — not
hand-curated for messiness), sitting in `evals/gold_30_candidates.json` (gitignored, regenerable).
**Tomorrow starts Phase 2.**

**Next up (in order):**
1. Finalize the Pydantic extraction schema (open questions logged in ROADMAP.md).
2. Hand-label the 30 gold-set candidates against that schema.
3. Build the extraction pipeline + eval script.

**Watch out:**
- Docker needs no babysitting — systemd service, enabled at boot, user is in the `docker` group. A
  rogue Windows Postgres service on the same port has bitten this before — if `docker compose up`
  fails to bind 5432, check `Get-Service *postgres*` in an elevated PowerShell.
- Proxy: `~/.proxy.env` is the single source of truth. Never put globs (`127.*`, `<local>`) in
  `no_proxy` — `requests`/`httpx` don't honor them the way `curl` does, and localhost calls silently
  route through the proxy.
- `adzuna_client.py`'s retry logic only catches `ConnectionError`/`Timeout` — a 429 or 5xx still
  kills the whole `load.py` run. Known, not fixed.
- 276 old HN rows predate the `posted_at` column and are still `NULL` there — low priority, fix
  sketch was worked out if it ever matters.
- The gold-set's random (not hand-curated) selection is a real quality tradeoff — worth revisiting
  if Phase 2 eval accuracy looks off and the postings themselves turn out to be too easy/uniform.
- `hn_client.py`, `remotive_client.py`, and `adzuna_client.py` have no docstrings/comments —
  deliberate, don't flag it again.

Start by checking the current state of the repo in case I've changed things since.

---
