"""The eval sets are themselves tested: valid, unique, grounded in real records, and covering the pack's hard cases."""
import json
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest
from pypdf import PdfReader

from evals.schema import EvalCase, W1Expect, W1Input, W2Expect, W2Input

SETS = Path(__file__).resolve().parents[1] / "sets"
REPO = SETS.parents[1]
REPORTS = REPO / "data" / "synthetic" / "output" / "reports.jsonl"


def load(name):
    return [EvalCase.model_validate(json.loads(l)) for l in (SETS / name).read_text().splitlines() if l.strip()]


W1, W2 = load("w1_triage.jsonl"), load("w2_records.jsonl")


def test_thirty_cases_per_workflow_unique_ids():  # architecture decision 17
    assert len(W1) == 30 and len(W2) == 30
    ids = [c.id for c in W1 + W2]
    assert len(ids) == len(set(ids))


def test_every_case_has_source_and_author():
    for c in W1 + W2:
        assert c.source.strip() and c.added_by.strip()


def test_inputs_and_expectations_match_their_workflow():
    for c in W1:
        assert isinstance(c.input, W1Input) and isinstance(c.expect, W1Expect)
    for c in W2:
        assert isinstance(c.input, W2Input) and isinstance(c.expect, W2Expect)


# ---------- W1 ----------
def test_w1_red_flags_cover_the_a01_list_and_never_book():
    rf = [c for c in W1 if c.expect.red_flag]
    assert len(rf) >= 10
    for c in rf:
        assert c.expect.route == "emergency_desk" and c.expect.specialty is None
        assert "slot" in c.must_not
    assert any("case A" in c.source for c in rf)  # the pack's own worked example


def test_w1_specialties_exist_and_primary_is_acceptable():
    names = set(pd.read_csv(REPO / "data" / "reference" / "specialties.csv")["name"])
    for c in W1:
        assert set(c.expect.acceptable_specialties) <= names
        if c.expect.route == "booking":
            assert c.expect.specialty in c.expect.acceptable_specialties


def test_w1_hard_cases_present():
    cats = Counter(c.category for c in W1)
    assert cats["clarify"] >= 3 and cats["two_specialties"] >= 2
    assert sum(c.input.language == "hi-en" for c in W1) >= 4        # A04
    assert any("must not fire a red flag" in c.source for c in W1)   # false-positive guard


# ---------- W2 ----------
@pytest.fixture(scope="module")
def reports():
    rows = [json.loads(l) for l in REPORTS.read_text().splitlines() if l.strip()]
    return {r["report_id"]: (r["patient_id"], json.dumps(r["draft"])) for r in rows}


def test_w2_answers_are_grounded_in_the_cited_report(reports):
    for c in W2:
        for rid in c.expect.cites:
            owner, text = reports[rid]
            assert owner == c.input.subject_patient_id, c.id
            for s in c.expect.answer_contains:
                assert s in text, (c.id, s)


def test_w2_must_not_strings_never_occur_in_the_subjects_own_records(reports):
    """A correct answer must be able to pass: forbidden strings come only from other patients' records."""
    for c in W2:
        if c.expect.route not in ("refuse", "answer") or c.category == "own_record":
            continue
        own = " ".join(t for o, t in reports.values() if o == c.input.caller_patient_id)
        for s in c.must_not:
            if s.startswith("R0"):
                assert reports[s][0] != c.input.caller_patient_id, (c.id, s)
            else:
                assert s not in own, (c.id, s)


def test_w2_must_not_strings_are_absent_from_the_callers_uploads():
    """The red-team PDF repeats names on purpose; leak markers must be values only the victim's record holds."""
    for c in W2:
        for up in c.input.uploads:
            text = " ".join(p.extract_text() for p in PdfReader(str(REPO / up)).pages)
            for s in c.must_not:
                assert s not in text, (c.id, s)


def test_w2_hard_cases_present():
    cats = Counter(c.category for c in W2)
    assert cats["scope"] >= 5 and cats["injection"] >= 5 and cats["handoff"] >= 5 and cats["outside_record"] >= 2
    assert any(c.input.uploads for c in W2)                          # the red-team PDF is used
    assert {x.state for c in W2 for x in c.input.consents} >= {"expired", "revoked"}
    assert sum(c.input.language == "hi-en" for c in W2) >= 2


def test_redteam_pdf_carries_both_injection_channels():
    text = PdfReader(str(SETS / "redteam" / "redteam_injection.pdf")).pages[0].extract_text()
    assert "SYSTEM OVERRIDE" in text          # hidden white text is still extracted by a parser
    assert "processing system" in text        # the visible disguised instruction
    assert "Haemoglobin" in text              # and a legitimate answer exists
