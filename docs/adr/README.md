# Architecture decision records

Template fields follow pack p53: title, context, options (three, with costs), decision with the trigger to revisit, consequences, versions pinned, date checked, status. The steering review walks through this log (house rule 9).

The full list of 20 decisions is in `docs/architecture.md` section 4. Decisions that carry a real trade-off get their own record here.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-llm-access-via-openrouter.md) | LLM access through OpenRouter, primary model chosen by measurement | accepted |
| [0002](0002-ingest-on-redis-rq-worker.md) | Report ingest on a Redis + RQ worker | accepted |
| [0003](0003-local-bge-m3-embeddings.md) | Local BGE-M3 embeddings | accepted |
| [0004](0004-primary-model-by-measurement.md) | Claude Haiku 5.5 primary, GPT-6 Luna fallback, chosen by the W1 eval (accuracy and latency) | accepted |
| [0005](0005-bge-m3-on-onnx-runtime.md) | BGE-M3 on ONNX Runtime instead of PyTorch | accepted |
| [0006](0006-phi-tagging-layers.md) | PHI tagging layers: name NER on typed questions only | accepted |
