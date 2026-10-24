# ADR 0004 — Claude Haiku 5.5 primary, GPT-6 Luna fallback, chosen by the W1 eval

```yaml
title: anthropic/claude-haiku-5.5 is the primary model and openai/gpt-6-luna the fallback, on measured W1 accuracy AND latency
context: Both candidates cost US$0.10 / 1M input and US$0.50 / 1M output on OpenRouter (24 Oct 2026). Architecture decision 6 said the primary is chosen by measurement on the W1 eval set, not assumed. The client's targets are strict specialty accuracy of at least 85% and p95 triage latency under 4 s (pack p16).
options:
  - name: Claude Haiku 5.5 primary
    cost: Strict accuracy 88.2% in all 3 runs; red-flag recall 100%; p95 3.2 s, 2.9 s, 2.9 s (meets the target every run); US$0.0092 per 30-case run
  - name: GPT-6 Luna primary
    cost: Strict accuracy 94.1% in all 4 runs; red-flag recall 100%; p95 3.4 s, 3.7 s, 4.1 s, 4.4 s (misses the target in half the runs); US$0.0048 per run
  - name: GPT-6 Luna primary with a shorter prompt to cut latency
    cost: More work and more runs with no guarantee of a stable p95 under 4 s; the gain is one ambiguous case
decision: Claude Haiku 5.5 primary, GPT-6 Luna fallback. Revisit if Haiku's strict accuracy drops below 85% on the growing eval set, or its p95 exceeds 3.5 s.
consequences: Both models scored 100% lenient accuracy and got every unambiguous case right; Luna's strict edge is one deliberately ambiguous case (w1-029, either Rheumatology or Dermatology is acceptable). Haiku costs about US$0.0044 more per eval run, which is negligible against the budget.
versions_pinned: openai == 2.54.0
checked_on: 2026-10-24
status: accepted
```

## How the decision changed

1. After two runs each, GPT-6 Luna was chosen on strict accuracy (94.1% vs 88.2%) at half the cost.
2. A third Luna run, made from the delivery lead's own terminal, showed p95 4.13 s, above the 4 s target. The first suspect, the price-list fetch landing inside the first patient's turn, was fixed (prices now load when the client starts), but the next Luna run still measured 4.43 s: the variance is in the model calls themselves.
3. The revisit trigger written into the first version of this ADR ("p95 approaches 4 s") had fired, so the choice was reopened and Haiku became primary. Same day, same eval set, all seven runs committed.

Evidence: `evals/runs/w1_claude-haiku-5.5_*.json` (3 runs) and `evals/runs/w1_gpt-6-luna_*.json` (4 runs).
