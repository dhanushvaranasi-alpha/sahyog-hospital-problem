# D4: Data contracts

21 contracts, one per table, written on the pack's template (p53) by `python -m data.build_contracts`.
The sensitivity class decides what may cross the hospital boundary (pack p21).

| Table | Owner (role) | Sensitivity | Freshness |
|---|---|---|---|
| [`patient`](patient.md) | Records service owner | direct | On change; read at request time |
| [`consent`](consent.md) | Compliance officer | quasi | Checked on every read; no caching |
| [`document`](document.md) | Records service owner | direct | Status visible within 60 s of upload (E3-S1) |
| [`doc_chunk`](doc_chunk.md) | Records service owner | direct | Re-embedded when content_hash changes |
| [`ingest_job`](ingest_job.md) | Platform | operational | Updated at every state change |
| [`appointment`](appointment.md) | Scheduling service owner | operational | Real time; tied to a patient, so reads are audited |
| [`slot`](slot.md) | Scheduling service owner | operational | Availability cached at most 30 s |
| [`doctor`](doctor.md) | Scheduling service owner | operational | Daily |
| [`clinic`](clinic.md) | Platform | operational | On change |
| [`specialty`](specialty.md) | Clinical safety | operational | On change, by pull request |
| [`condition_specialty`](condition_specialty.md) | Clinical safety | operational | On change, by pull request |
| [`medicine`](medicine.md) | Pharmacy | operational | Monthly |
| [`medicine_stock`](medicine_stock.md) | Pharmacy | operational | Nightly CSV today (stock age shown on every flag); API later (AD-5) |
| [`encounter`](encounter.md) | Records service owner | clinical | Real time |
| [`clinical_note`](clinical_note.md) | Clinical safety | clinical | Persisted only at signature; signed notes are immutable |
| [`prescription`](prescription.md) | Clinical safety | clinical | With its signed note |
| [`audit_event`](audit_event.md) | Compliance officer | operational | Written in the same transaction as the read; kept one year |
| [`src_appointment_history`](src_appointment_history.md) | Data | quasi | Static source snapshot |
| [`src_encounter_history`](src_encounter_history.md) | Data | quasi | Static source snapshot |
| [`src_condition_symptom`](src_condition_symptom.md) | Clinical safety | operational | Static source snapshot |
| [`src_transcription_note`](src_transcription_note.md) | Data | clinical | Static source snapshot |

## Sensitivity classes

| Class | Treatment |
|---|---|
| direct | Never leaves the boundary. Tokenise before any external call; Presidio plus Indian phone and ABHA recognisers. |
| quasi | Leaves only generalised: age band instead of birth date, district instead of pincode. |
| clinical | Leaves only de-identified; the token map stays on-premise. |
| operational | May leave; still audited when tied to a patient. |

## Compliance sign-off of the class column

Signed off by: Dhanush (compliance officer, in role) · Date: 2026-10-24
