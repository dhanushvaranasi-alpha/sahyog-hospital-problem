# ADR 0008 — Erasure removes every derived copy of an upload; logs and hospital records stay

```yaml
title: CR-001 (self-set) — patients erase their uploads and withdraw consent; audit rows and hospital-issued reports are retained
context: The DPDP Act gives a right to erasure (s. 12) and to withdraw consent as easily as it was given (s. 6(4)); logs must be kept for at least a year (Rules r. 6). The system holds several derived copies of each report (chunks, vectors, token map, cached embeddings) and an append-only audit table. Hospital-issued reports are medical records whose retention is set by other law.
options:
  - name: Soft delete (flag the document, hide it from retrieval)
    cost: Simple and reversible, but the text, vectors and token map remain, which is not erasure
  - name: Hard delete of the upload and every derived copy; keep audit rows; refuse hospital reports
    cost: Irreversible by design; needs care that no copy is missed (tested) and that only the upload folder is touched
  - name: Hard delete everything for the patient, including audit rows and hospital reports
    cost: Breaks the append-only audit guarantee and the one-year log rule, and erases medical records the hospital may be obliged to keep
decision: Option 2. Erasure deletes the stored file, the document row and, by cascade, its chunks, vectors and token map, then removes cached embeddings for its chunks, then writes an audit event. Audit rows are kept because they hold ids only and are the required log. Hospital-issued reports return 409 with the reason; that answer depends on assumption A15 below. Consent withdrawal sets revoked_at and takes effect on the next question, because the access check reads consent on every call.
consequences: A15 added to the assumptions register for the compliance officer. Erasure is immediate, well inside 90 days. Backups and the hosted tracing project are outside this change (open questions in CR-001). No eval case changed; 8 tests cover the behaviour.
versions_pinned: none new
checked_on: 2026-10-25
status: accepted
```

**A15.** Hospital-issued reports are retained as medical records and are not erasable through the assistant; an erasure request for them goes to the records office. Owner: compliance officer. Validation: confirm the retention period and process with the client before go-live. Fallback: make hospital reports erasable from the assistant index only (chunks, vectors, token map), leaving the source record in the HIS.
