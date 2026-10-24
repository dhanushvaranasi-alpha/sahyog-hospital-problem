# ADR 0004 — GPT-6 Luna primary, Claude Haiku 5.5 fallback, chosen by the W1 eval

```yaml
title: openai/gpt-6-luna is the primary model and anthropic/claude-haiku-5.5 the fallback, on measured W1 results
context: Both candidates cost US$0.10 / 1M input and US$0.50 / 1M output on OpenRouter (24 Oct 2026). Architecture decision 6 said the primary is chosen by specialty accuracy on the W1 eval set rather than assumed. Each model ran the 30-case W1 set twice (evals/runs/w1_*.json).
options:
  - name: Claude Haiku 5.5 primary
    cost: Strict specialty accuracy 88.2% (twice), red-flag recall 100%, p95 2.9-3.2 s, US$0.0092 per run
  - name: GPT-6 Luna primary
    cost: Strict specialty accuracy 94.1% (twice), red-flag recall 100%, p95 3.4-3.7 s, US$0.0048 per run
  - name: Route per step (small model to classify, larger to draft)
    cost: Not needed at Core; W1 has one model step. Revisit for W2 answers and W3 drafting
decision: GPT-6 Luna primary, Claude Haiku 5.5 fallback. Revisit if strict specialty accuracy drops below 85% on the growing eval set, or if p95 triage latency approaches 4 s.
consequences: Both models scored 100% lenient accuracy and got every unambiguous case right; the strict difference is one deliberately ambiguous case (w1-029, joint pain with skin patches, Rheumatology or Dermatology both acceptable). The choice therefore rests on that case plus half the cost, not on a large quality gap, and is stated that way. Luna's p95 is about 0.5 s slower, still inside the 4 s target.
versions_pinned: openai == 2.54.0
checked_on: 2026-10-24
status: accepted
```

Evidence: `evals/runs/w1_gpt-6-luna_*.json` and `evals/runs/w1_claude-haiku-5.5_*.json` (two runs each, identical scores).
