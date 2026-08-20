# Decisions

One entry per locked decision: what was decided, why, and what was rejected. Traps live in
GOTCHAS.md; progress lives in ROADMAP.md.

## Schema

### One list, `stack` — undated
`skills` is dropped; synonyms normalized in Python via an alias map (`postgresql|psql → postgres`,
`k8s → kubernetes`), plus a stoplist — the spike emitted `"Open Source"` as a technology.
Rejected: normalizing in the prompt, which makes set-F1 punish the model for spelling.

### Salary stored monthly — undated
The LLM extracts verbatim (`amount`, `period`, `currency`); Python converts `year ÷ 12`,
`hour × 173.33` (2080/12 — pin the constant). Currencies are **not** converted.
Rejected: storing the derived figure in `source_quotes["salary"]` — unquotable by construction, and
it would fail every containment check.

### Multi-role postings split into one record per role — undated
Of the 10 original HN gold rows, 4 were clearly multi-role, 2 ambiguous, 4 single.
`company` is posting-level; `title`/`seniority` are role-level; the rest inherit-with-override.
Rejected: one record per posting, which cannot represent per-role location, type or salary.

### Two Pydantic models, verbatim and normalized — undated
`RoleExtraction` (what the LLM emitted) → `normalize()` → the stored shape. Enum-shaped fields stay
free strings on the verbatim layer.
Why: keeps *model misread the posting* and *my `÷12` has a bug* separately measurable.

### Don't split on location — undated
One system-engineer role hiring in Sydney *and* Brisbane is one role.
Why: without an explicit prompt rule this yields two spurious roles.

### Salary is a fifth inheritable field group — locked 2026-08-16
HN `49157647` states a posting-level band *and* per-role overrides (`senior band $170K-$210K`), so
`INHERITABLE_FIELDS` is eight names, salary's four among them.
Rejected: salary as posting-only.

### `stack` unions on fill-down; the other seven replace — locked 2026-08-16
The one inheritable field that does not behave like the rest — say so in the labeling notes.
Rejected: replacing, which would drop the shared stack for exactly the roles that bothered to list
their own.

### `"salary"` is a legal `source_quotes` key — locked 2026-08-16
The four `salary_*` fields share one verbatim quote, so allowed keys are `model_fields | {"salary"}`.
Why: it is not a field name, and key validation would otherwise reject it.

### `QUOTE_REQUIRED` is deliberately narrow — locked 2026-08-16
Only `title`, `company`, `salary_min`, `salary_max` — the fields where the spike actually fabricated.
Rejected: requiring a quote for every non-null field, which sends the retry loop into a storm over
header tokens nobody quotes cleanly.

### A posting with `roles: []` gets one synthesized role — locked 2026-08-16
It carries the posting-level fields.
Why: `structured_postings` is keyed on the role, so a single-role posting would otherwise normalize
to nothing.

### `ExtractionInput.ground_truth` carries an explicit `held_out` set — locked 2026-08-16
Why: without it "this source has no such field" is indistinguishable from "this source says null",
and the eval punishes correct nulls.

### Only Habr's salary reaches the monthly axis — locked 2026-08-16
`salary_period_known=True` for Habr only. Web3 states amounts with `salary_currency` and
`salary_unit` both `None` in all 8 gold rows; Remotive's `salary` is free text mixing `"$3k - $10k"`
with `"$150k - $230k"`. Both carry amounts unconverted in `salary_raw`.
Rejected: guessing a period — the eval skips salary comparison there instead.

### Eval cannot compare roles positionally — undated
Score role *count* first, then greedy-match predicted↔gold on normalized title, then per-field score
only matched pairs; report unmatched as precision/recall loss.
Rejected: positional comparison, which misscores whenever role order differs.

## Pipeline

### Sequencing — vertical slice first — locked 2026-08-19
Order is now: (1) run extraction as it stands over all 1,098 rows, accept bad output, store it;
(2) embed → pgvector → one working `vector_search`; (3) DeepSeek tool-calling loop, three tools,
FastAPI + SSE; (4) *then* label the gold set against observed retrieval failures.
Rejected: finishing Phase 2 first — three weeks in, nothing in the repo answered a question yet,
with the hardest-to-finish phase sitting in front of the three that demo well.

### Keep `pydantic-ai` — locked 2026-08-19
`Agent(retries=2)` already does validate-and-retry.
Rejected: hand-rolling the manual loop now; it is a Phase 5 exercise, not a blocker.

### `extract` catches transport, never bare `Exception` — locked 2026-08-20
`UnexpectedModelBehavior` → `invalid`; `(AgentRunError, TimeoutError)` → `error`; everything else
propagates and kills the run. `TimeoutError` is named explicitly because `asyncio.wait_for` raises
the builtin, not an `AgentRunError`.
Rejected: `except Exception` — a `TypeError` in our own code was recorded as a DeepSeek failure and
`persist` then claimed the row, which on the full pass would produce 1,098 rows of fake
transport errors (see GOTCHAS: extraction).

### Adapters own source-specific JSON shape — undated
`source_adapters.py` is the only place that knows it, and lives in the extraction pipeline, not the
loader: keeps `raw_postings` lossless, needs no re-ingest, stays a pure function testable off a
fixture.
Rejected: letting the eval script re-parse `raw_text` — the two drift and the scores stop meaning
anything.

