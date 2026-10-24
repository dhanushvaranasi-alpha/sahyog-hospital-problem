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
