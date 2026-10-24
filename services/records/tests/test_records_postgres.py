"""PostgresRecordStore against a real database: ingest, patient-filtered search, tokens, consent, audit."""
import os

import psycopg
import pytest
from dotenv import load_dotenv

from data.transforms.common import REPO
from services.common.embed import HashEmbedder
from services.common.phi import TOKEN
from services.records.ingest import ingest_file
from services.records.store import PostgresRecordStore

load_dotenv(REPO / ".env")
URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
REDTEAM = REPO / "evals" / "sets" / "redteam" / "redteam_injection.pdf"


def _ready():
    try:
        with psycopg.connect(URL, connect_timeout=3) as c:
            has_patient = c.execute("SELECT count(*) FROM patient WHERE patient_id = 'P00637'").fetchone()[0] == 1
            has_cols = c.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'doc_phi_token'").fetchone()[0] == 1
            return has_patient and has_cols
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not URL or not _ready(), reason="Postgres with patients and the 003 schema not reachable")


class Emb1024(HashEmbedder):
    def __init__(self):
        super().__init__(1024)


@pytest.fixture
def pg():
    conn = psycopg.connect(URL)
    store = PostgresRecordStore(conn)
    yield store, conn
    conn.rollback()
    with conn.cursor() as cur:   # documents and their chunks/tokens cascade; audit rows are append-only by design
        cur.execute("DELETE FROM document WHERE uri = %s", (str(REDTEAM),))
        cur.execute("DELETE FROM consent WHERE purpose = 'test-fixture'")
    conn.commit(); conn.close()


def test_ingest_search_and_tokens(pg):
    store, conn = pg
    emb = Emb1024()
    r = ingest_file(store, emb, REDTEAM, "P00637", doc_type="upload")
    assert r["injection_removed"] == 5
    assert ingest_file(store, emb, REDTEAM, "P00637")["existing"]
    hits = store.search("P00637", emb.embed(["haemoglobin"])[0], 8)
    assert hits and {h.patient_id for h in hits} == {"P00637"} and hits[0].source_ref == "RT-0001"
    assert all("OVERRIDE" not in h.text and "P00637" not in h.text for h in hits)
    tok = store.tokens([r["doc_id"]])[r["doc_id"]]
    assert all(m.group(0) in tok for h in hits for m in TOKEN.finditer(h.text))   # every token resolvable
    others = store.search("P-SUNITA", emb.embed(["haemoglobin"])[0], 50)
    assert all(h.patient_id == "P-SUNITA" and h.source_ref != "RT-0001" for h in others)


def test_consent_states_from_rows(pg):
    store, conn = pg
    with conn.cursor() as cur:
        cur.execute("INSERT INTO consent (patient_id, grantee_id, scope, purpose, expires_at) "
                    "VALUES ('P00637', 'P00219', 'records:read', 'test-fixture', now() - interval '1 day')")
        cur.execute("INSERT INTO consent (patient_id, grantee_id, scope, purpose, expires_at, revoked_at) "
                    "VALUES ('P00637', 'P00164', 'records:read', 'test-fixture', now() + interval '30 days', now())")
        cur.execute("INSERT INTO consent (patient_id, grantee_id, scope, purpose, expires_at) "
                    "VALUES ('P00637', 'P00560', 'records:read', 'test-fixture', now() + interval '30 days')")
    conn.commit()
    assert store.grant("P00637", "P00219").state == "expired"
    assert store.grant("P00637", "P00164").state == "revoked"
    assert store.grant("P00637", "P00560").state == "valid"
    assert store.grant("P00637", "P00001").state == "none"


def test_audit_is_append_only(pg):
    store, conn = pg
    eid = store.audit(actor_id="test", actor_role="test", purpose="test", action="read",
                      resource_type="document", resource_id="test")
    with pytest.raises(psycopg.errors.RaiseException):
        with conn.cursor() as cur:
            cur.execute("DELETE FROM audit_event WHERE event_id = %s", (eid,))
    conn.rollback()
