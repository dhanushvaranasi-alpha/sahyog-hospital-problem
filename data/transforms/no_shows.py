"""Medical Appointment No Shows -> appointment history with an `attended` flag.

Known mess (pack p19): negative ages, schedule dates after the visit date, and a
target column that reads backwards ("No-show" = "Yes" means the patient did NOT come).
"""
from __future__ import annotations

import pandas as pd

from .common import Tally

MAX_PLAUSIBLE_AGE = 110


def clean(raw: pd.DataFrame, clinic_ids: list[str]) -> tuple[pd.DataFrame, Tally]:
    t = Tally("no_shows", rows_in=len(raw))
    df = raw.copy()
    df["scheduled_at"] = pd.to_datetime(df["ScheduledDay"], utc=True)
    df["appointment_day"] = pd.to_datetime(df["AppointmentDay"], utc=True).dt.normalize()

    df = t.drop(df, df["Age"] < 0, "negative age")
    df = t.drop(df, df["Age"] > MAX_PLAUSIBLE_AGE, f"age above {MAX_PLAUSIBLE_AGE}")
    df = t.drop(df, df["scheduled_at"].dt.normalize() > df["appointment_day"], "scheduled after the visit day")

    # The source target reads backwards: rename it to what it means.
    df["attended"] = df["No-show"].map({"No": True, "Yes": False})
    t.notes.append("'No-show' renamed to 'attended' and inverted (No -> True)")

    # 81 Brazilian neighbourhoods -> the network's 22 clinics, busiest first, round-robin.
    order = df["Neighbourhood"].value_counts().index.tolist()
    mapping = {n: clinic_ids[i % len(clinic_ids)] for i, n in enumerate(order)}
    df["clinic_id"] = df["Neighbourhood"].map(mapping)
    t.notes.append(f"{len(order)} neighbourhoods mapped to {len(clinic_ids)} fictional clinics")

    out = pd.DataFrame(
        {
            "history_id": df["AppointmentID"].astype("int64"),
            "source_patient_ref": df["PatientId"].astype("int64").astype("string"),
            "gender": df["Gender"],
            "age": df["Age"].astype("int64"),
            "scheduled_at": df["scheduled_at"],
            "appointment_day": df["appointment_day"],
            "lead_days": (df["appointment_day"] - df["scheduled_at"].dt.normalize()).dt.days.astype("int64"),
            "sms_received": df["SMS_received"].astype(bool),
            "clinic_id": df["clinic_id"],
            "attended": df["attended"].astype(bool),
        }
    )
    t.rows_out = len(out)
    return out, t
