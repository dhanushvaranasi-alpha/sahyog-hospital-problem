"""Load the generated layer into Postgres: doctors, patients, slots and the persona consent.

    python -m data.synthetic.load      # after python -m data.load
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv

from data.load import upsert
from data.synthetic import patients, slots
from data.transforms.common import REPO

DOCTORS = Path(__file__).resolve().parent / "output" / "doctors.jsonl"


def doctors_frame() -> pd.DataFrame:
    rows = [json.loads(l) for l in DOCTORS.read_text().splitlines() if l.strip()]
    df = pd.DataFrame(rows)
    return df[["doctor_id", "name", "specialty_id", "clinic_id", "languages", "years_in_practice", "synthetic"]]


def main(database_url: str | None = None) -> dict[str, int]:
    load_dotenv(REPO / ".env")
    url = database_url or os.environ["DATABASE_URL"]
    docs = doctors_frame()
    pts = patients.build()[["patient_id", "abha_id", "name", "dob", "phone", "language", "synthetic"]]
    cal = slots.build(docs)
    c = patients.persona_consent()
    counts = {}
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        counts["doctor"] = upsert(cur, "doctor", docs, ["doctor_id"])
        counts["patient"] = upsert(cur, "patient", pts, ["patient_id"])
        counts["slot"] = upsert(cur, "slot", cal, ["doctor_id", "starts_at"])
        cur.execute(
            "INSERT INTO consent (patient_id, grantee_id, scope, purpose, expires_at) "
            "SELECT %(patient_id)s, %(grantee_id)s, %(scope)s, %(purpose)s, %(expires_at)s "
            "WHERE NOT EXISTS (SELECT 1 FROM consent WHERE patient_id = %(patient_id)s AND grantee_id = %(grantee_id)s "
            "AND scope = %(scope)s AND revoked_at IS NULL)", c)
        cur.execute("SELECT count(*) FROM consent")
        counts["consent"] = cur.fetchone()[0]
        conn.commit()
    for k, v in counts.items():
        print(f"{k:10s} {v:>8,}")
    return counts


if __name__ == "__main__":
    main()
