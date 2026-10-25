# Response to the Sahyog Health Network RFP

**Tier delivered:** Core. **Status:** built and evaluated on synthetic data, 25 Oct 2026.

## What Sahyog asked for

Patients who find the right doctor and book in under three minutes without a phone call, and who can question their own records with every answer cited and scoped to their own data; every AI output traceable, auditable and reversible by a named human; a design that runs under the DPDP Act with identified data kept in India (pack p4).

## What we delivered

| Outcome | How it is met | Evidence |
|---|---|---|
| Find a doctor and book without a call | W1: red-flag rules, specialty match against a reviewed crosswalk, shortlist, patient picks, idempotent booking | 20 of 20 simulated sessions booked; red-flag recall 100%; specialty accuracy 88% strict (`evals/report.md`) |
| Question my own records, cited and scoped | W2: consent check, scope and safety rules, retrieval filtered by patient in SQL, cited answer, verification | 0 scope leaks; faithfulness 0.93 by a calibrated judge |
| Traceable, auditable, reversible | Append-only audit of every record read; hand-offs to named roles; a trace id on every model call in the spend ledger; erasure and consent withdrawal (CR-001) | ADR 0008; audit tests |
| DPDP and residency | Identifiers tokenised before any model call; token map stays local; erasure of uploads | ADR 0006, ADR 0008 |

## What is not in this tier

The consultation scribe (W3), deployment ADR and threat model (D6, D7), and load testing at 1,400 requests an hour belong to the Pro and Architect tiers.

## Cost

Model cost per consultation (one booking and one record question): see `docs/cost-sheet.md`, computed from the spend ledger with the price list recorded on each call.

## Assumptions that need the client

The D2 questions had no client answers, so each is closed as a working assumption with a validation and a fallback in `docs/assumptions.md` (A01 to A15). The ones that most change the design: who owns incidents (A03), consent defaults (A05), and how long hospital-issued reports must be kept (A15).
