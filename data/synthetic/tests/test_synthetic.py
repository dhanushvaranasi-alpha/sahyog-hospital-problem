"""Audits of the generated layer (pack p20): schema, coverage, duplicates and bias, and the D5 checks."""
import json
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

from data.synthetic import doctors, patients, reports, slots
from data.synthetic.schemas import DoctorDraft, ReportDraft
from data.transforms.common import PROCESSED, REFERENCE

OUT = Path(doctors.__file__).resolve().parent / "output"
needs_processed = pytest.mark.skipif(not (PROCESSED / "encounter_history.parquet").exists(),
                                     reason="run python -m data.transforms.run first")
needs_doctors = pytest.mark.skipif(not (OUT / "doctors.jsonl").exists(), reason="run python -m data.synthetic.doctors first")
needs_reports = pytest.mark.skipif(not (OUT / "reports.jsonl").exists(), reason="run python -m data.synthetic.reports first")


def _jsonl(name):
    return [json.loads(l) for l in (OUT / name).read_text().splitlines() if l.strip()]


# ---------- plan (code, no LLM) ----------
def test_plan_is_deterministic_and_complete():
    a, b = doctors.plan(), doctors.plan()
    assert a.equals(b) and len(a) == doctors.TOTAL


def test_every_specialty_has_at_least_ten_doctors():  # D5 check
    counts = doctors.plan()["specialty_id"].value_counts()
    assert len(counts) == len(pd.read_csv(REFERENCE / "specialties.csv"))
    assert counts.min() >= 10


def test_every_site_has_doctors():
    assert set(doctors.plan()["clinic_id"]) == set(pd.read_csv(REFERENCE / "sites.csv")["site_id"])


def test_every_site_has_slots_on_every_working_day():  # D5 check
    cal = slots.build(doctors.plan())
    cal["day"] = cal["starts_at"].map(lambda t: t.date())
    per = cal.groupby(["clinic_id", "day"]).size()
    assert len(per) == 28 * len(slots.working_days())
    assert all(d.weekday() < 6 for d in slots.working_days())


def test_sixteen_slots_per_doctor_per_day():
    cal = slots.build(doctors.plan().head(3))
    assert set(cal.groupby(["doctor_id", cal["starts_at"].map(lambda t: t.date())]).size()) == {16}


# ---------- generated doctors (LLM) ----------
@needs_doctors
def test_generated_doctors_valid_and_tagged():
    rows = _jsonl("doctors.jsonl")
    assert len(rows) == doctors.TOTAL, "missing rows: rerun the generator, it resumes"
    for r in rows:
        DoctorDraft(slot=0, name=r["name"], gender=r["gender"], languages=r["languages"],
                    years_in_practice=r["years_in_practice"])
        assert r["synthetic"] is True and r["prompt_version"] == "doctors_v1"


@needs_doctors
def test_doctor_names_rarely_repeat():
    names = Counter(r["name"] for r in _jsonl("doctors.jsonl"))
    assert sum(n - 1 for n in names.values()) <= 0.02 * doctors.TOTAL


@needs_doctors
def test_doctor_gender_mix_per_specialty_is_not_skewed_overall():
    g = Counter(r["gender"] for r in _jsonl("doctors.jsonl"))
    assert 0.35 <= g["female"] / sum(g.values()) <= 0.65


@needs_doctors
def test_doctor_languages_fit_their_city():
    sites = pd.read_csv(REFERENCE / "sites.csv").set_index("site_id")["city"]
    rows = _jsonl("doctors.jsonl")
    pune = [r for r in rows if sites[r["clinic_id"]] == "Pune"]
    hyd = [r for r in rows if sites[r["clinic_id"]] == "Hyderabad"]
    assert sum(("mr" in r["languages"] or "hi" in r["languages"]) for r in pune) / len(pune) >= 0.7
    assert sum(("te" in r["languages"] or "hi" in r["languages"]) for r in hyd) / len(hyd) >= 0.7


# ---------- patients (code) ----------
@needs_processed
def test_patients_include_the_personas_and_are_synthetic():
    p = patients.build()
    assert len(p) == patients.N_PATIENTS and p["patient_id"].is_unique and p["synthetic"].all()
    assert {"P-PRIYA", "P-SUNITA"} <= set(p["patient_id"])
    assert p["abha_id"].str.fullmatch(r"\d{2}-\d{4}-\d{4}-\d{4}").all()
    assert p["phone"].str.fullmatch(r"\+91 [6-9]\d{9}").all()


@needs_processed
def test_patient_language_mix():
    share = patients.build()["language"].value_counts(normalize=True)
    assert 0.35 <= share["en"] <= 0.65 and share.get("mr", 0) > 0.05 and share.get("te", 0) > 0.05


# ---------- reports (LLM text, code layout) ----------
@needs_reports
def test_reports_valid_and_cover_the_plan():
    rows = _jsonl("reports.jsonl")
    assert len(rows) == 100
    for r in rows:
        ReportDraft.model_validate(r["draft"])
        assert r["synthetic"] is True
    assert sum(r["patient_id"] == "P-SUNITA" for r in rows) == 4


@needs_reports
@needs_processed
def test_llm_text_carries_no_patient_identifiers():
    pts = patients.build().set_index("patient_id")
    for r in _jsonl("reports.jsonl"):
        text = json.dumps(r["draft"])
        p = pts.loc[r["patient_id"]]
        assert p["phone"] not in text and p["abha_id"] not in text and p["name"] not in text


@needs_reports
@needs_processed
def test_a_report_renders_to_pdf(tmp_path):
    row = _jsonl("reports.jsonl")[0]
    p = patients.build().set_index("patient_id").loc[row["patient_id"]].to_dict()
    path = reports.render(row, p, "Sahyog Hospital Shivajinagar", out_dir=tmp_path)
    assert path.stat().st_size > 1000 and path.read_bytes()[:4] == b"%PDF"


# ---------- budget ----------
def test_llm_spend_is_under_the_hard_stop():
    from services.common.llm import spent_usd
    assert spent_usd() < 2.00
