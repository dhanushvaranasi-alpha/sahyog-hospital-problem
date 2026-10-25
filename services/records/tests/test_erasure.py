"""CR-001: erasure of an upload and consent withdrawal, end to end in memory."""
import shutil

import pytest

from services.agent.w2.answer import Answer, Citation
from services.agent.w2.graph import ask, build_ask_graph
from services.common.embed import CachedEmbedder, HashEmbedder
from services.records.erasure import ErasureRefused, erase_upload, grant_consent, withdraw_consent
from services.records.ingest import ingest_file
from services.records.store import InMemoryRecordStore, PatientIdentity

REDTEAM = "evals/sets/redteam/redteam_injection.pdf"


class Client:
    def structured(self, **kw):
        return Answer(route="answer", answer="Your haemoglobin was 12.1 g/dL.", citations=[Citation(report_id="RT-0001", page=1)])


@pytest.fixture
def env(tmp_path):
    store = InMemoryRecordStore([PatientIdentity("P00637", "Lakshmi Mehta", "+91 7824903518", "45-4959-3395-8681"),
                                 PatientIdentity("P-PRIYA", "Priya Deshmukh", None, None)])
    uploads = tmp_path / "uploads" / "P00637"
    uploads.mkdir(parents=True)
    pdf = uploads / "r.pdf"
    shutil.copy(REDTEAM, pdf)
    emb = CachedEmbedder(HashEmbedder(), cache_dir=tmp_path / "cache")
    doc_id = ingest_file(store, emb, pdf, "P00637", doc_type="upload")["doc_id"]
    return store, emb, tmp_path / "uploads", pdf, doc_id


def test_erasure_removes_every_derived_copy(env):
    store, emb, upload_dir, pdf, doc_id = env
    cached_before = len(list(emb.cache_dir.glob("*.npy")))
    r = erase_upload(store, patient_id="P00637", doc_id=doc_id, actor_id="P00637", upload_dir=upload_dir, embedder=emb)
    assert r.file_removed and not pdf.exists()
    assert r.chunks_removed == 2 and r.cache_entries_removed == 2
    assert len(list(emb.cache_dir.glob("*.npy"))) == cached_before - 2
    assert store.document(doc_id) is None and store.tokens([doc_id])[doc_id] == {}
    assert store.search("P00637", HashEmbedder().embed(["haemoglobin"])[0], 8) == []
    assert store.audit_log[-1]["action"] == "erase" and store.audit_log[-1]["resource_id"] == doc_id


def test_after_erasure_the_assistant_no_longer_finds_it(env):
    store, emb, upload_dir, _, doc_id = env
    g = build_ask_graph(store, Client(), HashEmbedder())
    assert ask(g, caller_id="P00637", subject_id="P00637", question="What was my haemoglobin?")["route"] == "answer"
    erase_upload(store, patient_id="P00637", doc_id=doc_id, actor_id="P00637", upload_dir=upload_dir, embedder=emb)
    assert ask(g, caller_id="P00637", subject_id="P00637", question="What was my haemoglobin?")["route"] == "not_in_record"


def test_cannot_erase_someone_elses_document(env):
    store, emb, upload_dir, _, doc_id = env
    with pytest.raises(LookupError):
        erase_upload(store, patient_id="P-PRIYA", doc_id=doc_id, actor_id="P-PRIYA", upload_dir=upload_dir, embedder=emb)
    assert store.document(doc_id) is not None


def test_hospital_reports_are_not_erased_here(env):
    store, emb, upload_dir, _, doc_id = env
    store._docs[doc_id].type = "report"
    with pytest.raises(ErasureRefused):
        erase_upload(store, patient_id="P00637", doc_id=doc_id, actor_id="P00637", upload_dir=upload_dir, embedder=emb)


def test_file_outside_the_upload_folder_is_never_deleted(env, tmp_path):
    store, emb, upload_dir, _, doc_id = env
    outside = tmp_path / "elsewhere.pdf"
    shutil.copy(REDTEAM, outside)
    store._docs[doc_id].uri = str(outside)
    r = erase_upload(store, patient_id="P00637", doc_id=doc_id, actor_id="P00637", upload_dir=upload_dir, embedder=emb)
    assert outside.exists() and not r.file_removed and store.document(doc_id) is None


def test_withdrawal_is_as_easy_as_granting_and_takes_effect_at_once(env):
    store, *_ = env
    g = build_ask_graph(store, Client(), HashEmbedder())
    grant_consent(store, subject_id="P00637", grantee_id="P-PRIYA", days=30, actor_id="P00637")
    assert ask(g, caller_id="P-PRIYA", subject_id="P00637", question="What was her haemoglobin?")["route"] == "answer"
    assert withdraw_consent(store, subject_id="P00637", grantee_id="P-PRIYA", actor_id="P00637") == 1
    assert ask(g, caller_id="P-PRIYA", subject_id="P00637", question="What was her haemoglobin?")["route"] == "refuse"
    assert [a["action"] for a in store.audit_log if a["resource_type"] == "consent"] == ["grant", "revoke"]
