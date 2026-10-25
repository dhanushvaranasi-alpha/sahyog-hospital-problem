# CR-001 — Erasure and consent withdrawal under the DPDP Act

> **Self-set, not issued by the client.** No change request was issued during the engagement, so this one was chosen to exercise the re-plan ritual (pack p43; architecture decision 20).

**Raised:** 25 Oct 2026 · **Type:** regulation · **Re-plan time box:** two hours · **Decision record:** [ADR 0008](../adr/0008-dpdp-erasure.md)

## The request

"A patient must be able to withdraw a caregiver's consent and to have the reports they uploaded erased, in line with the Digital Personal Data Protection Act 2023, before go-live."

Legal basis, as checked on 25 Oct 2026 (secondary sources, listed at the end; the client's compliance officer confirms before go-live):

| Provision | What it requires |
|---|---|
| DPDP Act s. 6(4) | Consent can be withdrawn at any time, as easily as it was given |
| DPDP Act s. 12 | Erasure on request, unless retention is needed for the purpose or required by law |
| DPDP Act s. 8(7) | Erase when consent is withdrawn or the purpose is served, including copies held by processors |
| DPDP Rules 2025, r. 14 | Requests handled within 90 days |
| DPDP Rules 2025, r. 6 | Access and activity logs kept for at least one year |

## Impact analysis

| Component | Before | Change | Effort |
|---|---|---|---|
| Consent | Rows created by seed data only; revocation existed in the schema and the access check | Patients grant and withdraw from the API; both audited | Small |
| Uploaded reports | Kept until deleted by hand | Patient erases one upload: file, document, chunks, vectors, token map, cached embeddings | Medium |
| Hospital-issued reports | Indexed for W2 | Not erasable through the assistant; answered 409 with the reason (ADR 0008) | Small |
| Audit table | Append-only; ids only | Kept; erasure and withdrawal are themselves audit events | None |
| Embedding cache | Keyed by text hash, never pruned | Entries for an erased document removed | Small |
| Ingest jobs | Linked to the document | Link cleared on erasure; job history kept | Small |
| LangSmith traces | De-identified text only | Token map erased, so traces cannot be re-identified through the system; retention setting is an open question | Open question |
| Eval set | 30 W2 cases | Unchanged (frozen); the new behaviour is covered by tests | None |

## Re-plan

| Step | Status |
|---|---|
| Store: document lookup, chunk texts, delete, grant, revoke (Postgres and in memory) | Done |
| `services/records/erasure.py`: erase an upload, withdraw and grant consent, with audit | Done |
| API: `GET /v1/w2/documents`, `DELETE /v1/w2/documents/{id}`, `POST /v1/w2/consents`, `DELETE /v1/w2/consents/{grantee}` | Done |
| Tests: every derived copy gone, assistant no longer finds the report, withdrawal refuses at once, no file deleted outside the upload folder | Done (8 new tests) |
| ADR 0008, data contracts updated | Done |
| Not done in this change: erasure from backups; a 48-hour notice before purpose-based expiry (r. 8(2)); an erasure request for hospital records routed to the records office | Deferred, listed below |

Schedule effect: the change fits in the remaining Core time; nothing else in Core was cut. The evaluation report and cost sheet move one step later.

## Open questions for the client

1. How long must hospital-issued reports be kept as medical records, and who answers an erasure request for them? (Assumption: the records office, outside the assistant.)
2. Do database backups need targeted erasure, or is expiry of the backup cycle accepted?
3. What retention is set on the hosted tracing project? Traces hold de-identified text only.

## Sources

- [DSCI, FAQ on data retention and data erasure (2025)](https://www.dsci.in/files/content/documents/2025/faq-on-data-retention-and-data-erasure-v2.pdf): s. 8(7), r. 6, r. 8
- [Seclore, DPDP Rules 2025 compliance guide](https://www.seclore.com/fundamentals/dpdp-rules-2025-compliance-guide/): notification 13 Nov 2025, r. 14 90 days
- [miniOrange, data principal rights under the DPDP Act](https://www.miniorange.com/blog/data-principal-rights-under-dpdp-act/): s. 6(4), s. 12
