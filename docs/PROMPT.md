# Session state

Volatile half only — where the work stands right now. The stable half (project brief, working
style, conventions, environment gotchas) lives in `CLAUDE.md` and loads automatically; don't paste
it and don't duplicate it back here.

Paste this to start the next session:

---

**Where we left off (2026-08-17).** Phase 1 is closed. Phase 2's extraction path is **wired end to
end and verified** on one row per source — `source_adapters` → LLM → `schema` validators →
`transform` → `NormalizedRole` (four modules, committed in `a0cabb9`).

**This session: testing got unblocked.** pytest added as a dev dependency,
`[tool.pytest.ini_options]` added (`testpaths`, and `pythonpath = ["."]` — without it `import src`
fails at collection because nothing is installed), and `tests/test_normalize.py` written: **83
parametrized cases over all ten public functions** in `normalize.py`. Uncommitted. Gate is green —
`uv run ruff check src/ evals/ tests/ && uv run mypy src/ tests/ && uv run pytest -q`.

**Next up:** tests for `schema.py` / `transform.py` → settle the labeling questions → hand-label
`evals/gold_labeled.json` → eval script → extraction pipeline module with the retry loop →
Langfuse. `source_adapters.py` tests want the offline fixtures, so those two land together.

**Two loose ends before committing.** `tests/test_experiment.ipynb` is a notebook sitting in
`tests/` — notebooks are `experiments/` material, and `.gitignore` covers `experiments/*` but not
this. And `CLAUDE.md` is still untracked.

**Settle the labeling questions in ROADMAP "Still open" before labeling** — each decides what a
correct label *is*, and relabeling 40 rows twice is the expensive mistake here. Short version:
`stack` ground truth barely intersects extracted stack; card fields contradict body prose on Habr
and Remotive; `location` has no normalizer; a quote for a `None` field goes unchecked. Two
`normalize.py` holes are pinned by tests as *current* behaviour and logged in the same section; a
third (`"team lead"` leaking into `stack`) was closed this session by extending `STACK_STOPLIST`.

Two things that will bite the eval script specifically:

- **Containment runs against `html_to_text(raw_text)`, never `raw_text`** — and must whitespace-
  normalize both sides, because source prose is hard-wrapped mid-sentence. `test_html_to_text`
  guards the inline-markup half of this (a quote spanning `<strong>` must not split); the
  whitespace half belongs to the eval script and is still unwritten.
- **Only Habr's salary has a known period.** Web3 and Remotive amounts stay unconverted in
  `salary_raw`; skip salary scoring there rather than guessing a period.

Start by checking the current state of the repo in case I've changed things since.

---
