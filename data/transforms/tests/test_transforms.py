"""Unit tests: each transform on a small hand-built frame (pack p19: every check becomes a test)."""
import pandas as pd
import pytest

from data.transforms import az_medicine, disease_symptom, healthcare, no_shows, transcriptions

CLINICS = ["C-1", "C-2"]
HOSPITALS = ["H-1", "H-2", "H-3"]


def _ns(**over):
    row = {"PatientId": 1.0, "AppointmentID": 1, "Gender": "F", "ScheduledDay": "2016-04-29T10:00:00Z",
           "AppointmentDay": "2016-04-30T00:00:00Z", "Age": 30, "Neighbourhood": "A", "Scholarship": 0,
           "Hipertension": 0, "Diabetes": 0, "Alcoholism": 0, "Handcap": 0, "SMS_received": 1, "No-show": "No"}
    row.update(over)
    return row


def test_no_shows_drops_impossible_rows_with_reasons():
    raw = pd.DataFrame([_ns(), _ns(AppointmentID=2, Age=-1), _ns(AppointmentID=3, Age=115),
                        _ns(AppointmentID=4, ScheduledDay="2016-05-02T09:00:00Z")])
    out, t = no_shows.clean(raw, CLINICS)
    assert len(out) == 1
    assert t.dropped == {"negative age": 1, "age above 110": 1, "scheduled after the visit day": 1}
    assert t.balanced()


def test_no_shows_target_is_inverted_to_attended():
    raw = pd.DataFrame([_ns(), _ns(AppointmentID=2, **{"No-show": "Yes"})])
    out, _ = no_shows.clean(raw, CLINICS)
    assert out.set_index("history_id")["attended"].to_dict() == {1: True, 2: False}
    assert set(out["clinic_id"]) <= set(CLINICS)


@pytest.mark.parametrize("raw,expected", [
    (" dischromic _patches", "dischromic_patches"),
    (" spotting_ urination", "spotting_urination"),
    ("foul_smell_of urine", "foul_smell_of_urine"),
    ("itching", "itching"),
])
def test_symptom_names_normalised(raw, expected):
    assert disease_symptom.norm_symptom(raw) == expected


def test_disease_duplicates_dropped_and_names_stripped():
    raw = pd.DataFrame({"Disease": ["Diabetes ", "Diabetes ", "Acne"],
                        "Symptom_1": [" fatigue", " fatigue", "skin_rash"], "Symptom_2": [None, None, None]})
    sev = pd.DataFrame({"Symptom": ["fatigue", "skin_rash"], "weight": [4, 3]})
    out, t = disease_symptom.clean(raw, sev)
    assert t.dropped == {"exact duplicate row": 1}
    assert set(out["condition"]) == {"Diabetes", "Acne"}
    assert out["severity"].notna().all()


def test_transcription_layout_repaired():
    s = "DOPPLER: , ,1.  Mild regurgitation.,2.  Trace regurgitation."
    assert transcriptions.repair_layout(s) == "DOPPLER:\n1. Mild regurgitation.\n2. Trace regurgitation."


def test_transcription_duplicate_keeps_specific_label():
    raw = pd.DataFrame({"Unnamed: 0": [0, 1], "description": ["d", "d"],
                        "medical_specialty": [" Surgery", " Gastroenterology"],
                        "sample_name": ["EGD", "EGD"], "transcription": ["same text", "same text"], "keywords": [None, None]})
    out, t = transcriptions.clean(raw)
    assert len(out) == 1 and out.loc[0, "specialty"] == "Gastroenterology"
    assert t.balanced()


def test_transcription_unknown_label_fails_loudly():
    raw = pd.DataFrame({"description": ["d"], "medical_specialty": ["Astrology"], "sample_name": ["x"],
                        "transcription": ["t"], "keywords": [None]})
    with pytest.raises(ValueError, match="unmapped"):
        transcriptions.clean(raw)


def _hc(**over):
    row = {"Name": "bOBby jacKSon", "Age": 30, "Gender": "Male", "Blood Type": "B-", "Medical Condition": "Cancer",
           "Date of Admission": "2024-01-31", "Doctor": "X", "Hospital": "Sons and Miller", "Insurance Provider": "Y",
           "Billing Amount": 100.0, "Room Number": 1, "Admission Type": "Urgent", "Discharge Date": "2024-02-02",
           "Medication": "Paracetamol", "Test Results": "Normal"}
    row.update(over)
    return row


def test_healthcare_dedup_date_order_and_mapping():
    raw = pd.DataFrame([_hc(), _hc(), _hc(Name="a", **{"Discharge Date": "2024-01-01"})])
    out, t = healthcare.clean(raw, HOSPITALS)
    assert t.dropped == {"exact duplicate row": 1, "discharge before admission": 1}
    assert out.loc[0, "patient_name"] == "Bobby Jackson"
    assert "Billing Amount" not in out.columns and "billing" not in " ".join(out.columns)
    assert out.loc[0, "hospital_id"] == healthcare.stable_pick("Sons and Miller", HOSPITALS)


@pytest.mark.parametrize("label,expected", [
    ("strip of 10 tablets", (10.0, "tablets")),
    ("bottle of 200 ml Syrup", (200.0, "ml syrup")),
    ("tube of 20 gm Gel", (20.0, "gm gel")),
    (None, (None, None)),
])
def test_pack_size_parsed(label, expected):
    assert az_medicine.parse_pack(label) == expected


def test_composition_key_is_order_independent():
    assert az_medicine.composition_key("Amoxycillin (500mg)", "Clavulanic Acid (125mg)") == \
        az_medicine.composition_key("Clavulanic Acid  (125mg)", "Amoxycillin (500mg)")


def test_az_drops_non_positive_price():
    raw = pd.DataFrame({"id": [1, 2], "name": ["A", "B"], "price(₹)": [10.0, 0.0], "Is_discontinued": [False, False],
                        "manufacturer_name": ["M", "M"], "type": ["allopathy"] * 2,
                        "pack_size_label": ["strip of 10 tablets"] * 2, "short_composition1": ["X (1mg)"] * 2,
                        "short_composition2": [None, None]})
    out, t = az_medicine.clean(raw)
    assert len(out) == 1 and t.dropped == {"price not positive": 1}
