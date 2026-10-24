# D5: Is there enough data?

Measured on 24 Oct 2026 after a clean load (`python -m data.load` then `python -m data.synthetic.load`, followed by `VACUUM FULL`). The pack's sizing (p22) was a planning estimate for the full network; this build sizes its own, smaller estate and keeps the pack's three checks.

## The three checks

| Check (pack p22) | Result | Status |
|---|---|---|
| Every specialty has at least ten doctors | Minimum is 10 (33 specialties, 500 doctors) | Pass |
| Every clinic has slots on every working day | 336 of 336 site-days (28 sites × 12 working days) have slots | Pass |
| Every eval case has at least five candidate chunks | Estimated minimum 8 chunks per patient with reports (median 10; Priya's mother 19), from the generated report text split at about 1,200 characters per section | Estimated; confirmed after ingest (PR #6) against the eval set (PR #5) |

Checks 1 and 2 are automated in `data/synthetic/tests/test_synthetic.py`.

## Row counts

| Store | Rows | Source |
|---|---|---|
| `medicine` | 253,964 | A-Z Medicine Dataset of India |
| `src_appointment_history` | 110,516 | Medical Appointment No Shows |
| `slot` | 96,000 | 500 doctors × 12 working days × 16 slots, plain code |
| `src_encounter_history` | 54,966 | Healthcare Dataset |
| `src_transcription_note` | 2,347 | Medical Transcriptions |
| `patient` | 1,000 | Generated (code), including the two personas |
| `doctor` | 500 | Generated (code plan + LLM names) |
| Report PDFs | 100 | Generated (LLM text + code layout), for 49 patients |
| `src_condition_symptom` | 321 | Disease Symptom Prediction |

## Storage

| Store | Size rule | This build | Pack's full-network estimate |
|---|---|---|---|
| Vector index | chunks × 1,024 dimensions × 4 bytes | about 541 chunks → about 2.2 MB | 60,000 chunks → about 246 MB |
| Chunk text | chunks × average length | about 0.15 MB (median report 1,446 characters) | about 72 MB |
| Slot calendar | measured | 11 MB for 96,000 rows, indexes included | about 38 MB for 480,000 rows |
| Formulary | measured | 47 MB for 253,964 rows | — |
| Whole database | measured | 92 MB | — |
| Checkpoints | runs × steps × a few KB | negligible at demo volume; a 30-day purge is still required (p31) | tens of MB a day at 9,000 runs |
| Audio | minutes × about 1 MB | none at Core (W3 is Pro) | about 70 GB a day, deleted within 24 h |

## What this means

- The data is enough for Core: both workflows have doctors, slots and patient documents with more chunks per patient than the retrieval check needs.
- Everything fits comfortably on a laptop; the full network's vector index (about 246 MB) would too, so pgvector in Postgres stays the right store at this scale (architecture decision 4).
- A finding from the first load: the loader's upsert rewrote unchanged rows on every reload, which grew the database to 277 MB before `VACUUM`. The upsert now skips unchanged rows; a reload grows the database by about 1 MB.
