"""PostgresDirectory against a real database: shortlist, idempotent booking, one live booking per slot, audit."""
import os
import uuid
from datetime import datetime

import psycopg
import pytest
from dotenv import load_dotenv

from data.transforms.common import REPO
from services.agent.w1.directory import PostgresDirectory, SlotTaken

load_dotenv(REPO / ".env")
URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL", "")


def _ready():
    try:
        with psycopg.connect(URL, connect_timeout=3) as c:
            return c.execute("SELECT count(*) FROM slot").fetchone()[0] > 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not URL or not _ready(), reason="Postgres with slots not reachable")
NOW = datetime.fromisoformat("2026-10-26T08:00:00+05:30")


@pytest.fixture
def pg():
    conn = psycopg.connect(URL)
    yield PostgresDirectory(conn), conn
    # clean up anything this test booked
    with conn.cursor() as cur:
        cur.execute("DELETE FROM appointment WHERE idempotency_key LIKE 'test-%%'")
    conn.commit(); conn.close()


def test_shortlist_returns_three_free_doctors(pg):
    d, _ = pg
    c = d.shortlist("Cardiology", NOW)
    assert len(c) == 3 and len({x.doctor_id for x in c}) == 3


def test_booking_is_idempotent_and_audited(pg):
    d, conn = pg
    slot = d.shortlist("Dermatology", NOW)[0].slot_id
    key = f"test-{uuid.uuid4().hex}"
    a1, a2 = d.book("P-PRIYA", slot, key), d.book("P-PRIYA", slot, key)
    assert a1 == a2
    n = conn.execute("SELECT count(*) FROM audit_event WHERE resource_type='appointment' AND resource_id=%s", (a1,)).fetchone()[0]
    assert n == 1


def test_a_booked_slot_cannot_be_booked_again_and_leaves_the_shortlist(pg):
    d, _ = pg
    first = d.shortlist("ENT", NOW)[0]
    d.book("P-PRIYA", first.slot_id, f"test-{uuid.uuid4().hex}")
    with pytest.raises(SlotTaken):
        d.book("P-SUNITA", first.slot_id, f"test-{uuid.uuid4().hex}")
    assert first.slot_id not in {c.slot_id for c in d.shortlist("ENT", NOW)}
