# ADR 0001 — LLM access through OpenRouter, primary model chosen by measurement

```yaml
title: All model calls go through OpenRouter behind one ModelClient interface; the primary model is picked by eval results
context: The client requires the LLM vendor to be swappable without a rewrite (p4) and only de-identified text may leave the boundary (p5). The engagement has a single API key with a US$4 budget.
options:
  - name: One vendor's API directly (e.g. Anthropic or OpenAI SDK)
    cost: Simplest calls, but a vendor switch means a second SDK and new code paths; a fallback provider needs a second key and budget
  - name: OpenRouter through an OpenAI-compatible client
    cost: One key and one client for every vendor; adds a routing intermediary to the data path, acceptable only because text is scrubbed first
  - name: Local model only (no egress)
    cost: Strongest residency, but slower on a laptop and below hosted quality for triage and answers; risks the 85% specialty target
decision: OpenRouter behind a ModelClient interface. Candidates anthropic/claude-haiku-5.5 and openai/gpt-6-luna (both US$0.10 / 1M input, US$0.50 / 1M output on 24 Oct 2026). Run the W1 eval set on both; the higher specialty accuracy becomes primary and the other the fallback. Red-flag recall must be 100% on both. Revisit if the primary falls below 85% specialty accuracy or residency terms change.
consequences: Every call passes the egress scrubber first. Model ids live in configuration, never in graph code. A cost meter with a US$2.00 hard stop guards the key. The router's own retention terms must be checked before any real deployment.
versions_pinned: openai == 2.54.0 (client); langsmith == 0.14.12
checked_on: 2026-10-24
status: accepted
```

Note on the client pin: `openai` 3.x is current, but `ragas` 0.4.3 depends on `instructor`, which requires `openai` below 3. 2.54.0 is the newest 2.x and resolves cleanly on Python 3.12.
