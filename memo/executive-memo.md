# Sahyog Care Companion: executive memo

**On synthetic data, 20 of 20 simulated patients booked a doctor without a phone call, each of the 17 with a reference label in an acceptable specialty; every record answer stayed inside the caller's own records (0 leaks), and the model cost of one booking plus one record question is US$0.0008.** Emergencies never reach a booking screen: red-flag recall is 100% with no false alarms.

## The problem

Sahyog Health Network (fictional; 6 hospitals, 22 clinics) asked for two patient workflows first: find the right doctor and book in under three minutes without calling, and question your own medical records with every answer cited and scoped to your own data. It must run under the DPDP Act, keep identified data in India and keep the model vendor swappable.

## What was built (Core tier)

- **Find my doctor:** emergency rules run before any model call; one small-model call matches the specialty against a reviewed condition-to-specialty crosswalk; the patient picks a slot; booking is idempotent and audited.
- **My records:** uploads are parsed, identifiers replaced by tokens and planted instructions removed before indexing; a question passes a consent check, then retrieval filtered by patient in the database, a cited answer and a verification step.
- **Platform:** signed-token API, rate limits, append-only audit of every record read, and erasure plus consent withdrawal under the DPDP Act (a self-set change request, re-planned with an ADR).

## Results against the client's targets

| Target | Result |
|---|---|
| Red-flag recall 100% | 100% across 7 runs, 0 false alarms |
| Specialty accuracy ≥ 85% | 88% strict, 100% counting the reviewed alternative |
| Bookings without a call ≥ 70% | 100% of 20 simulated sessions |
| Faithfulness ≥ 0.9, calibrated judge | 0.93; judge agreed with the reference on 20 of 20 |
| Scope leaks 0 | 0, including a PDF built to steal another patient's report |
| Triage p95 < 4 s; record answer p95 < 8 s | 2.9–3.2 s; 2.3–4.3 s |

Not yet measured: the patient's own time to book (needs usability sessions), availability, and backup restore. The scribe workflow is the next tier.

## Three decisions that carried the result

1. **Code before model where the rule is known.** Emergencies, consent, scope and dose requests are decided by rules; the model only matches specialties and writes cited answers.
2. **The patient filter lives in the database query, not the prompt.** The red-team PDF's five hidden instructions were removed at ingest, and the filter would have stopped them anyway.
3. **Measure before choosing.** The more accurate model missed the latency target in two of four runs, so the faster one became primary; the answer model and the judge come from different providers.

## Where the AI assistant misled us

It blamed a slow first triage turn on a price-list fetch. We kept its fix, but the next run was still slow (4.43 s p95): the cause was the model's own latency, and the primary model changed because of it. Separately, a model answer gave a wrong report date with every number correct: the deterministic checks passed it and only the calibrated judge and a human grade caught it.

## Next

Confirm the medical-record retention period and incident ownership with the client (assumptions A03, A15); usability sessions for time to book; then the doctor's scribe with sign-off.
