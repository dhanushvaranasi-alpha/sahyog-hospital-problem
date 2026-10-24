"""Run every transform on data/raw/ and write data/processed/.

    python -m data.transforms.run

Writes one parquet per source, one tally per source, and data/processed/report.json.
"""
from __future__ import annotations

import json

import pandas as pd

from . import az_medicine, disease_symptom, healthcare, no_shows, transcriptions
from .common import PROCESSED, RAW, REFERENCE, write


def sites() -> pd.DataFrame:
    return pd.read_csv(REFERENCE / "sites.csv")


def main() -> dict:
    s = sites()
    clinics = s.loc[s["kind"] == "clinic", "site_id"].tolist()
    hospitals = s.loc[s["kind"] == "hospital", "site_id"].tolist()

    results = {}
    df, t = no_shows.clean(pd.read_csv(RAW / "no_shows" / "KaggleV2-May-2016.csv"), clinics)
    write(df, "appointment_history", t); results["no_shows"] = t

    df, t = disease_symptom.clean(
        pd.read_csv(RAW / "disease_symptom" / "dataset.csv"),
        pd.read_csv(RAW / "disease_symptom" / "Symptom-severity.csv"),
    )
    write(df, "condition_symptom", t); results["disease_symptom"] = t

    df, t = transcriptions.clean(pd.read_csv(RAW / "transcriptions" / "mtsamples.csv"))
    write(df, "transcription_note", t); results["transcriptions"] = t

    df, t = healthcare.clean(pd.read_csv(RAW / "healthcare" / "healthcare_dataset.csv"), hospitals)
    write(df, "encounter_history", t); results["healthcare"] = t

    df, t = az_medicine.clean(pd.read_csv(RAW / "az_medicine" / "A_Z_medicines_dataset_of_India.csv"))
    write(df, "medicine", t); results["az_medicine"] = t

    report = {k: v.as_dict() | {"balanced": v.balanced()} for k, v in results.items()}
    PROCESSED.mkdir(parents=True, exist_ok=True)
    (PROCESSED / "report.json").write_text(json.dumps(report, indent=2))
    for k, v in report.items():
        print(f"{k:16s} in {v['rows_in']:>8,}  out {v['rows_out']:>8,}  dropped {v['dropped']}")
    return report


if __name__ == "__main__":
    main()
