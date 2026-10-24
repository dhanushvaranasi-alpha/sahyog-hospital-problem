# Sahyog Care Companion

An agentic patient and doctor assistant for Sahyog Health Network (a fictional client from the FDE Academy engagement pack), built on LangGraph, Postgres + pgvector and FastAPI.

**Tier reached:** in progress, targeting Core. **Delivery:** solo.

## What is here so far

| Path | What it is |
|---|---|
| `docs/prd-lite.md` | Personas, journeys, epics and testable acceptance criteria |
| `docs/architecture.md` | Proposed Core-tier architecture and decisions awaiting confirmation |
| `AI-COLLABORATION.md` | One entry per pull request on how the AI assistant was used |
| `.env.example` | Settings to copy into a local, git-ignored `.env` |

## Running it

Not runnable yet. The one-command start (`docker compose up`) arrives with the scaffold pull request.

## Data

All patient, doctor and appointment data is synthetic or drawn from public datasets listed in `data/inventory.md` (to come). No real identified health data is used anywhere in this repository.
