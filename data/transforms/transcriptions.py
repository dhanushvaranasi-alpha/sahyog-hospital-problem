"""Medical Transcriptions (mtsamples) -> de-duplicated notes with a normalised specialty.

Known mess (pack p19): template headers flattened into the body, forty uneven
specialty labels, duplicates. Found in this copy: 2,641 notes repeat, usually the
same note filed under a generic label (e.g. "Surgery") and a specific one.

These notes are only seed text for synthetic reports. The Presidio scrub the pack
lists for this source runs in the egress scrubber (PR #6), before any text leaves.
"""
from __future__ import annotations

import re

import pandas as pd

from .common import Tally

# Source label -> network specialty (None = a document type, not a specialty).
SPECIALTY_MAP: dict[str, str | None] = {
    "Allergy / Immunology": "Allergy & Immunology",
    "Bariatrics": "Bariatric Surgery",
    "Cardiovascular / Pulmonary": "Cardiology",
    "Chiropractic": "Physiotherapy & Rehabilitation",
    "Consult - History and Phy.": None,
    "Cosmetic / Plastic Surgery": "Plastic Surgery",
    "Dentistry": "Dentistry",
    "Dermatology": "Dermatology",
    "Diets and Nutritions": "Dietetics & Nutrition",
    "Discharge Summary": None,
    "ENT - Otolaryngology": "ENT",
    "Emergency Room Reports": "Emergency Medicine",
    "Endocrinology": "Endocrinology",
    "Gastroenterology": "Gastroenterology",
    "General Medicine": "General Medicine",
    "Hematology - Oncology": "Haematology & Oncology",
    "Hospice - Palliative Care": "Palliative Care",
    "IME-QME-Work Comp etc.": None,
    "Lab Medicine - Pathology": "Pathology",
    "Letters": None,
    "Nephrology": "Nephrology",
    "Neurology": "Neurology",
    "Neurosurgery": "Neurosurgery",
    "Obstetrics / Gynecology": "Obstetrics & Gynaecology",
    "Office Notes": None,
    "Ophthalmology": "Ophthalmology",
    "Orthopedic": "Orthopaedics",
    "Pain Management": "Pain Management",
    "Pediatrics - Neonatal": "Paediatrics",
    "Physical Medicine - Rehab": "Physiotherapy & Rehabilitation",
    "Podiatry": "Orthopaedics",
    "Psychiatry / Psychology": "Psychiatry",
    "Radiology": "Radiology",
    "Rheumatology": "Rheumatology",
    "SOAP / Chart / Progress Notes": None,
    "Sleep Medicine": "Sleep Medicine",
    "Speech - Language": "Speech & Language Therapy",
    "Surgery": "General Surgery",
    "Urology": "Urology",
}
# Labels that describe a document, not care; dropped with a tally.
EXCLUDED_LABELS = {"Autopsy"}
# Generic labels lose to a specific one when the same note appears twice.
GENERIC_LABELS = {"Surgery", "Consult - History and Phy.", "SOAP / Chart / Progress Notes",
                  "Discharge Summary", "Office Notes", "Letters", "General Medicine"}


def repair_layout(text: str) -> str:
    """Restore line breaks the CSV export flattened: 'DOPPLER: , ,1. x.,2. y.' -> lines."""
    text = re.sub(r":\s*,\s*(?:,\s*)?", ":\n", text)
    text = re.sub(r"\.,(?=\S)", ".\n", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, Tally]:
    t = Tally("transcriptions", rows_in=len(raw))
    df = raw.drop(columns=[c for c in raw.columns if c.startswith("Unnamed")]).copy()
    df["label"] = df["medical_specialty"].str.strip()

    unknown = set(df["label"]) - set(SPECIALTY_MAP) - EXCLUDED_LABELS
    if unknown:
        raise ValueError(f"unmapped specialty labels: {sorted(unknown)}")

    df = t.drop(df, df["transcription"].isna(), "empty transcription")
    df = t.drop(df, df["label"].isin(EXCLUDED_LABELS), "not a patient-care document (autopsy)")

    # Repair first, then de-duplicate: some copies differ only in spacing.
    df["text"] = df["transcription"].map(repair_layout)
    df["_generic"] = df["label"].isin(GENERIC_LABELS)
    df = df.sort_values(["_generic", "label"], kind="stable")
    df = t.drop(df, df["text"].duplicated(keep="first"), "duplicate note (kept the most specific label)")

    df["specialty"] = df["label"].map(SPECIALTY_MAP)
    df["doc_type"] = df["label"].where(df["specialty"].isna(), "clinical note")
    out = df.rename(columns={"sample_name": "title"})[["title", "label", "specialty", "doc_type", "description", "text", "keywords"]]
    out = out.sort_index().reset_index(drop=True)
    out.insert(0, "note_id", range(1, len(out) + 1))
    t.rows_out = len(out)
    t.notes.append(f"{df['label'].nunique()} source labels mapped to {out['specialty'].nunique()} specialties plus document types")
    return out, t
