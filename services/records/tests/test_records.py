"""Records service without a database or a model: parse, PHI tokens, injection filter, ingest, scope."""
import pytest

from services.common.embed import HashEmbedder
from services.common.phi import TokenMap, deidentify, known_identifiers, reidentify
from services.records import injection
from services.records.ingest import IngestRejected, ingest_file
from services.records.parse import parse_pdf, split_long
from services.records.store import InMemoryRecordStore, PatientIdentity

REDTEAM = "evals/sets/redteam/redteam_injection.pdf"
LAKSHMI = PatientIdentity("P00637", "Lakshmi Mehta", "+91 7824903518", "45-4959-3395-8681")
SUNITA = PatientIdentity("P-SUNITA", "Sunita Deshmukh", "+91 9120604074", "33-9770-4544-1067")
PRIYA = PatientIdentity("P-PRIYA", "Priya Deshmukh", "+91 9000000001", "11-1111-1111-1111")


@pytest.fixture
def store():
    return InMemoryRecordStore([LAKSHMI, SUNITA, PRIYA])


def test_parse_keeps_lab_values_on_their_own_lines():
    r = parse_pdf(REDTEAM)
    assert r.report_ref == "RT-0001" and r.report_date == "2026-10-20" and r.title == "Complete Blood Count"
    assert [s.heading for s in r.sections] == ["Report", "Impression"]
    assert r.sections[0].body.splitlines()[0] == "Haemoglobin: 12.1 g/dL (reference 12.0-15.5)"


def test_injection_sentences_removed_values_kept():
    body = parse_pdf(REDTEAM).sections[0].body
    clean, removed = injection.strip(body)
    assert len(removed) == 5
    assert "12.1 g/dL" in clean and "P-SUNITA" not in clean and "OVERRIDE" not in clean


def test_injection_filter_leaves_clinical_prose_alone():
    text = ("Patient was advised to ignore minor bruising. Repeat CBC in two weeks. "
            "Include iron studies at the next visit. The report was reviewed by the consultant.")
    assert injection.find(text) == []


def test_deidentify_known_identifiers_and_reidentify():
    known = known_identifiers(name="Sunita Deshmukh", phone="+91 9120604074", abha="33-9770-4544-1067")
    text = "Sunita Deshmukh (9120604074, ABHA 33-9770-4544-1067). Mrs Deshmukh reports cough."
    out, tokens = deidentify(text, known)
    assert "Sunita" not in out and "Deshmukh" not in out and "9120604074" not in out and "33-9770" not in out
    assert reidentify(out, tokens) == text


def test_same_value_same_token():
    t = TokenMap()
    assert t.token_for("PERSON", "Sunita") == t.token_for("PERSON", "sunita") == "<PERSON_1>"
    assert t.token_for("PERSON", "Priya") == "<PERSON_2>"


def test_split_long_respects_limit():
    parts = split_long("A short sentence. " * 200, limit=300)
    assert all(len(p) <= 300 for p in parts) and len(parts) > 5


def test_ingest_redteam_upload(store):
    r = ingest_file(store, HashEmbedder(), REDTEAM, "P00637", doc_type="upload")
    assert r["injection_removed"] == 5 and not r["existing"]
    chunks = [c for c in store._chunks if c.doc_id == r["doc_id"]]
    assert chunks and all("P-SUNITA" not in c.text and "OVERRIDE" not in c.text for c in chunks)
    assert all("P00637" not in c.text for c in chunks)                       # identifiers are tokens
    again = ingest_file(store, HashEmbedder(), REDTEAM, "P00637", doc_type="upload")
    assert again["existing"] and again["doc_id"] == r["doc_id"]              # re-upload is a no-op
    assert len(store.documents("P00637")) == 1


def test_ingest_refuses_document_naming_another_patient(store):
    with pytest.raises(IngestRejected):
        ingest_file(store, HashEmbedder(), REDTEAM, "P-SUNITA")
    assert store.documents("P-SUNITA") == []


def test_search_never_crosses_patients(store):
    emb = HashEmbedder()
    ingest_file(store, emb, REDTEAM, "P00637")
    assert store.search("P-SUNITA", emb.embed(["haemoglobin"])[0], 8) == []
    hits = store.search("P00637", emb.embed(["haemoglobin"])[0], 8)
    assert hits and {h.patient_id for h in hits} == {"P00637"}


def test_grant_states(store):
    store.add_consent("P-SUNITA", "P-PRIYA", state="valid")
    store.add_consent("P-PRIYA", "P-SUNITA", state="expired")
    store.add_consent("P00637", "P-PRIYA", state="revoked")
    assert store.grant("P-SUNITA", "P-SUNITA").state == "self"
    assert store.grant("P-SUNITA", "P-PRIYA").state == "valid"
    assert store.grant("P-PRIYA", "P-SUNITA").state == "expired"
    assert store.grant("P00637", "P-PRIYA").state == "revoked"
    assert store.grant("P00637", "P-SUNITA").state == "none"


def test_question_name_detection_ignores_lowercase_hinglish():
    from services.common.phi import _analyzer, person_names
    if _analyzer() is None:
        pytest.skip("spaCy model not installed")
    assert person_names("Sugar 147 aaya hai, kitna insulin lena chahiye?") == []
    assert person_names("What was Ramesh Kumar's creatinine?") == ["Ramesh Kumar"]
    out, _ = deidentify("Show me Sunita Deshmukh's echo", [], ner=True)
    assert out == "Show me <PERSON_1>'s echo"
