# D1 — Automation ladder: task cards

Every task sits on one rung, decided by four questions (pack p8):
is the rule known and stable, is the input bounded, what does a wrong answer cost and who notices, who must sign off.

Rungs: **code** (known rule, bounded input) · **llm** (one fuzzy step inside checked code) · **agentic** (the path depends on tool results) · **human** (harm or law decides, whatever the model can do).

Eval case ids are planned ranges; the cases themselves land in `evals/sets/` before any graph code. Code-rung tasks are covered by unit tests rather than eval cases.

## Summary

| # | Task | Source | Rung | Tier |
|---|---|---|---|---|
| T01 | Sign the clinical note | Client | human | Pro |
| T02 | Pick a substitute medicine | Client | human | Pro |
| T03 | Choose among candidate doctors | Client | agentic | Core |
| T04 | Map symptoms to a specialty | Client | llm | Core |
| T05 | Answer a question on a report | Client | llm | Core |
| T06 | Turn dictation into a SOAP note | Client | llm | Pro |
| T07 | Decide whether a question needs a doctor | Client | llm | Core |
| T08 | Flag red-flag symptoms | Client | code (rules) + llm second | Core |
| T09 | Check the slot is still free | Client | code | Core |
| T10 | Send the booking confirmation | Client | code | Core |
| T11 | Extract text from a PDF | Client | code | Core |
| T12 | Check a medicine is in stock | Client | code | Pro |
| T13 | Check caregiver consent before a read | Found in discovery | code | Core |
| T14 | Write an audit event on every record read | Found in discovery | code | Core |
| T15 | Ask one clarifying question on unclear symptoms | Found in discovery | llm | Core |
| T16 | Grade whether retrieved context can answer | Found in discovery | llm | Core |
| T17 | Detect injected instructions in an uploaded PDF | Found in discovery | code + llm second | Core |
| T18 | Override or cancel a booking the assistant made | Found in discovery | human | Core |

## Client tasks (pack p8)

```yaml
task: Sign the clinical note
rule_known: no
input_bounded: yes
cost_of_error: patient harm and legal liability; noticed by the patient, pharmacist or an auditor, often late
sign_off: consulting doctor
rung: human
why: A signed note is a clinical and legal act (RFP addendum, p5). The model drafts; the graph interrupts and nothing persists unsigned.
eval_cases: w3 set (Pro tier)
```

```yaml
task: Pick a substitute medicine
rule_known: partly
input_bounded: yes
cost_of_error: wrong composition or dose reaches the patient; noticed by the pharmacist if lucky
sign_off: pharmacist
rung: human
why: Pharmacy fears software substitutions (p7). The model may list same-composition options from the formulary; the pharmacist chooses.
eval_cases: w3 set (Pro tier)
```

```yaml
task: Choose among candidate doctors
rule_known: partly
input_bounded: yes
cost_of_error: a slower or less suitable appointment; noticed by the patient or front desk
sign_off: patient
rung: agentic
why: The path depends on tool results (doctor list, free slots, no-show risk), so the graph loops over tools. The patient makes the final pick at an interrupt.
eval_cases: w1-029 to w1-030 (two specialties; the patient picks between candidates at the interrupt)
```

```yaml
task: Map symptoms to a specialty
rule_known: partly
input_bounded: no
cost_of_error: a wrong department visit and a wasted slot; noticed by the doctor at the visit
sign_off: none (patient confirms by choosing a slot)
rung: llm
why: Free text, often mixed Hindi-English, is a language problem. The model matches against the validated condition-to-specialty crosswalk inside checked code; confidence under 0.6 asks a question instead of guessing.
eval_cases: w1-011 to w1-025
```

```yaml
task: Answer a question on a report
rule_known: no
input_bounded: partly
cost_of_error: a patient misreads their own result; noticed late, if at all
sign_off: none (doctor hand-off for diagnosis or dose)
rung: llm
why: Language over the patient's own retrieved chunks. Retrieval scope is enforced in SQL; every answer cites document and page; citations are checked in code.
eval_cases: w2-001 to w2-015
```

```yaml
task: Turn dictation into a SOAP note
rule_known: partly
input_bounded: partly
cost_of_error: a wrong line in the medical record; noticed by the doctor at review
sign_off: consulting doctor (T01)
rung: llm
why: Structuring speech into four sections is a language task with a JSON schema. The model structures, never prescribes; gaps are bracketed for the doctor.
eval_cases: w3 set (Pro tier)
```

