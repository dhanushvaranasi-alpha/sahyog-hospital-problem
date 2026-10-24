"""Synthetic patient master, built by code from the cleaned encounter history (ages and genders),
with Indian names, phones, ABHA-format ids and languages drawn from distributions. No LLM.

Includes the two pack personas: Priya (34), who manages the care of her mother (62, diabetic).
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from data.synthetic import names
from data.transforms.common import PROCESSED

SEED = 20261024
N_PATIENTS = 1000
AS_OF = date(2026, 10, 24)
PERSONAS = [
    {"patient_id": "P-PRIYA", "name": "Priya Deshmukh", "gender": "female", "age": 34, "city": "Pune", "language": "en"},
    {"patient_id": "P-SUNITA", "name": "Sunita Deshmukh", "gender": "female", "age": 62, "city": "Pune", "language": "mr"},
]


def _phone(rng: random.Random) -> str:
    return f"+91 {rng.choice('6789')}{rng.randrange(10**8, 10**9):09d}"


def _abha(rng: random.Random) -> str:
    d = f"{rng.randrange(10**13, 10**14)}"
    return f"{d[:2]}-{d[2:6]}-{d[6:10]}-{d[10:]}"


def _dob(rng: random.Random, age: int) -> date:
    return AS_OF - timedelta(days=age * 365 + rng.randrange(0, 365))


def build() -> pd.DataFrame:
    rng = random.Random(SEED)
    enc = pd.read_parquet(PROCESSED / "encounter_history.parquet")
    sample = enc.sample(N_PATIENTS - len(PERSONAS), random_state=SEED)
    rows, used = [], set()
    for i, r in enumerate(sample.itertuples(), start=1):
        city = "Pune" if r.hospital_id.startswith("H-PUN") else "Hyderabad"
        gender = "female" if r.gender == "Female" else "male"
        while True:
            first = rng.choice(names.FEMALE if gender == "female" else names.MALE)
            last = rng.choice(names.SURNAME_PUNE if city == "Pune" else names.SURNAME_HYD)
            if (first, last) not in used or len(used) > 5000:
                break
        used.add((first, last))
        local = "mr" if city == "Pune" else "te"
        language = rng.choices(["en", "hi", local], weights=[0.5, 0.25, 0.25])[0]
        rows.append({"patient_id": f"P{i:05d}", "name": f"{first} {last}", "gender": gender, "age": int(r.age),
                     "city": city, "language": language, "source_encounter_ref": int(r.encounter_ref)})
    for p in PERSONAS:
        rows.append(p | {"source_encounter_ref": None})
    df = pd.DataFrame(rows)
    df["dob"] = [_dob(rng, a) for a in df["age"]]
    df["phone"] = [_phone(rng) for _ in range(len(df))]
    df["abha_id"] = [_abha(rng) for _ in range(len(df))]
    df["synthetic"] = True
    return df


def persona_consent() -> dict:
    """Priya may read her mother's records as caregiver for 90 days (assumption A05)."""
    now = datetime(2026, 10, 24, tzinfo=timezone.utc)
    return {"patient_id": "P-SUNITA", "grantee_id": "P-PRIYA", "scope": "records:read", "purpose": "caregiver",
            "expires_at": now + timedelta(days=90)}
