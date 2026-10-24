# PRD-lite: Sahyog Care Companion

| | |
|---|---|
| Client | Sahyog Health Network (fictional): 6 hospitals, 22 clinics, Pune and Hyderabad |
| Engagement | FDE Academy engagement pack, two-week agentic build |
| Delivery | Solo, Core tier first; Pro and Architect items only if time remains |
| Status | Draft for review, version 0.1, 24 Oct 2026 |
| Source of truth | Engagement pack (pages cited as `p<n>` use the pack's footer numbers) |

## 1. Problem

Sahyog's front desk has stopped scaling (p3). The client's own figures, to be verified in discovery:

| Signal | Figure | Business problem it points to |
|---|---|---|
| Bookings still made by phone | 41% | Take the phone out of booking |
| Booked patients who never arrive | 18% | Slot logic and reminders |
| Consultation time spent typing | 11 min | Give the eleven minutes back to the doctor |
| Report PDFs scanned a year | 2.4M | Bring patients to their own records |
| Appointments a day | 9,000 | Plan for peak load |

**What the client wants vs what it needs.** The RFP asks for "an AI assistant". What it needs is a system where every AI output is traceable, scoped to the right person, and reversible by a named human, so that the CMO, compliance officer and doctors will let it run (p4, p7).

## 2. Goals and non-goals

### Outcomes the client is buying (p4)

1. A patient finds the right doctor and books in under three minutes without a phone call.
2. A patient sees and questions their own records; every answer is cited and scoped to their own data.
3. A doctor leaves each consultation with a signed note after at most ninety seconds of review. *(Pro tier)*
4. Every AI output is traceable, auditable and reversible by a named human.
5. The design runs under the DPDP Act and is ABDM-ready, with a path to on-premise handling of identified data.

### Out of scope (p4)

- Billing and insurance adjudication
- Telemedicine video and wearable data
- Inpatient workflows (offered later as extensions only)

A feature that serves no persona in section 3 is scope creep (p11).

## 3. Personas (p11)

| Persona | Role | Needs | Fears |
|---|---|---|---|
| Priya, 34 | Patient, also manages her mother's care | The right specialist tonight, and yesterday's report in plain words | Her mother's reports read by someone who should not see them |
| Meena | Front desk lead, 300 calls a day | Fewer calls about which doctor to see, and a queue she still controls | A bot that books the wrong slot and sends the patient to her counter |
| Dr. Rao | Cardiologist, 22 patients a day | A note he can sign in 90 seconds without re-reading the transcript | Being on record for a line the model invented |
| Imran | Pharmacist, two counters | Prescriptions that match stock before the patient walks over | Substitutions decided by software instead of by him |
| Kavita | Compliance officer | To answer "who saw this record" with one query | Identified health data in a public API log |

Stakeholders missing from the RFP, to be added to the stakeholder map: Finance (signs the invoice) and the nursing lead (owns the inpatient extension) (p7).

## 4. Requirements from the RFP addendum (p5)

Each addendum answer is a requirement. Design rules below cite the line they come from.

| ID | Client said | Design rule |
|---|---|---|
| AD-1 | The assistant does not diagnose; it routes to a specialty and flags emergencies | A red-flag gate runs before any match; wording guardrails on every patient answer |
| AD-2 | A patient can share records with family through a caregiver role whose consent expires | Consent is a table with scope, grantee and expiry, never a checkbox |
| AD-3 | Consultation audio is processed and deleted within 24 hours; transcript and note are kept | Object store with a lifecycle rule; deletion writes an audit event *(Pro)* |
| AD-4 | Only de-identified text may cross the hospital boundary | A scrubber sits on the egress path; identified text stays in-region |
| AD-5 | Stock arrives as a nightly CSV today, an API in about six months | One stock interface with two adapters; the graph never knows which is live |
| AD-6 | The consulting doctor approves every AI-drafted note; nothing auto-signs | The graph interrupts before persistence; an unsigned note is a draft by schema *(Pro)* |
| AD-7 | 9,000 appointments a day; 1,400 requests an hour at the morning peak | Stateless API, async ingest; load test at peak *(Architect)* |

### Constraints (p4)

- Identified health data never leaves India.
- The LLM vendor must be swappable without a rewrite.
- The hospital system exposes FHIR R4 read-only APIs for demographics and encounters (marked optional in the pack; mocked at Core).
- English first, Hindi and Marathi later: nothing in the schema may assume English.

## 5. User journeys

### J1: Patient, symptoms to booking (p12)

1. Describe symptoms (patient)
2. Red-flag check (Companion, rules first)
3. Specialty and shortlist of three doctors with next free slot (Companion)
4. Pick doctor and slot (patient; the run pauses here)
5. Book and confirm by SMS (systems)

**Failure paths**

- Red flag at step 2: leave the booking path, show emergency guidance, open an emergency-desk ticket, end the run (p14, case A).
- Confidence under 0.6 at step 3: ask one clarifying question; after two low-confidence turns, hand off to the front desk (p14).
- No slot at step 4: offer the alternative specialty or the next available day; never book silently.

### J2: Patient, upload and ask (p12)

6. Upload a report (patient)
7. Ingest and index (systems, asynchronous, visible status)
8. Ask about a report (patient)
9. Answer with citations, or hand off to a doctor (Companion)

**Failure paths**

- Upload rejected at step 6 (not a PDF, unreadable): clear status and reason shown.
- Question about another patient, or outside the patient's records: refuse.
- Request for a diagnosis or a dose: hand off to a doctor.

### J3: Doctor, dictation to signed note *(Pro tier, p13)*

Pre-consult brief, dictate, transcribe and draft SOAP, stock check, review and edit, sign or reject (reject returns to the draft with comments), store and audit, reserve medicines, notify patient.

## 6. Epics and user stories

Acceptance criteria are written so a test can pass or fail them (p15). Tier shows when each story is built.

### E1 Find my doctor (Priya) — Core

| ID | Story | Acceptance criteria | Source |
|---|---|---|---|
| E1-S1 | As Priya, I describe symptoms in free text and get one specialty and three doctors with their next free slot | Returned within 4 s (p95); exactly one specialty and up to three doctors | p15 E1 |
| E1-S2 | As Priya, if the symptoms are an emergency I am told to seek urgent care and a human is alerted | Any red-flag rule ends the flow with emergency guidance and a logged human hand-off; no specialty or slot is shown; red-flag recall 100% on the eval set | AD-1, p14 |
| E1-S3 | As Priya, if my description is unclear I am asked one question rather than given a guess | Confidence < 0.6 triggers one clarifying question; two low-confidence turns hand off to the front desk | p14, p25 |
| E1-S4 | As Priya, I can type in English or mixed Hindi-English | Eval set includes mixed-language cases; specialty accuracy reported separately for them | p10 assumption |

### E2 Book and manage (Priya, Meena) — Core

| ID | Story | Acceptance criteria | Source |
|---|---|---|---|
| E2-S1 | As Priya, I pick a slot and get an SMS confirmation | Booking confirms by SMS (stubbed at Core, logged) | p15 E2 |
| E2-S2 | As Priya, a retried tap never books twice | Booking is idempotent under retries: same idempotency key returns the same appointment_id | p15 E2, p29 |
| E2-S3 | As Meena, I see and can override any booking the assistant made | Front-desk endpoint lists assistant bookings and can cancel or move them; each override is audited | p15 E2 |
| E2-S4 | As Meena, no slot is ever double-booked | Booking and slot lock in one transaction; a unique constraint blocks a second appointment on a single-capacity slot | p44 |

### E3 My records (Priya) — Core

| ID | Story | Acceptance criteria | Source |
|---|---|---|---|
| E3-S1 | As Priya, I upload a text PDF and see its status | Stored against the patient within 60 s with a visible status (job id + status endpoint) | p15 E3 |
| E3-S2 | As Priya, I can give my mother's records to myself as caregiver, for a limited time | Caregiver sees a document only while a consent row (grantee, scope, purpose, expiry) is valid | AD-2, p33 |

### E4 Ask my record (Priya) — Core

| ID | Story | Acceptance criteria | Source |
|---|---|---|---|
| E4-S1 | As Priya, I ask a question about my report and get an answer with its source | Every answer cites the document and page; every citation resolves to a retrieved chunk | p15 E4 |
| E4-S2 | As Priya, nobody else's data can appear in my answers | Patient filter applied in SQL at retrieval; zero scope leaks on the red-team set, including the injected PDF | p15 E4, p34 |
| E4-S3 | As Priya, if I ask for a diagnosis or a dose I am sent to a doctor | Safety check hands off; no diagnosis or dose in any answer | p15 E4 |

### E5 Scribe (Dr. Rao, Imran) — Pro

| ID | Story | Acceptance criteria | Source |
|---|---|---|---|
| E5-S1 | As Dr. Rao, a transcript becomes a SOAP draft I can sign in 90 s | Draft within 20 s (p95) after the transcript; review under 90 s in role-play | p15 E5, p16 |
| E5-S2 | As Dr. Rao, nothing is stored until I sign | Persisted only with the doctor's signature and edit history; reject loops back with comments | AD-6 |
| E5-S3 | As Dr. Rao, the model never fills in a medicine I did not name | Any molecule absent from the transcript is replaced by "[doctor to specify]"; invented molecules = 0 | p28, p44 |
| E5-S4 | As Imran, medicines are flagged against stock | Each medicine line shows stock status and stock age | p15 E5, AD-5 |

### E6 Platform (Kavita) — Core

| ID | Story | Acceptance criteria | Source |
|---|---|---|---|
| E6-S1 | As Kavita, I answer "who saw this record" with one query | Every record read writes an AuditEvent with actor, role, purpose, record, time | p15 E6, p33 |
| E6-S2 | As Kavita, identified data never reaches an external API | Egress scrubber on every outbound LLM call; replay of outbound payloads finds zero identifiers | AD-4, p34 |
| E6-S3 | As Kavita, access follows the matrix | Role checks enforced in the records service per the p33 access matrix; the graph never sees a row the caller may not | p33 |

## 7. Non-functional requirements (p16)

| Requirement | Target | Tier |
|---|---|---|
| Triage turn latency | p95 < 4 s | Core |
| Record answer latency | p95 < 8 s | Core |
| Note draft latency | p95 < 20 s after transcript | Pro |
| Audit | Every record read logged with actor, purpose, time | Core |
| Residency | Identified data stored and processed in India | Core (design), Architect (implemented boundary) |
| Retention | Audio gone within 24 h; audit kept one year | Pro |
| Recovery | Checkpoints survive restarts | Core |
| Availability | 99.5% during clinic hours | Architect |
| Budget (engagement constraint) | LLM spend for the whole build under US$4 | Core |

## 8. Success metrics shown in the demo (p16)

| Metric | Target |
|---|---|
| Bookings completed without a call | ≥ 70% of synthetic sessions |
| Time to book | Median < 3 min |
| Red-flag recall | 100% |
| Specialty accuracy | ≥ 85% on the golden set |
| Answer faithfulness | ≥ 0.9 by a judge calibrated on 20 hand-graded answers |
| Scope leaks | 0 across the red-team set |
| Doctor review time per note | < 90 s *(Pro)* |
| Cost per consultation | Computed, with the formula shown |

A target that is missed stays in the report with the number reached and the reason.

## 9. Release plan by tier (p40)

| Tier | Scope | Done when |
|---|---|---|
| Core | E1, E2, E3, E4, E6; D1–D5; 30 eval cases per workflow; memo and demo | A patient books and asks about a record in the demo, and the red-team PDF fails to leak |
| Pro | + E5; async queue; model routing with fallback; D6, D7; cost sheet from traces | A doctor signs a stock-flagged note in the demo and cost per consultation is shown with its formula |
| Architect | + MCP server; parallel ingest; load test at 1,400 req/h; hybrid ADR implemented | The load test passes under the stated p95s and the ADR survives the steering review |

## 10. Working assumptions in place of client answers

No client answers to the discovery questions are available, so each open point is settled by a working assumption, logged in `docs/assumptions.md` with how it is validated and the fallback if it fails.

| Open point | Working assumption | Source of the question |
|---|---|---|
| Core eval set size | 30 cases per workflow (60 in total), satisfying both p40 and p45 | Pack contradiction |
| Architecture-pack scope at Core | W1 and W2 graphs and their sequences in full; W3 graph drawn as design only | p48 |
| Change request | Self-set, labelled as such, handled with the two-hour re-plan and an ADR | p43 |
| One slot = one appointment | No overbooking; capacity modelled per slot so overbooking can be switched on later | p10 |
