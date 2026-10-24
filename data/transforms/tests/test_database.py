"""Schema guarantees, tested against the running Postgres. Skipped if it is not reachable.

Each test runs inside a transaction that is rolled back, so it leaves no rows behind.
"""
import os

import psycopg
import pytest
from dotenv import load_dotenv

from data.transforms.common import REPO

load_dotenv(REPO / ".env")
URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL", "")


def _reachable() -> bool:
    try:
        with psycopg.connect(URL, connect_timeout=3):
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not URL or not _reachable(), reason="Postgres not reachable; run docker compose up")


@pytest.fixture
def cur():
    with psycopg.connect(URL) as conn:
        with conn.cursor() as c:
            c.execute("SELECT count(*) FROM clinic")
            if c.fetchone()[0] == 0:
                pytest.skip("reference data not loaded; run python -m data.load")
            c.execute("INSERT INTO patient (patient_id, name) VALUES ('T-P1', 'Test Patient')")
            c.execute("INSERT INTO doctor (doctor_id, name, specialty_id, clinic_id) VALUES ('T-D1', 'Dr Test', 'SP01', 'C-PUN-01')")
            c.execute("INSERT INTO slot (doctor_id, clinic_id, starts_at) VALUES ('T-D1', 'C-PUN-01', '2026-11-02 09:00+05:30') RETURNING slot_id")
            yield c, c.fetchone()[0]
        conn.rollback()


def _book(db, key):
    c, slot_id = db
    c.execute("INSERT INTO appointment (patient_id, slot_id, status, idempotency_key, booked_by) "
              "VALUES ('T-P1', %s, 'booked', %s, 'assistant')", (slot_id, key))


def test_a_slot_cannot_be_double_booked(cur):
    _book(cur, "k1")
    with pytest.raises(psycopg.errors.UniqueViolation, match="one_live_booking_per_slot"):
        _book(cur, "k2")


def test_a_retried_booking_cannot_create_a_second_row(cur):
    _book(cur, "same-key")
    cur[0].execute("UPDATE appointment SET status = 'cancelled' WHERE idempotency_key = 'same-key'")
    with pytest.raises(psycopg.errors.UniqueViolation, match="idempotency_key"):
        _book(cur, "same-key")


def test_audit_log_is_append_only(cur):
    cur = cur[0]
    cur.execute("INSERT INTO audit_event (actor_id, actor_role, purpose, action, resource_type, resource_id) "
                "VALUES ('T-P1', 'patient', 'test', 'read', 'document', 'x') RETURNING event_id")
    event_id = cur.fetchone()[0]
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        cur.execute("UPDATE audit_event SET purpose = 'edited' WHERE event_id = %s", (event_id,))


def test_loaded_counts_match_processed_files(cur):
    cur = cur[0]
    import pandas as pd
    from data.transforms.common import PROCESSED
    for table, name in [("medicine", "medicine"), ("src_appointment_history", "appointment_history"),
                        ("src_encounter_history", "encounter_history"), ("src_transcription_note", "transcription_note")]:
        cur.execute(f"SELECT count(*) FROM {table}")
        assert cur.fetchone()[0] == len(pd.read_parquet(PROCESSED / f"{name}.parquet")), table
