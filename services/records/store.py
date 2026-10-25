"""Records service (architecture: 'Records service — access matrix + consent').

Every read the W2 graphs make goes through a RecordStore. The patient filter is a required
argument of `search`, so there is no code path that searches across patients; in Postgres it is
a WHERE clause in the same query as the similarity ranking (p31).

Two implementations behind one Protocol, as with the W1 directory: Postgres + pgvector for the
running system, and an in-memory store for evals and unit tests.
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Protocol

import numpy as np

ConsentState = Literal["self", "valid", "expired", "revoked", "none"]


@dataclass
class PatientIdentity:
    patient_id: str
    name: str
    phone: str | None = None
    abha_id: str | None = None


@dataclass
class DocumentRow:
    doc_id: str
    patient_id: str
    type: str
    uri: str
    source_ref: str | None
    report_date: str | None
    title: str
    content_hash: str
    injection_removed: int = 0
    phi_status: str = "tagged"


@dataclass
class ChunkRow:
    doc_id: str
    patient_id: str
    page: int
    section: str
    text: str                 # de-identified; tokens like <PERSON_1>
    content_hash: str
    embedding: np.ndarray | None = None
    score: float = 0.0
    source_ref: str | None = None
    report_date: str | None = None
    title: str = ""


@dataclass
class Grant:
    state: ConsentState
    consent_id: str | None = None
    purpose: str = "self"


class RecordStore(Protocol):
    def patient(self, patient_id: str) -> PatientIdentity | None: ...
    def patients_named(self, name: str) -> list[str]: ...
    def grant(self, subject_id: str, grantee_id: str, at: datetime | None = None) -> Grant: ...
    def document_by_hash(self, patient_id: str, content_hash: str) -> DocumentRow | None: ...
    def add_document(self, doc: DocumentRow, chunks: list[ChunkRow], tokens: dict[str, tuple[str, str]]) -> str: ...
    def documents(self, patient_id: str) -> list[DocumentRow]: ...
    def search(self, patient_id: str, query: np.ndarray, k: int) -> list[ChunkRow]: ...
    def tokens(self, doc_ids: list[str]) -> dict[str, dict[str, tuple[str, str]]]: ...
    def audit(self, *, actor_id: str, actor_role: str, purpose: str, action: str, resource_type: str,
              resource_id: str, trace_id: str | None = None) -> int: ...
    # DPDP change request (CR-001): erasure and consent withdrawal
    def document(self, doc_id: str) -> DocumentRow | None: ...
    def chunk_texts(self, doc_id: str) -> list[str]: ...
    def delete_document(self, doc_id: str) -> bool: ...
    def grant_consent(self, subject_id: str, grantee_id: str, days: int, purpose: str) -> str: ...
    def revoke_consent(self, subject_id: str, grantee_id: str) -> int: ...
    def consents_for(self, patient_id: str) -> list[dict]: ...


def _grant_from(rows: list[tuple[str, str, datetime, datetime | None]], at: datetime) -> Grant:
    """rows: (consent_id, purpose, expires_at, revoked_at). Valid beats expired beats revoked."""
    best = Grant("none")
    rank = {"none": 0, "revoked": 1, "expired": 2, "valid": 3}
    for cid, purpose, expires, revoked in rows:
        state = "revoked" if revoked is not None and revoked <= at else ("expired" if expires <= at else "valid")
        if rank[state] > rank[best.state]:
            best = Grant(state, str(cid), purpose)
    return best


class InMemoryRecordStore:
    def __init__(self, patients: list[PatientIdentity] | None = None):
        self._patients = {p.patient_id: p for p in patients or []}
        self._consents: list[dict] = []
        self._docs: dict[str, DocumentRow] = {}
        self._chunks: list[ChunkRow] = []
        self._tokens: dict[str, dict[str, tuple[str, str]]] = {}
        self.audit_log: list[dict] = []

    def fork(self) -> "InMemoryRecordStore":
        """Copy for one eval case: uploads, consents and audit rows do not leak into the next case."""
        other = InMemoryRecordStore()
        other._patients = self._patients
        other._consents = copy.deepcopy(self._consents)
        other._docs = dict(self._docs)
        other._chunks = list(self._chunks)
        other._tokens = dict(self._tokens)
        return other

    def add_patient(self, p: PatientIdentity) -> None:
        self._patients[p.patient_id] = p

    def add_consent(self, patient_id: str, grantee_id: str, *, state: str = "valid", purpose: str = "caregiver") -> None:
        now = datetime.now(timezone.utc)
        far, past = datetime(2099, 1, 1, tzinfo=timezone.utc), datetime(2020, 1, 1, tzinfo=timezone.utc)
        self._consents.append({"consent_id": str(uuid.uuid4()), "patient_id": patient_id, "grantee_id": grantee_id,
                               "purpose": purpose, "expires_at": past if state == "expired" else far,
                               "revoked_at": now if state == "revoked" else None})

    def patient(self, patient_id: str) -> PatientIdentity | None:
        return self._patients.get(patient_id)

    def patients_named(self, name: str) -> list[str]:
        n = name.strip().lower()
        return [p.patient_id for p in self._patients.values()
                if n and (p.name.lower() == n or n in p.name.lower().split())]

    def grant(self, subject_id: str, grantee_id: str, at: datetime | None = None) -> Grant:
        if subject_id == grantee_id:
            return Grant("self")
        at = at or datetime.now(timezone.utc)
        rows = [(c["consent_id"], c["purpose"], c["expires_at"], c["revoked_at"]) for c in self._consents
                if c["patient_id"] == subject_id and c["grantee_id"] == grantee_id]
        return _grant_from(rows, at)

    def document_by_hash(self, patient_id: str, content_hash: str) -> DocumentRow | None:
        return next((d for d in self._docs.values()
                     if d.patient_id == patient_id and d.content_hash == content_hash), None)

    def add_document(self, doc: DocumentRow, chunks: list[ChunkRow], tokens: dict[str, tuple[str, str]]) -> str:
        self._docs[doc.doc_id] = doc
        self._chunks.extend(chunks)
        self._tokens[doc.doc_id] = dict(tokens)
        return doc.doc_id

    def documents(self, patient_id: str) -> list[DocumentRow]:
        return sorted((d for d in self._docs.values() if d.patient_id == patient_id),
                      key=lambda d: d.report_date or "")

    def search(self, patient_id: str, query: np.ndarray, k: int) -> list[ChunkRow]:
        mine = [c for c in self._chunks if c.patient_id == patient_id and c.embedding is not None]
        if not mine:
            return []
        scores = np.vstack([c.embedding for c in mine]) @ query
        out = []
        for i in np.argsort(-scores)[:k]:
            c = copy.copy(mine[i])
            d = self._docs[c.doc_id]
            c.score, c.source_ref, c.report_date, c.title = float(scores[i]), d.source_ref, d.report_date, d.title
            out.append(c)
        return out

    def tokens(self, doc_ids: list[str]) -> dict[str, dict[str, tuple[str, str]]]:
        return {d: self._tokens.get(d, {}) for d in doc_ids}

    def document(self, doc_id: str) -> DocumentRow | None:
        return self._docs.get(doc_id)

    def chunk_texts(self, doc_id: str) -> list[str]:
        return [c.text for c in self._chunks if c.doc_id == doc_id]

    def delete_document(self, doc_id: str) -> bool:
        if doc_id not in self._docs:
            return False
        del self._docs[doc_id]
        self._chunks = [c for c in self._chunks if c.doc_id != doc_id]
        self._tokens.pop(doc_id, None)
        return True

    def grant_consent(self, subject_id: str, grantee_id: str, days: int, purpose: str) -> str:
        from datetime import timedelta
        cid = str(uuid.uuid4())
        self._consents.append({"consent_id": cid, "patient_id": subject_id, "grantee_id": grantee_id, "purpose": purpose,
                               "expires_at": datetime.now(timezone.utc) + timedelta(days=days), "revoked_at": None})
        return cid

    def revoke_consent(self, subject_id: str, grantee_id: str) -> int:
        n = 0
        for c in self._consents:
            if c["patient_id"] == subject_id and c["grantee_id"] == grantee_id and c["revoked_at"] is None:
                c["revoked_at"] = datetime.now(timezone.utc)
                n += 1
        return n

    def consents_for(self, patient_id: str) -> list[dict]:
        now = datetime.now(timezone.utc)
        out = []
        for c in self._consents:
            if patient_id in (c["patient_id"], c["grantee_id"]):
                state = _grant_from([(c["consent_id"], c["purpose"], c["expires_at"], c["revoked_at"])], now).state
                out.append({"consent_id": c["consent_id"], "patient_id": c["patient_id"], "grantee_id": c["grantee_id"],
                            "purpose": c["purpose"], "expires_at": c["expires_at"].isoformat(), "state": state})
        return out

    def audit(self, *, actor_id: str, actor_role: str, purpose: str, action: str, resource_type: str,
              resource_id: str, trace_id: str | None = None) -> int:
        self.audit_log.append({"actor_id": actor_id, "actor_role": actor_role, "purpose": purpose, "action": action,
                               "resource_type": resource_type, "resource_id": resource_id, "trace_id": trace_id})
        return len(self.audit_log)


def _vec(v: np.ndarray) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v.tolist()) + "]"


class PostgresRecordStore:
    def __init__(self, conn):
        self.conn = conn          # psycopg connection, autocommit off; each write commits

    def patient(self, patient_id: str) -> PatientIdentity | None:
        with self.conn.cursor() as cur:
            cur.execute("SELECT patient_id, name, phone, abha_id FROM patient WHERE patient_id = %s", (patient_id,))
            r = cur.fetchone()
        return PatientIdentity(*r) if r else None

    def patients_named(self, name: str) -> list[str]:
        n = name.strip().lower()
        if not n:
            return []
        with self.conn.cursor() as cur:
            cur.execute("SELECT patient_id FROM patient WHERE lower(name) = %s OR %s = ANY(string_to_array(lower(name), ' '))",
                        (n, n))
            return [r[0] for r in cur.fetchall()]

    def grant(self, subject_id: str, grantee_id: str, at: datetime | None = None) -> Grant:
        if subject_id == grantee_id:
            return Grant("self")
        with self.conn.cursor() as cur:
            cur.execute("SELECT consent_id, purpose, expires_at, revoked_at FROM consent "
                        "WHERE patient_id = %s AND grantee_id = %s AND scope = 'records:read'", (subject_id, grantee_id))
            rows = cur.fetchall()
        return _grant_from(rows, at or datetime.now(timezone.utc))

    def document_by_hash(self, patient_id: str, content_hash: str) -> DocumentRow | None:
        with self.conn.cursor() as cur:
            cur.execute("SELECT doc_id, patient_id, type, uri, source_ref, report_date::text, coalesce(title, ''), "
                        "content_hash, injection_removed, phi_status FROM document "
                        "WHERE patient_id = %s AND content_hash = %s", (patient_id, content_hash))
            r = cur.fetchone()
        return DocumentRow(str(r[0]), *r[1:]) if r else None

    def add_document(self, doc: DocumentRow, chunks: list[ChunkRow], tokens: dict[str, tuple[str, str]]) -> str:
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO document (doc_id, patient_id, type, uri, source_ref, report_date, title, content_hash, "
                "injection_removed, phi_status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (doc.doc_id, doc.patient_id, doc.type, doc.uri, doc.source_ref, doc.report_date, doc.title,
                 doc.content_hash, doc.injection_removed, doc.phi_status))
            for c in chunks:
                cur.execute("INSERT INTO doc_chunk (doc_id, patient_id, page, section, text, content_hash, embedding) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s::vector)",
                            (c.doc_id, c.patient_id, c.page, c.section, c.text, c.content_hash, _vec(c.embedding)))
            for tok, (ent, val) in tokens.items():
                cur.execute("INSERT INTO doc_phi_token (doc_id, token, entity_type, value) VALUES (%s,%s,%s,%s)",
                            (doc.doc_id, tok, ent, val))
        self.conn.commit()
        return doc.doc_id

    def documents(self, patient_id: str) -> list[DocumentRow]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT doc_id, patient_id, type, uri, source_ref, report_date::text, coalesce(title, ''), "
                        "content_hash, injection_removed, phi_status FROM document "
                        "WHERE patient_id = %s AND phi_status = 'tagged' ORDER BY report_date NULLS FIRST", (patient_id,))
            return [DocumentRow(str(r[0]), *r[1:]) for r in cur.fetchall()]

    def search(self, patient_id: str, query: np.ndarray, k: int) -> list[ChunkRow]:
        # Exact ranking over this patient's rows (tens of chunks): `+ 0` keeps the planner off the HNSW
        # index, whose approximate scan applies the patient filter afterwards and can return too few rows.
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT c.doc_id, c.patient_id, c.page, coalesce(c.section, ''), c.text, c.content_hash, "
                "1 - (c.embedding <=> %s::vector) AS score, d.source_ref, d.report_date::text, coalesce(d.title, '') "
                "FROM doc_chunk c JOIN document d USING (doc_id) "
                "WHERE c.patient_id = %s AND d.patient_id = %s AND d.phi_status = 'tagged' "
                "ORDER BY (c.embedding <=> %s::vector) + 0 LIMIT %s",
                (_vec(query), patient_id, patient_id, _vec(query), k))
            rows = cur.fetchall()
        return [ChunkRow(doc_id=str(r[0]), patient_id=r[1], page=r[2], section=r[3], text=r[4], content_hash=r[5],
                         score=float(r[6]), source_ref=r[7], report_date=r[8], title=r[9]) for r in rows]

    def tokens(self, doc_ids: list[str]) -> dict[str, dict[str, tuple[str, str]]]:
        out: dict[str, dict[str, tuple[str, str]]] = {d: {} for d in doc_ids}
        if not doc_ids:
            return out
        with self.conn.cursor() as cur:
            cur.execute("SELECT doc_id, token, entity_type, value FROM doc_phi_token WHERE doc_id = ANY(%s::uuid[])",
                        (doc_ids,))
            for d, tok, ent, val in cur.fetchall():
                out[str(d)][tok] = (ent, val)
        return out

    def document(self, doc_id: str) -> DocumentRow | None:
        with self.conn.cursor() as cur:
            cur.execute("SELECT doc_id, patient_id, type, uri, source_ref, report_date::text, coalesce(title, ''), "
                        "content_hash, injection_removed, phi_status FROM document WHERE doc_id = %s::uuid", (doc_id,))
            r = cur.fetchone()
        return DocumentRow(str(r[0]), *r[1:]) if r else None

    def chunk_texts(self, doc_id: str) -> list[str]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT text FROM doc_chunk WHERE doc_id = %s::uuid", (doc_id,))
            return [r[0] for r in cur.fetchall()]

    def delete_document(self, doc_id: str) -> bool:
        # chunks and the token map cascade; the ingest job keeps its history without the link
        with self.conn.cursor() as cur:
            cur.execute("UPDATE ingest_job SET doc_id = NULL WHERE doc_id = %s::uuid", (doc_id,))
            cur.execute("DELETE FROM document WHERE doc_id = %s::uuid", (doc_id,))
            n = cur.rowcount
        self.conn.commit()
        return n == 1

    def grant_consent(self, subject_id: str, grantee_id: str, days: int, purpose: str) -> str:
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO consent (patient_id, grantee_id, scope, purpose, expires_at) "
                        "VALUES (%s, %s, 'records:read', %s, now() + make_interval(days => %s)) RETURNING consent_id",
                        (subject_id, grantee_id, purpose, days))
            cid = str(cur.fetchone()[0])
        self.conn.commit()
        return cid

    def revoke_consent(self, subject_id: str, grantee_id: str) -> int:
        with self.conn.cursor() as cur:
            cur.execute("UPDATE consent SET revoked_at = now() WHERE patient_id = %s AND grantee_id = %s "
                        "AND revoked_at IS NULL", (subject_id, grantee_id))
            n = cur.rowcount
        self.conn.commit()
        return n

    def consents_for(self, patient_id: str) -> list[dict]:
        now = datetime.now(timezone.utc)
        with self.conn.cursor() as cur:
            cur.execute("SELECT consent_id, patient_id, grantee_id, purpose, expires_at, revoked_at FROM consent "
                        "WHERE (patient_id = %s OR grantee_id = %s) AND scope = 'records:read' ORDER BY created_at",
                        (patient_id, patient_id))
            rows = cur.fetchall()
        return [{"consent_id": str(r[0]), "patient_id": r[1], "grantee_id": r[2], "purpose": r[3],
                 "expires_at": r[4].isoformat(), "state": _grant_from([(r[0], r[3], r[4], r[5])], now).state}
                for r in rows]

    def audit(self, *, actor_id: str, actor_role: str, purpose: str, action: str, resource_type: str,
              resource_id: str, trace_id: str | None = None) -> int:
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO audit_event (actor_id, actor_role, purpose, action, resource_type, resource_id, trace_id) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING event_id",
                        (actor_id, actor_role, purpose, action, resource_type, resource_id, trace_id))
            eid = cur.fetchone()[0]
        self.conn.commit()
        return eid

