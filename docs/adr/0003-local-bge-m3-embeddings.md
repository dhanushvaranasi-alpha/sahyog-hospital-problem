# ADR 0003 — Local BGE-M3 embeddings

```yaml
title: Report chunks are embedded locally with BAAI/bge-m3 (1,024 dimensions)
context: The pack sizes the vector index for a 1,024-dimension model (p22). Report chunks are clinical content: they may leave the boundary only de-identified (p21). Hindi and Marathi follow English (p4). The LLM budget is US$4.
options:
  - name: Hosted embedding API via OpenRouter or a vendor
    cost: No model download and fast, but every chunk must be scrubbed before it leaves, and embedding spend comes out of the budget
  - name: Local BGE-M3
    cost: 2.27 GB download and slower ingest on CPU; no egress for embedding and no API cost; multilingual; MIT licence
  - name: A small local English model (e.g. 384 dimensions)
    cost: Fast and light, but breaks the pack's sizing and is weak on Hindi-English text
decision: Local BGE-M3, dense vectors only, stored in pgvector as vector(1024). Revisit if ingest misses the 60-second target on the laptop (assumption A12).
consequences: Embeddings are cached by content hash so re-ingest is free. The first run downloads the model. Retrieval quality is measured on the W2 set before any change of model.
versions_pinned: sentence-transformers == 6.2.0; pgvector == 0.5.1; image pgvector/pgvector:0.8.7-pg18-trixie
checked_on: 2026-10-24
status: accepted
```

Facts checked on 24 Oct 2026: `hidden_size` 1024 in the model's config.json, MIT licence and 2.27 GB `pytorch_model.bin` on the Hugging Face model page.
