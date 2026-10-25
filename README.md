# Sahyog Care Companion

An agentic patient and doctor assistant for Sahyog Health Network (a fictional client from the FDE Academy engagement pack), built on LangGraph, Postgres + pgvector and FastAPI.

**Tier reached:** in progress, targeting Core. **Delivery:** solo.

## Quick start

Requires Docker Desktop and Python 3.12.

```sh
cp .env.example .env            # then add your keys locally; .env is git-ignored
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
docker compose -f infra/docker-compose.yml up -d --build   # Postgres + pgvector, Redis, API on :8000, ingest worker
```

The data steps below fill the database; the API and worker read the same `data/` folder through a mount.

## Data estate

```sh
bash data/fetch_datasets.sh        # needs a Kaggle token in ~/.kaggle/access_token; writes data/raw/ (git-ignored)
python -m data.transforms.run      # clean each source -> data/processed/ with a tally of every dropped row
python -m data.load                # schema + reference data + cleaned history -> Postgres
python -m data.build_inventory     # regenerate data/inventory.md
python -m pytest                   # transform, reference, real-data and database tests
```

## Synthetic layer

```sh
python -m data.synthetic.doctors          # 500 doctors (LLM names; resumes; ~US$0.03)
python -m data.synthetic.reports          # 100 report drafts (LLM; resumes; ~US$0.10)
python -m data.synthetic.reports --render # 100 PDFs into data/synthetic/output/pdfs/ (git-ignored)
python -m data.synthetic.load             # doctors, patients, slots and the persona consent -> Postgres
python -m data.build_contracts            # regenerate docs/data-contracts/
```

The generated JSON (`data/synthetic/output/*.jsonl`) and the spend ledger (`data/llm_ledger.jsonl`) are committed, so nobody has to pay to regenerate them.

## Repository map

| Path | What it is |
|---|---|
| `docs/prd-lite.md` | Personas, journeys, epics and testable acceptance criteria |
| `docs/architecture.md` | Core-tier architecture and the 20 decisions |
| `docs/adr/` | Architecture decision records |
| `docs/task-cards.md` | D1 automation ladder: 18 tasks, each on a rung |
| `docs/discovery-questions.md` | D2 discovery questions and the decision each unlocks |
| `docs/assumptions.md` | D3 assumptions register: owner, validation, fallback |
| `docs/data-contracts/` | D4 data contracts, one per table |
| `docs/data-sizing.md` | D5 sizing and the three "is there enough data" checks |
| `data/` | Download script, transforms with tests, reference data, loader, inventory |
| `services/` | agent (LangGraph graphs), scheduling, records, scribe |
| `evals/` | Eval sets, runs and the report |
| `infra/` | docker-compose and database init |
| `memo/` | Executive memo |
| `AI-COLLABORATION.md` | One entry per pull request on how the AI assistant was used |

## W1 Find my doctor

`services/agent/w1/`: red-flag rules, then one model call to match a specialty against the reviewed crosswalk, then a shortlist of three doctors with their next free slot, an `interrupt()` while the patient picks, and an idempotent booking. Red flags leave the graph for a human; two unclear turns go to the front desk; a model failure degrades to the front desk.

```sh
python -m evals.run_w1 --model anthropic/claude-haiku-5.5   # score the 30 W1 cases (~US$0.01 a run)
python -m pytest services                             # graph paths, rules, Postgres booking
```

## W2 My records

`services/records/` and `services/agent/w2/`: report PDFs are parsed, identifiers replaced by tokens, instruction-like sentences removed, chunked by section and embedded locally with BGE-M3 (ONNX Runtime) on the RQ worker. A question passes a consent check (own records, or a valid consent row), scope and safety rules, then retrieval restricted to that patient in SQL, one cited answer and a verification step. Every document read is written to the append-only audit table.

```sh
python -m spacy download en_core_web_lg            # name detection in typed questions (ADR 0006)
python -m data.load                                # applies infra/db/init/003-records.sql
python -m services.records.ingest --synthetic      # index the 100 reports (first run downloads BGE-M3, ~2.3 GB)
rq worker ingest --url $REDIS_URL                  # worker for uploads (macOS: --worker-class rq.SimpleWorker)
python -m evals.run_w2 --model anthropic/claude-haiku-5.5   # score the 30 W2 cases (~US$0.005 a run)
```

## API

`services/api/`: FastAPI gateway. Identity comes only from a signed bearer token (role, user id, patient id), never from the request body. Per-caller rate limits (Redis, one-minute window), a request id echoed in `X-Request-ID` and used as the trace id in audit rows. W1 sessions survive restarts through the Postgres checkpointer.

| Method and path | What it does |
|---|---|
| `POST /v1/w1/sessions` | Start "find my doctor"; returns a clarifying question, slot options, or an emergency/front-desk hand-off |
| `POST /v1/w1/sessions/{id}/reply` | Answer the question, or pick a slot with an idempotency key; only the patient who started the session |
| `POST /v1/w2/questions` | Ask about your records, or a consenting relative's (`subject_patient_id`) |
| `POST /v1/w2/uploads` | Upload a PDF report (max 10 MB); returns a job id at once; the worker ingests it |
| `GET /v1/w2/uploads/{job_id}` | Ingest status, shown only to the uploader |
| `GET /health` | Postgres and Redis reachability |

```sh
TOKEN=$(python -m services.api.auth --sub P-PRIYA)        # development token, 1 hour
curl -s localhost:8000/v1/w2/questions -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
     -d '{"question": "What did my mother'"'"'s echocardiogram show?", "subject_patient_id": "P-SUNITA"}'
```

Interactive docs at `http://localhost:8000/docs`.

## Evaluation sets

Written before any graph code: 30 cases for W1 (find my doctor) and 30 for W2 (my records), plus a red-team PDF. See `evals/README.md` for what each case checks and how it is scored.

```sh
python -m evals.redteam.make_redteam_pdf   # rebuild the red-team PDF (committed)
python -m pytest evals                     # the sets are tested too: valid, grounded, passable
```

## Data

All patient, doctor and appointment data is synthetic or drawn from public datasets listed in `data/inventory.md` (to come). No real identified health data is used anywhere in this repository.
