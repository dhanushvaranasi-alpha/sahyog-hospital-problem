# AI-collaboration log

One entry per pull request: what the AI assistant proposed, what I rejected, and why (pack p38, p49).

**Assistant used:** Claude (Anthropic), in Cowork, working on my machine's repository. I review every diff before committing.

---

## PR #1 — PRD-lite and proposed architecture

**Branch:** `docs/prd-and-architecture`
**Date:** 24 Oct 2026

### What the assistant proposed

- `docs/prd-lite.md`: personas, journeys with failure paths, epics broken into user stories with testable acceptance criteria, each citing the pack page or RFP addendum line behind it.
- `docs/architecture.md`: Core-tier context, container and graph views, and 20 decisions with versions it checked on PyPI, Hugging Face and OpenRouter on 24 Oct 2026.
- An LLM budget estimate for the Core build (about US$0.75 of a US$4 key), with the formula.
- Pinning `langgraph` 1.2.16 rather than 1.2.17, which was released on the day of the check. Accepted.
- Local BGE-M3 for embeddings (1,024 dimensions, MIT licence, runs locally). Accepted.
- 30 eval cases per workflow, 100 synthetic report PDFs, a signed-token auth stub, and a US$2.00 budget hard stop. Accepted.

### What I rejected, and why

| # | Assistant's proposal | My decision | Why |
|---|---|---|---|
| 1 | Langfuse Cloud for tracing | Overruled: LangSmith | I asked why not LangSmith: native LangGraph integration through environment variables only, less setup. Residency caveat recorded in architecture decision 10 |
| 2 | A direct vendor API (Anthropic, OpenAI or Gemini) or a local model | Overruled: OpenRouter with a US$4 cap | One OpenAI-compatible interface, so the vendor is swappable by config, which demonstrates the "swappable vendor" constraint. The cap led to the budget guard (decision 15) and a Haiku-class model |
| 3 | Ingest as a FastAPI background task with a job table; a real queue deferred to Pro | Overruled: Redis + RQ worker now | Matches the pack's container view and keeps ingest off the API process. Redis also serves the 30-second slot cache, removing one difference from the pack |
| 4 | Claude Haiku 5.5 as the primary model, GPT-6 Luna as fallback | Overruled: run the W1 eval set on both and pick on specialty accuracy | Same price, so quality should decide, and a measured comparison is defensible where an assumed one is not. Costs about US$0.02 |
| 5 | Skip the calibrated faithfulness judge to save time; report deterministic citation checks instead | Overruled: build the judge, calibrated on 20 hand-graded answers | The p16 target names a calibrated judge, and evaluation carries 25% of the score |

---

## PR #2 — Scaffold, data tier and discovery deliverables

**Branch:** `feat/scaffold-and-discovery`
**Date:** 24 Oct 2026

### What the assistant proposed

- Repository layout from pack p48, with placeholders for each folder.
- `infra/docker-compose.yml` with Postgres + pgvector and Redis, image tags checked against the pgvector README and Docker's official-images list on 24 Oct 2026, and an init script that enables the `vector` extension.
- `pyproject.toml` with every dependency pinned and the set resolved on Python 3.12 with `uv pip compile`.
- D1 `docs/task-cards.md`: the 12 client tasks plus 6 found in discovery, each on a rung with all template fields filled.
- D2 `docs/discovery-questions.md`: 10 questions, 3 from the pack, each tied to the decision it unlocks.
- D3 `docs/assumptions.md`: 14 assumptions with owner, validation and fallback; A01–A10 close the D2 questions in place of client answers.
- ADRs 0001–0003 (LLM access, ingest queue, embeddings) and an ADR index.

### What I rejected, and why

| # | Assistant's proposal | My decision | Why |
|---|---|---|---|
| 1 | Pin `openai==3.37.0`, the newest release | Rejected: pinned `openai==2.54.0` | The dependency check failed: `ragas` 0.4.3 depends on `instructor`, which requires `openai` below 3. 2.54.0 is the newest 2.x and the full set resolves |
| 2 | A `pyproject.toml` without a build-system section | Rejected: added `[build-system]` and `packages = []` | A dry-run install failed on setuptools auto-discovery because the repo has several top-level folders; the project installs dependencies only |

---

## PR #3 — Data estate: inventory, cleaning with tests, schema and loader

**Branch:** `feat/data-estate`
**Date:** 24 Oct 2026

### What the assistant proposed

