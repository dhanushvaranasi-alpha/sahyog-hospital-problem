"""Doctors, slots and bookings behind one interface (pack p24: tools are plain functions with typed inputs).

PostgresDirectory is what the service uses. InMemoryDirectory is built from the same committed doctor
directory and slot plan, so the eval runner can exercise the graph without a database.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import pandas as pd

from data.synthetic import slots as slot_plan
from data.transforms.common import REFERENCE

DOCTORS = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "output" / "doctors.jsonl"


@dataclass(frozen=True)
class Candidate:
    doctor_id: str
    doctor_name: str
    specialty: str
    clinic_id: str
    clinic_name: str
    city: str
    languages: tuple[str, ...]
    slot_id: str
    starts_at: str            # ISO 8601 with offset


class SlotTaken(Exception):
    """Another booking holds this slot; the caller offers the next one."""


class Directory(Protocol):
    def shortlist(self, specialty: str, now: datetime, k: int = 3, language: str | None = None) -> list[Candidate]: ...
    def book(self, patient_id: str, slot_id: str, idempotency_key: str) -> str: ...
    def handoff(self, kind: str, patient_id: str | None, detail: dict) -> str: ...
    def notify(self, patient_id: str, message: str) -> None: ...


def _rank(cands: list[Candidate], k: int, language: str | None) -> list[Candidate]:
    # Earliest slot first; a doctor who speaks the patient's language wins a tie within the same hour.
    def key(c: Candidate):
        return (c.starts_at[:13], 0 if language and language in c.languages else 1, c.starts_at, c.doctor_id)
    return sorted(cands, key=key)[:k]


class InMemoryDirectory:
    def __init__(self):
        docs = pd.DataFrame([json.loads(l) for l in DOCTORS.read_text().splitlines() if l.strip()])
        spec = pd.read_csv(REFERENCE / "specialties.csv").rename(columns={"name": "specialty"})
        sites = pd.read_csv(REFERENCE / "sites.csv").set_index("site_id")
        self.docs = docs.merge(spec, on="specialty_id")
        self.sites = sites
        cal = slot_plan.build(docs)
        cal["slot_id"] = [f"S{i:06d}" for i in range(1, len(cal) + 1)]
        self.slots = cal
        self.bookings: dict[str, str] = {}         # idempotency_key -> appointment id
        self.live: dict[str, str] = {}             # slot_id -> appointment id
        self.events: list[dict] = []

    def shortlist(self, specialty, now, k=3, language=None):
        docs = self.docs[self.docs["specialty"] == specialty]
        free = self.slots[(self.slots["doctor_id"].isin(docs["doctor_id"])) & (self.slots["starts_at"] >= now)
                          & (~self.slots["slot_id"].isin(self.live))]
        first = free.sort_values("starts_at").groupby("doctor_id").head(1)
        by_doc = docs.set_index("doctor_id")
        out = []
        for r in first.itertuples():
            d = by_doc.loc[r.doctor_id]
            site = self.sites.loc[r.clinic_id]
            out.append(Candidate(r.doctor_id, d["name"], specialty, r.clinic_id, site["name"], site["city"],
                                 tuple(d["languages"]), r.slot_id, r.starts_at.isoformat()))
        return _rank(out, k, language)

    def book(self, patient_id, slot_id, idempotency_key):
        if idempotency_key in self.bookings:
            return self.bookings[idempotency_key]
        if slot_id in self.live:
            raise SlotTaken(slot_id)
        appt = f"A-{uuid.uuid4().hex[:10]}"
        self.bookings[idempotency_key] = self.live[slot_id] = appt
        self.events.append({"action": "write", "resource_type": "appointment", "resource_id": appt, "actor_id": patient_id})
        return appt

    def handoff(self, kind, patient_id, detail):
        ticket = f"T-{uuid.uuid4().hex[:10]}"
        self.events.append({"action": "handoff", "resource_type": kind, "resource_id": ticket,
                            "actor_id": patient_id or "anonymous", "detail": detail})
        return ticket

    def notify(self, patient_id, message):
        self.events.append({"action": "notify", "resource_type": "sms", "resource_id": patient_id, "detail": message})


class PostgresDirectory:
    def __init__(self, conn):
        self.conn = conn          # a psycopg connection; autocommit off

    def shortlist(self, specialty, now, k=3, language=None):
        sql = """
        SELECT DISTINCT ON (d.doctor_id) d.doctor_id, d.name, s.name, c.site_id, c.name, c.city, d.languages,
               sl.slot_id, sl.starts_at
        FROM doctor d
        JOIN specialty s ON s.specialty_id = d.specialty_id
        JOIN slot sl ON sl.doctor_id = d.doctor_id
        JOIN clinic c ON c.site_id = sl.clinic_id
        WHERE s.name = %s AND sl.starts_at >= %s
          AND NOT EXISTS (SELECT 1 FROM appointment a WHERE a.slot_id = sl.slot_id AND a.status = 'booked')
        ORDER BY d.doctor_id, sl.starts_at"""
        with self.conn.cursor() as cur:
            cur.execute(sql, (specialty, now))
            rows = cur.fetchall()
        cands = [Candidate(r[0], r[1], r[2], r[3], r[4], r[5], tuple(r[6]), str(r[7]), r[8].isoformat()) for r in rows]
        return _rank(cands, k, language)

    def book(self, patient_id, slot_id, idempotency_key):
        import psycopg
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute("SELECT appt_id FROM appointment WHERE idempotency_key = %s", (idempotency_key,))
            row = cur.fetchone()
            if row:                               # E2-S2: a retry returns the same appointment
                return str(row[0])
            try:
                with self.conn.transaction():
                    cur.execute("INSERT INTO appointment (patient_id, slot_id, status, idempotency_key, booked_by) "
                                "VALUES (%s, %s, 'booked', %s, 'assistant') RETURNING appt_id",
                                (patient_id, int(slot_id), idempotency_key))
                    appt = str(cur.fetchone()[0])
            except psycopg.errors.UniqueViolation as e:
                if "one_live_booking_per_slot" in str(e):
                    raise SlotTaken(slot_id) from e
                raise
            cur.execute("INSERT INTO audit_event (actor_id, actor_role, purpose, action, resource_type, resource_id) "
                        "VALUES (%s, 'patient', 'booking', 'write', 'appointment', %s)", (patient_id, appt))
        self.conn.commit()
        return appt

    def handoff(self, kind, patient_id, detail):
        ticket = f"T-{uuid.uuid4().hex[:10]}"
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO audit_event (actor_id, actor_role, purpose, action, resource_type, resource_id) "
                        "VALUES (%s, 'patient', %s, 'handoff', %s, %s)",
                        (patient_id or "anonymous", json.dumps(detail)[:500], kind, ticket))
        self.conn.commit()
        return ticket

    def notify(self, patient_id, message):
        # SMS is a logged stub at Core (architecture decision 13).
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO audit_event (actor_id, actor_role, purpose, action, resource_type, resource_id) "
                        "VALUES ('system', 'system', %s, 'notify', 'sms', %s)", (message[:500], patient_id))
        self.conn.commit()


def as_dict(c: Candidate) -> dict:
    d = asdict(c)
    d["languages"] = list(c.languages)
    return d
