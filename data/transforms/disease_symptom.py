"""Disease Symptom Prediction -> long-form (condition, symptom, severity).

Known mess (pack p19): wide symptom columns with stray spaces and underscores.
Found in this copy: 4,616 of 4,920 rows are exact duplicates; two disease names
carry trailing spaces.
"""
from __future__ import annotations

import re

import pandas as pd

from .common import Tally


def norm_symptom(s: str) -> str:
    """' dischromic _patches' -> 'dischromic_patches'; 'foul_smell_of urine' -> 'foul_smell_of_urine'."""
    s = s.strip().lower()
    s = re.sub(r"\s*_\s*", "_", s)
    return re.sub(r"\s+", "_", s)


def clean(raw: pd.DataFrame, severity: pd.DataFrame) -> tuple[pd.DataFrame, Tally]:
    t = Tally("disease_symptom", rows_in=len(raw))
    df = raw.copy()
    df["Disease"] = df["Disease"].str.strip()
    df = t.drop(df, df.duplicated(), "exact duplicate row")

    long = df.melt(id_vars="Disease", value_name="symptom").dropna(subset=["symptom"])
    long["symptom"] = long["symptom"].map(norm_symptom)
    long = long.drop_duplicates(["Disease", "symptom"])

    sev = severity.assign(symptom=severity["Symptom"].map(norm_symptom)).drop_duplicates("symptom")
    long = long.merge(sev[["symptom", "weight"]], on="symptom", how="left")
    t.notes.append(f"melted {len(df)} unique rows to {len(long)} (condition, symptom) pairs")

    out = long.rename(columns={"Disease": "condition", "weight": "severity"})[["condition", "symptom", "severity"]]
    out["severity"] = out["severity"].astype("Int64")
    out = out.sort_values(["condition", "symptom"]).reset_index(drop=True)
    # Row accounting is on the wide table; the long table is reported in notes.
    t.rows_out = len(df)
    return out, t
