"""Healthcare Dataset (synthetic) -> encounter history mapped to the network.

Known mess (pack p19): random-case names, discharge before admission, coarse test
results. Found in this copy: 534 exact duplicate rows, 108 negative bills, no
discharge-before-admission rows, ~39,900 random hospital names.
Billing and insurance are out of scope (p4), so those columns are dropped.
"""
from __future__ import annotations

import hashlib

import pandas as pd

from .common import Tally


def stable_pick(key: str, options: list[str]) -> str:
    """Deterministic mapping that does not depend on row order or Python's hash seed."""
    h = int(hashlib.sha1(key.encode("utf-8")).hexdigest(), 16)
    return options[h % len(options)]


def clean(raw: pd.DataFrame, hospital_ids: list[str]) -> tuple[pd.DataFrame, Tally]:
    t = Tally("healthcare", rows_in=len(raw))
    df = raw.copy()
    df["admitted_on"] = pd.to_datetime(df["Date of Admission"])
    df["discharged_on"] = pd.to_datetime(df["Discharge Date"])

    df = t.drop(df, df.duplicated(subset=list(raw.columns)), "exact duplicate row")
    df = t.drop(df, df["discharged_on"] < df["admitted_on"], "discharge before admission")

    out = pd.DataFrame(
        {
            "patient_name": df["Name"].str.strip().str.title(),
            "age": df["Age"].astype("int64"),
            "gender": df["Gender"],
            "blood_type": df["Blood Type"],
            "condition": df["Medical Condition"],
            "admission_type": df["Admission Type"],
            "admitted_on": df["admitted_on"].dt.date,
            "discharged_on": df["discharged_on"].dt.date,
            "medication": df["Medication"],
            "test_result": df["Test Results"],
            "hospital_id": df["Hospital"].map(lambda h: stable_pick(str(h), hospital_ids)),
        }
    ).reset_index(drop=True)
    out.insert(0, "encounter_ref", range(1, len(out) + 1))
    t.rows_out = len(out)
    t.notes.append("billing, insurance, room and source doctor columns dropped: out of scope (p4)")
    t.notes.append(f"{df['Hospital'].nunique()} source hospital names mapped to {len(hospital_ids)} network hospitals")
    return out, t