### Classify non-postings in the extraction layer, never filter at ingest — locked 2026-08-13
`doc_type: Literal["posting", "candidate", "other"]` on the schema, plus a hard prefilter in the HN
adapter for the unambiguous cases only (`[flagged]`, `[dead]`, text under ~120 chars). An enum, not
a bool: `candidate` is a coherent class, not noise. Storing it means re-extraction doesn't re-litigate.
Rejected: a header-must-contain-`|` regex — it drops ~35 legitimate free-form postings (Tether,
PrairieLearn, Proton), and a regex's mistakes are invisible where a scored field's surface.

### Every LLM call is traced to Langfuse from the first one — undated
Why: retrofitting tracing after a full corpus pass loses the run it would have explained.

## Storage

### `structured_postings` is 1:N with `raw_postings` — undated
Keyed `role_index` with a unique `(raw_posting_id, role_index)`. Phase 3 embeddings key on the
**role** row, not the raw posting.
Rejected: 1:1 — re-extraction duplicates rows instead of updating them.

### Two tables: `structured_postings` + `extraction_runs` — locked 2026-08-19
`structured_postings` is 1:N keyed `role_index`; `extraction_runs` is 1:1 with `raw_postings` and
carries coverage — status, `doc_type`, model, error.
Why: when `doc_type != "posting"` roles is empty, so a successful non-posting writes zero role rows
and is otherwise indistinguishable from a row never attempted.

### Embeddings are `bge-m3` via Ollama at `vector(1024)` — locked 2026-08-20
42% of the corpus is Russian (460 Habr rows). Measured RU/EN paraphrase cosine 0.824 on the local
instance; `bge-small-en-v1.5` is English-only and would embed those as noise. Second reason: 8192
token context vs 512, and job descriptions routinely exceed 512.
Rejected: `BAAI/bge-small-en-v1.5` at 384-dim — English-only, and adds a torch dependency Ollama
already makes unnecessary. Re-embedding 1,098 rows is minutes, so this is not a one-way door.

### Don't put embeddings in the snapshot — undated
Snapshot the tables and regenerate embeddings on restore.
Why: float noise that won't compress, and regenerating makes the eval DB a test of the embedding
pipeline instead of a fossil of it.

### Monthly rollups are the substrate for trends — undated
A rolling 90-day window can't answer "how did Rust demand change over the year". Fix when Phase 3/5
need it: skill frequency and salary percentiles into an aggregate table the purge doesn't touch.
Why: aggregates aren't postings, so the retention rule shouldn't reach them.

### Inputs live in the dump, labels live in git — undated
Why: labels get revised as the schema firms up, and those revisions must be reviewable diffs, which
they are not inside a binary dump.

## Labeling

### Label late, against observed retrieval failures — locked 2026-08-19
Hand-labeling waits until the slice runs end to end.
Why: the list of failures that actually degraded retrieval is far shorter than the one invented up
front, and relabeling 40 rows twice is the expensive mistake.

### Habr labeling language — locked, undated
Normalize the enums, not the whole record: `seniority` → English enum (195 rows senior/синьор, 160
middle/миддл, 82 lead/ведущий/тимлид, 38 junior/стажёр); `stack` needs no translation layer (190
rows Latin vs 1 Cyrillic; PostgreSQL 128 Latin vs 0); `title` and `source_quotes` stay verbatim
Russian. Rejected: translating quotes — containment runs against the adapter's cleaned text, so
every Habr row would fail for a reason unrelated to extraction quality.

## Open

- **Is `stack` scored against card tags at all, or only against hand labels?** Habr `1000162782`
  normalizes to `['waterfall']` against 14 extracted acronyms; Web3 `150580` to
  `['erc-20','smart-contract']` against 19. Set-F1 is near zero and the extraction isn't wrong.
- **Which wins when a card field contradicts body prose?** Habr `1000162782` card says
  `remoteWork=True`, prose says hybrid; card company `ИТ-Холдинг Т1` vs extracted `Т1`. Remotive
  `2090949` card title vs the body's own `Account Executive / B2B Sales Specialist`. One tiebreak
  rule, written into *both* the prompt and the labeling notes.
- **Which wins when a header contradicts the body?** One spike posting's header said `Onsite` while
  its body said 3 days/week in office (the spike chose hybrid — the better read).
- **Should `location` get a normalizer?** HN roles came out with `location="REMOTE (worldwide)"` — a
  remote policy sitting in the location field. Free text with junk in it.
- **Should a quote for a `None` field be rejected?** A role emitted `source_quotes["employment_type"]`
  while leaving the field `None`; both validators pass it. A sixth check (quote keys ⊆ non-null
  fields) would catch it.
- **How much placement variance does the eval tolerate?** Two runs of the same posting put `stack` at
  posting level once and role level the next. Fill-down absorbs it; role-count variance is noise.
- **Compound seniority:** `"Mid-Senior/Senior"` (HN `48749201`) matches no alias key and falls to
  `unknown`. Add compound keys, or rule that a range rounds up?
- **Two `normalize.py` holes are pinned by tests as *current* behaviour, not correct behaviour** —
  each test says so; update it when the rule changes. `fold_homoglyphs("РОСТ") == "POCT"` (a real
  Russian word fully Latinizes; not reachable from the current corpus) and
  `currency_enum("xyz") == "XYZ"` (the length-3 ASCII passthrough can't tell a currency from any
  other three-letter string).
- **Can `doc_type` be scored at all?** The gold set contains zero non-postings. Add 2–3 known junk
  ids as a deliberate hand-picked group, or accept the field is unmeasured. `EXCLUDED_HN` stays
  regardless.