```yaml
task: Decide whether a question needs a doctor
rule_known: partly
input_bounded: no
cost_of_error: a diagnosis or dose given by software; noticed by nobody until harm
sign_off: none (hand-off is the safe default)
rung: llm
why: Requests for diagnosis or dosing are phrased in many ways, so a model classifies; any doubt hands off. Paired with a keyword rule as a floor.
eval_cases: w2-016 to w2-020
```

```yaml
task: Flag red-flag symptoms
rule_known: partly
input_bounded: no
cost_of_error: a missed emergency; patient harm; noticed too late
sign_off: none at triage; emergency desk takes over
rung: code (rules) with llm second
why: Recall must be 100% and auditable, so deterministic rules run first and log which rule fired. The model only reviews what the rules did not catch, and can add a flag but never remove one.
eval_cases: w1-001 to w1-010
```

```yaml
task: Check the slot is still free
rule_known: yes
input_bounded: yes
cost_of_error: a double-booking at the front desk; noticed immediately
sign_off: none
rung: code
why: A known rule over a bounded row. Booking and slot lock run in one transaction with a unique constraint.
eval_cases: unit test test_slot_lock_under_retry (PR #5)
```

```yaml
task: Send the booking confirmation
rule_known: yes
input_bounded: yes
cost_of_error: a patient without a confirmation calls the front desk; noticed by the front desk
sign_off: none
rung: code
why: A fixed template filled from the booking row. No model is needed for a known message.
eval_cases: unit test test_sms_on_booking (PR #5)
```

```yaml
task: Extract text from a PDF
rule_known: yes
input_bounded: yes
cost_of_error: an empty or garbled document in the index; noticed when answers fail
sign_off: none
rung: code
why: Synthetic reports are text PDFs, so a parser is enough. Scanned PDFs would add an OCR fallback, still code.
eval_cases: unit test test_pdf_text_extraction (PR #6)
```

```yaml
task: Check a medicine is in stock
rule_known: yes
input_bounded: yes
cost_of_error: a patient walks to an empty counter; noticed by the pharmacist
sign_off: none
rung: code
why: A lookup against the stock table behind one interface with CSV and API adapters; stock age shown on every flag.
eval_cases: w3 set (Pro tier)
```

## Tasks found in discovery

```yaml
task: Check caregiver consent before a read
rule_known: yes
input_bounded: yes
cost_of_error: a caregiver reads a record after consent expired; a DPDP breach noticed by compliance
sign_off: none
rung: code
why: Consent is a row with grantee, scope, purpose and expiry (p5, p33). Checking it is a known rule, enforced in the records service before retrieval.
eval_cases: unit test test_consent_expiry_blocks_read (PR #6); w2-021 to w2-025
```

```yaml
task: Write an audit event on every record read
rule_known: yes
input_bounded: yes
cost_of_error: compliance cannot answer who saw a record; noticed at an audit
sign_off: none
rung: code
why: A deterministic side effect of every read, so the compliance officer's question is one SELECT (p33).
eval_cases: unit test test_every_read_audited (PR #6)
```

```yaml
task: Ask one clarifying question on unclear symptoms
rule_known: partly
input_bounded: no
cost_of_error: a guessed specialty, or a patient lost in a long chat; noticed as a misroute or a call
sign_off: none
rung: llm
why: Choosing the one question that best separates two specialties is a language task. The loop is bounded in code: at most two, then a front-desk hand-off.
eval_cases: w1-026 to w1-028
```

```yaml
task: Grade whether retrieved context can answer
rule_known: no
input_bounded: yes
cost_of_error: an answer built on weak context; noticed as a low faithfulness score
sign_off: none
rung: llm
why: Judging relevance of a few chunks to a question needs language. Weak context widens the search once, then the answer says it cannot find the information.
eval_cases: w2-011 to w2-015
```

```yaml
task: Detect injected instructions in an uploaded PDF
rule_known: partly
input_bounded: yes
cost_of_error: the assistant follows text planted in a document; scope leak noticed by the patient or never
sign_off: none
rung: code (pattern rules) with llm second
why: Known injection phrasings are caught by rules; a model flags the rest. Either way scope stays in SQL, so a missed injection still cannot reach another patient's chunks.
eval_cases: w2-026 to w2-030 (includes the red-team PDF)
```

```yaml
task: Override or cancel a booking the assistant made
rule_known: yes
input_bounded: yes
cost_of_error: front desk loses control of the queue; noticed by patients at the counter
sign_off: front desk
rung: human
why: The front desk fears a bot that books the wrong slot (p11); acceptance criterion E2 says they can see and override any assistant booking. The override is theirs; the system only records it.
eval_cases: unit test test_front_desk_override_audited (PR #5)
```
