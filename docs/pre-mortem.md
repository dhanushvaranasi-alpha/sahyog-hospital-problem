# Pre-mortem

Six ways this build could fail, with the signal, the detection built and the response (pack p44). The pack asks for this on day 5, before the first node; it was written late, on 25 Oct 2026, after W1 and W2 were built, so it is reread here against what the runs actually showed rather than used as a plan.

| Failure | Early signal | Detection built | Response | What happened in this build |
|---|---|---|---|---|
| A patient sees another patient's record | A citation to a report outside the caller's record | Patient filter in the SQL; every citation must be a retrieved report; consent read on every call; red-team PDF in the eval set | Block the answer, audit, review the filter | 0 scope leaks in 3 W2 runs; the red-team PDF's 5 instruction sentences removed at ingest |
| An answer states something the report does not say | A number or claim absent from the excerpts | Number check in the verify step; calibrated faithfulness judge on eval runs | Answer "not in record"; add the case to the eval set | **Happened once without the deterministic signal firing:** G14 gave a wrong report date with every number correct; only the judge and the human grade caught it |
| A red flag is missed | An emergency routed to a routine slot | Rules before any model call; recall on every W1 run | Stop the release, add the case, widen the rules | 100% recall, 0 false alarms in 7 runs |
| A slot is double-booked | Two live appointments on one slot | Partial unique index; idempotency key; retry test | Front-desk override | Not seen; the Postgres test proves the second booking is refused |
| Cost runs away | Spend per run climbing | Ledger on every call; US$2.00 hard stop | Route to a smaller model; cap turns | US$0.44 spent in total; per-run cost flat (about US$0.01) |
| Latency drifts past target | p95 per run | p95 reported by every eval run | Change model or cut prompt size | GPT-6 Luna missed the 4 s triage p95 in 2 of 4 runs, so the primary changed (ADR 0004); W2 p95 rose from 2.3 s to 4.3 s on one run, still under 8 s |

The pack's sixth row, "doctors ignore the drafts", belongs to W3 (Pro) and is out of scope here.

## Findings for the memo

1. The deterministic checks were not enough on their own: a misdated answer passed the number check. The judge earns its place as a second line, never the only gate.
2. Model choice moved on latency, not accuracy: the more accurate model was the slower one on this workload.
