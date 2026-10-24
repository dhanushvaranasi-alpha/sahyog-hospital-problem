# Sahyog Care Companion

An agentic patient and doctor assistant for Sahyog Health Network (a fictional client from the FDE Academy engagement pack), built on LangGraph, Postgres + pgvector and FastAPI.

**Tier reached:** in progress, targeting Core. **Delivery:** solo.

## Quick start

Requires Docker Desktop and Python 3.12.

```sh
cp .env.example .env            # then add your keys locally; .env is git-ignored
docker compose -f infra/docker-compose.yml up -d   # Postgres + pgvector, Redis
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Services, the worker and the graphs join the compose file as they are built.

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

## Evaluation sets

Written before any graph code: 30 cases for W1 (find my doctor) and 30 for W2 (my records), plus a red-team PDF. See `evals/README.md` for what each case checks and how it is scored.

```sh
python -m evals.redteam.make_redteam_pdf   # rebuild the red-team PDF (committed)
python -m pytest evals                     # the sets are tested too: valid, grounded, passable
```

## Data

All patient, doctor and appointment data is synthetic or drawn from public datasets listed in `data/inventory.md` (to come). No real identified health data is used anywhere in this repository.
