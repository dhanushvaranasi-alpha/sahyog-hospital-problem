"""CR-001 (self-set, not issued by the client): DPDP erasure and consent withdrawal.

Digital Personal Data Protection Act 2023: a patient may withdraw consent at any time, as easily as
it was given (s. 6(4)), and may ask for personal data to be erased unless retention is needed for
the purpose or required by law (s. 12). Erasure requests are to be handled within 90 days (DPDP
Rules 2025, r. 14); access and activity logs are kept for at least a year (r. 6).

What this module erases, for a document the patient uploaded:
  the stored PDF, the document row, its chunks and vectors (cascade), its PHI token map (cascade),
  and its cached embeddings on disk. Nothing derived from the document outlives it.
What it keeps:
  audit_event rows. They hold ids, never content, and are the log the rules require; the erasure
  itself is written as one more audit event.
What it refuses:
  hospital-issued reports. Those are part of the medical record, whose retention is governed by other
  law; ADR 0008 records this as an assumption for the client's compliance officer to confirm.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from services.records.store import RecordStore

PURPOSE_ERASE = "dpdp:s12-erasure"
PURPOSE_WITHDRAW = "dpdp:s6-withdrawal"
PURPOSE_GRANT = "dpdp:s6-consent"


class ErasureRefused(Exception):
    pass


@dataclass
class ErasureResult:
    doc_id: str
    chunks_removed: int
    cache_entries_removed: int
    file_removed: bool
    audit_id: int


def erase_upload(store: RecordStore, *, patient_id: str, doc_id: str, actor_id: str, upload_dir: Path,
                 embedder=None) -> ErasureResult:
    doc = store.document(doc_id)
    if doc is None or doc.patient_id != patient_id:
        raise LookupError("no such document")          # same answer for someone else's document
    if doc.type != "upload":
        raise ErasureRefused("hospital-issued report: kept as part of the medical record (ADR 0008)")
    texts = store.chunk_texts(doc_id)
    file_removed = False
    path = Path(doc.uri)
    # only ever delete inside the upload folder, whatever the uri says
    if path.is_file() and upload_dir.resolve() in path.resolve().parents:
        path.unlink()
        file_removed = True
    cache_removed = embedder.forget(texts) if embedder is not None and hasattr(embedder, "forget") else 0
    store.delete_document(doc_id)
    audit_id = store.audit(actor_id=actor_id, actor_role="patient", purpose=PURPOSE_ERASE, action="erase",
                           resource_type="document", resource_id=doc_id)
    return ErasureResult(doc_id, len(texts), cache_removed, file_removed, audit_id)


def withdraw_consent(store: RecordStore, *, subject_id: str, grantee_id: str, actor_id: str) -> int:
    n = store.revoke_consent(subject_id, grantee_id)
    store.audit(actor_id=actor_id, actor_role="patient", purpose=PURPOSE_WITHDRAW, action="revoke",
                resource_type="consent", resource_id=f"{subject_id}->{grantee_id}")
    return n


def grant_consent(store: RecordStore, *, subject_id: str, grantee_id: str, days: int, actor_id: str,
                  purpose: str = "caregiver") -> str:
    if subject_id == grantee_id:
        raise ValueError("cannot grant consent to yourself")
    if store.patient(grantee_id) is None:
        raise LookupError("unknown grantee")
    cid = store.grant_consent(subject_id, grantee_id, days, purpose)
    store.audit(actor_id=actor_id, actor_role="patient", purpose=PURPOSE_GRANT, action="grant",
                resource_type="consent", resource_id=cid)
    return cid