- `data/fetch_datasets.sh`: one command that downloads the five Kaggle datasets and their metadata, and writes SHA-256 checksums.
- One cleaning module per source with a tally of every dropped row and its reason, after profiling the real files against the pack's list of known problems (p19). Where the data differed from the pack, the code follows the data: prices were already numeric, a regex parses 100% of pack sizes (no LLM fallback needed), and there were no discharge-before-admission rows; it also found 4,616 duplicate rows in Disease-Symptom and 2,611 duplicate transcriptions that the pack does not mention.
- Reference data: 28 fictional sites (6 hospitals, 22 clinics), 33 specialties derived from the data rather than the pack's figure of 38, and a 41-row condition-to-specialty crosswalk drafted by the assistant for human review.
- `infra/db/init/002-schema.sql`: 21 tables, including a partial unique index that allows one live booking per slot, a unique idempotency key, a denormalised `patient_id` on chunks so the scope filter runs in SQL, and a trigger that makes `audit_event` append-only.
- `data/load.py` (idempotent) and `data/build_inventory.py`; 31 tests across transforms, reference data, real data and the database.
- Deferring the Presidio scrub of transcriptions to the egress scrubber (PR #6), since the notes are only seed text.
- A second-pass review of its own crosswalk draft, which changed two rows: Hypoglycaemia marked as an emergency condition (severe cases are life-threatening and red-flag recall must be 100%), and urinary tract infection routed to General Medicine first with Urology as the alternative (most first episodes are treated in primary care). I then reviewed all 41 rows and approved them; the reviewer mark is mine.

### What I rejected, and why

| # | Assistant's proposal | My decision | Why |
|---|---|---|---|
| 1 | De-duplicate transcriptions on the raw text, then repair the layout | Rejected after the real-data test failed: repair first, then de-duplicate | Some copies differ only in spacing; after repair they became identical, so duplicates slipped through |
| 2 | Keep symptom severity as produced by the merge | Rejected after the load failed on "3.0": cast to a nullable integer | The merge turned the column into floats, which Postgres refused for an integer column |
| 3 | Treat only `None`, `NaN` and `NaT` as missing in the loader | Rejected after the load failed on `pd.NA`: map every pandas missing marker to NULL | pandas 3 uses `pd.NA` in nullable columns, which psycopg cannot adapt |
| 4 | Read the licence from the top level of Kaggle's `dataset-metadata.json` | Rejected after the inventory showed "not stated" for all five sources: read it from the `info` block | `kaggle datasets metadata` nests the fields under `info`; the licences were CC BY-NC-SA 4.0, CC BY-SA 4.0 (×2) and CC0 (×2) |

---

## PR #4 — Synthetic layer, D4 data contracts and D5 sizing

**Branch:** `feat/synthetic-data`
**Date:** 24 Oct 2026

### What the assistant proposed

- `services/common/llm.py`: one model client for every call, with schema validation (reject, never repair), a timeout, a fallback model, prices fetched from OpenRouter at run time, and an append-only spend ledger with a US$2.00 hard stop.
- Doctors: code decides specialty and clinic (at least ten per specialty, every site staffed); the LLM writes only names, gender, languages and years, in 10 batches of 50 against a versioned prompt.
- Patients (1,000) and slots (96,000) by plain code, including the two personas and Priya's caregiver consent for her mother.
- 100 report PDFs: the LLM rewrites a cleaned transcription as a report, code adds the identifying header and renders the PDF.
- D4: 21 data contracts on the pack's template, one per table, generated from one spec. D5: sizing from measured counts, with the pack's three checks.
- Estimated LLM cost for this PR: about US$0.13.

### What I rejected, and why

| # | Assistant's proposal | My decision | Why |
|---|---|---|---|
| 1 | Accept the 500 generated doctors as returned | Rejected after the audit test found 29 repeated names: reject the later copies and regenerate them with the taken names listed | Batches of 50 cannot see each other's names; the pack asks for a duplicate audit |
| 2 | JSON schemas without `additionalProperties: false` | Rejected after the fallback model refused every call: close every schema, then smoke-test the fallback | OpenAI-family providers require closed schemas; a fallback that was never called was not a fallback (p36) |
| 3 | 1,800 output tokens per report | Rejected after replies were cut off mid-JSON (`finish_reason: length`): 3,500 tokens | Long sources produced truncated, invalid JSON |
| 4 | Choose report sources by their transcription label | Rejected after the first 100 came out 47% cardiology and 3% radiology: classify sources by content (title, lab section) and fix the mix at 40 lab / 35 radiology / 15 cardiology / 10 discharge (assumption A07) | The PR #3 de-duplication keeps the alphabetically first specific label, so most imaging notes carry a clinical label |
| 5 | Random sources for the demo personas | Rejected after Priya's mother drew "MRI Brain – Cryptococcus": persona sources filtered to coherent ones (glucose labs, echocardiogram, chest CT) | The personas carry the demo; their records must fit a 62-year-old diabetic |
| 6 | Prompt `reports_v1` | Rejected after a rendered PDF showed a 62-year-old's report describing "a 40-year-old female": `reports_v2` forbids ages and pronouns, and the schema now rejects them; 51 drafts regenerated | 47 of 100 reports copied the source note's age, contradicting the header |
| 7 | Loader upsert that updates every conflicting row | Rejected after a reload grew the database to 277 MB of dead rows: update only rows that changed | A reload now grows the database by about 1 MB |

Actual LLM spend for this PR: US$0.265 against the US$0.13 estimate. The difference is the regeneration in rows 1, 4 and 6 and retries of replies the schema rejected; every call is in `data/llm_ledger.jsonl`.
