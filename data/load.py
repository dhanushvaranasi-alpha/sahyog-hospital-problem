"""Apply the schema and load reference data plus cleaned source history into Postgres.

    docker compose -f infra/docker-compose.yml up -d
    python -m data.transforms.run      # raw -> data/processed/
    python -m data.load                # data/processed/ + data/reference/ -> Postgres

Idempotent: reference tables are upserted, source-history tables are replaced.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv

from data.transforms.common import PROCESSED, REFERENCE, REPO

SCHEMA = REPO / "infra" / "db" / "init" / "002-schema.sql"


def _null(v):
    """Map every pandas/numpy missing marker (None, NaN, NaT, pd.NA) to SQL NULL."""
    if isinstance(v, (list, tuple, dict)):
        return v
    try:
        return None if pd.isna(v) else v
    except (TypeError, ValueError):
        return v


def _rows(df: pd.DataFrame):
    for rec in df.itertuples(index=False, name=None):
        yield tuple(_null(v) for v in rec)


def upsert(cur: psycopg.Cursor, table: str, df: pd.DataFrame, key: list[str]) -> int:
    cols = list(df.columns)
    cur.execute(f"CREATE TEMP TABLE _stage (LIKE {table} INCLUDING DEFAULTS) ON COMMIT DROP")
    with cur.copy(f"COPY _stage ({', '.join(cols)}) FROM STDIN") as cp:
        for row in _rows(df):
            cp.write_row(row)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in key) or f"{key[0]} = EXCLUDED.{key[0]}"
    cur.execute(
        f"INSERT INTO {table} ({', '.join(cols)}) SELECT {', '.join(cols)} FROM _stage "
        f"ON CONFLICT ({', '.join(key)}) DO UPDATE SET {updates}"
    )
    n = cur.rowcount
    cur.execute("DROP TABLE _stage")
    return n


def replace(cur: psycopg.Cursor, table: str, df: pd.DataFrame) -> int:
    cur.execute(f"TRUNCATE {table}")
    with cur.copy(f"COPY {table} ({', '.join(df.columns)}) FROM STDIN") as cp:
        for row in _rows(df):
            cp.write_row(row)
    return len(df)


def main(database_url: str | None = None) -> dict[str, int]:
    load_dotenv(REPO / ".env")
    url = database_url or os.environ["DATABASE_URL"]
    sites = pd.read_csv(REFERENCE / "sites.csv")
    specialties = pd.read_csv(REFERENCE / "specialties.csv")
    by_name = dict(zip(specialties["name"], specialties["specialty_id"]))
    xw = pd.read_csv(REFERENCE / "condition_specialty_crosswalk.csv", dtype=str, keep_default_na=False)
    crosswalk = pd.DataFrame({
        "condition": xw["condition"],
        "display_name": xw["display_name"],
        "specialty_id": xw["specialty"].map(by_name),
        "alternative_specialty_id": xw["alternative_specialty"].map(lambda s: by_name.get(s) if s else None),
        "emergency_condition": xw["emergency_condition"].eq("true"),
        "drafted_by": xw["drafted_by"],
        "reviewed_by": xw["reviewed_by"].replace("", None),
        "reviewed_on": xw["reviewed_on"].replace("", None),
    })
    counts: dict[str, int] = {}
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute(Path(SCHEMA).read_text())
        # Hospitals before clinics, so the parent foreign key resolves.
        counts["clinic"] = upsert(cur, "clinic", sites.sort_values("kind", ascending=False), ["site_id"])
        counts["specialty"] = upsert(cur, "specialty", specialties, ["specialty_id"])
        counts["condition_specialty"] = upsert(cur, "condition_specialty", crosswalk, ["condition"])
        counts["medicine"] = upsert(cur, "medicine", pd.read_parquet(PROCESSED / "medicine.parquet"), ["medicine_id"])
        for table, name in [("src_appointment_history", "appointment_history"),
                            ("src_encounter_history", "encounter_history"),
                            ("src_condition_symptom", "condition_symptom"),
                            ("src_transcription_note", "transcription_note")]:
            counts[table] = replace(cur, table, pd.read_parquet(PROCESSED / f"{name}.parquet"))
        conn.commit()
    for k, v in counts.items():
        print(f"{k:26s} {v:>8,}")
    return counts


if __name__ == "__main__":
    main()
