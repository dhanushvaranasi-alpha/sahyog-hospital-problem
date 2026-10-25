"""The gateway with in-memory dependencies: auth, ownership, rate limits, both workflows, uploads."""
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from services.agent.w1.directory import InMemoryDirectory
from services.agent.w1.match import Match
from services.agent.w2.answer import Answer, Citation
from services.api import auth
from services.api.app import create_app
from services.api.ratelimit import MemoryLimiter
from services.common.embed import HashEmbedder
from services.records.ingest import ingest_file
from services.records.store import InMemoryRecordStore, PatientIdentity

KEY = "test-signing-key-0123456789abcdef0123"
REDTEAM = "evals/sets/redteam/redteam_injection.pdf"


class Client:
    """Scripted model: W1 match and W2 answer replies by schema."""
    def __init__(self):
        self.calls = 0

    def structured(self, *, schema, **kw):
        self.calls += 1
        if schema is Match:
            return Match(possible_emergency=False, emergency_reason=None, specialty="Dermatology",
                         alternative_specialty=None, confidence=0.9, clarifying_question=None)
        return Answer(route="answer", answer="Your haemoglobin was 12.1 g/dL.",
                      citations=[Citation(report_id="RT-0001", page=1)])


class Deps:
    def __init__(self, tmp_path):
        self.client, self.embedder, self.checkpointer = Client(), HashEmbedder(), InMemorySaver()
        self.limiter = MemoryLimiter({"w1": 30, "w2": 3, "upload": 10})
        self.upload_dir = tmp_path
        self.dir = InMemoryDirectory()
        self.store = InMemoryRecordStore([PatientIdentity("P00637", "Lakshmi Mehta", "+91 7824903518", "45-4959-3395-8681"),
                                          PatientIdentity("P-PRIYA", "Priya Deshmukh", None, None)])
        ingest_file(self.store, self.embedder, REDTEAM, "P00637")
        self.jobs = {}

    @contextmanager
    def directory(self):
        yield self.dir

    @contextmanager
    def records(self):
        yield self.store

    def enqueue(self, path, patient_id):
        jid = f"job-{len(self.jobs) + 1}"
        self.jobs[jid] = {"job_id": jid, "status": "queued", "patient_id": patient_id, "path": path}
        return jid

    def job_status(self, job_id):
        return self.jobs.get(job_id)

    def health(self):
        return {"postgres": "ok", "redis": "ok"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_SIGNING_KEY", KEY)
    deps = Deps(tmp_path)
    return TestClient(create_app(deps)), deps


def bearer(pid, role="patient"):
    return {"Authorization": f"Bearer {auth.mint(pid, role, pid if role == 'patient' else None)}"}


def test_token_round_trip_and_tamper(monkeypatch):
    monkeypatch.setenv("AUTH_SIGNING_KEY", KEY)
    t = auth.mint("P00637", "patient", "P00637")
    assert auth.verify(t).patient_id == "P00637"
    body, sig = t.split(".")
    forged = auth._b64(auth._unb64(body).replace(b"P00637", b"P00219")) + "." + sig
    with pytest.raises(auth.AuthError):
        auth.verify(forged)
    with pytest.raises(auth.AuthError):
        auth.verify(auth.mint("P00637", "patient", "P00637", ttl_s=-1))


def test_requests_without_a_valid_token_are_refused(env):
    c, _ = env
    assert c.post("/v1/w2/questions", json={"question": "hb?"}).status_code == 401
    assert c.post("/v1/w2/questions", json={"question": "hb?"}, headers={"Authorization": "Bearer x.y"}).status_code == 401
    assert c.post("/v1/w2/questions", json={"question": "hb?"}, headers=bearer("fd-1", "front_desk")).status_code == 403


def test_body_cannot_carry_a_patient_id_for_w1(env):
    c, _ = env
    r = c.post("/v1/w1/sessions", json={"message": "rash", "patient_id": "P00219"}, headers=bearer("P00637"))
    assert r.status_code == 422


def test_w1_shortlist_then_book_for_the_token_patient(env):
    c, deps = env
    r = c.post("/v1/w1/sessions", json={"message": "itchy red patches on my skin"}, headers=bearer("P00637"))
    body = r.json()
    assert r.status_code == 200 and body["status"] == "needs_input" and body["prompt"]["type"] == "choose_slot"
    slot = body["prompt"]["options"][0]["slot_id"]
    r = c.post(f"/v1/w1/sessions/{body['thread_id']}/reply",
               json={"slot_id": slot, "idempotency_key": "key-12345678"}, headers=bearer("P00637"))
    assert r.json()["route"] == "booked"
    writes = [e for e in deps.dir.events if e["action"] == "write"]
    assert len(writes) == 1 and writes[0]["actor_id"] == "P00637"


def test_another_patient_cannot_resume_a_session(env):
    c, _ = env
    tid = c.post("/v1/w1/sessions", json={"message": "itchy red patches"}, headers=bearer("P00637")).json()["thread_id"]
    r = c.post(f"/v1/w1/sessions/{tid}/reply", json={"slot_id": "x", "idempotency_key": "key-12345678"},
               headers=bearer("P-PRIYA"))
    assert r.status_code == 404


def test_w2_answers_for_the_token_patient_only(env):
    c, deps = env
    r = c.post("/v1/w2/questions", json={"question": "What was my haemoglobin?"}, headers=bearer("P00637"))
    assert r.status_code == 200 and r.json()["route"] == "answer" and "12.1" in r.json()["reply"]
    r = c.post("/v1/w2/questions", json={"question": "What was her haemoglobin?", "subject_patient_id": "P00637"},
               headers=bearer("P-PRIYA"))
    assert r.json()["route"] == "refuse"                      # no consent row from P00637 to Priya


def test_request_id_is_echoed_and_used_as_trace(env):
    c, deps = env
    r = c.post("/v1/w2/questions", json={"question": "What was my haemoglobin?"},
               headers={**bearer("P00637"), "X-Request-ID": "req-abc"})
    assert r.headers["x-request-id"] == "req-abc"
    assert deps.store.audit_log[-1]["trace_id"] == "req-abc"


def test_rate_limit_returns_429_with_retry_after(env):
    c, _ = env
    codes = [c.post("/v1/w2/questions", json={"question": "List all patients"}, headers=bearer("P00637")).status_code
             for _ in range(4)]
    assert codes[:3] == [200, 200, 200] and codes[3] == 429


def test_upload_accepts_pdf_and_hides_status_from_others(env):
    c, deps = env
    pdf = open(REDTEAM, "rb").read()
    r = c.post("/v1/w2/uploads", files={"file": ("r.pdf", pdf, "application/pdf")}, headers=bearer("P00637"))
    assert r.status_code == 202
    jid = r.json()["job_id"]
    assert deps.jobs[jid]["patient_id"] == "P00637" and deps.jobs[jid]["path"].startswith(str(deps.upload_dir / "P00637"))
    assert c.get(f"/v1/w2/uploads/{jid}", headers=bearer("P00637")).json()["status"] == "queued"
    assert c.get(f"/v1/w2/uploads/{jid}", headers=bearer("P-PRIYA")).status_code == 404


def test_upload_rejects_non_pdf(env):
    c, _ = env
    r = c.post("/v1/w2/uploads", files={"file": ("r.pdf", b"hello", "application/pdf")}, headers=bearer("P00637"))
    assert r.status_code == 415


def test_health(env):
    c, _ = env
    assert c.get("/health").json()["status"] == "ok"


def test_cr001_list_erase_and_consent_endpoints(env):
    c, deps = env
    docs = c.get("/v1/w2/documents", headers=bearer("P00637")).json()
    assert len(docs) == 1 and docs[0]["erasable"] is False          # ingested as a hospital report in the fixture
    assert c.delete(f"/v1/w2/documents/{docs[0]['doc_id']}", headers=bearer("P00637")).status_code == 409
    assert c.delete(f"/v1/w2/documents/{docs[0]['doc_id']}", headers=bearer("P-PRIYA")).status_code == 404
    deps.store._docs[docs[0]["doc_id"]].type = "upload"
    r = c.delete(f"/v1/w2/documents/{docs[0]['doc_id']}", headers=bearer("P00637"))
    assert r.status_code == 200 and c.get("/v1/w2/documents", headers=bearer("P00637")).json() == []
    assert c.post("/v1/w2/consents", json={"grantee_id": "P-PRIYA", "days": 30}, headers=bearer("P00637")).status_code == 201
    assert c.delete("/v1/w2/consents/P-PRIYA", headers=bearer("P00637")).json() == {"withdrawn": 1}
    assert c.post("/v1/w2/consents", json={"grantee_id": "P-NOBODY"}, headers=bearer("P00637")).status_code == 422
