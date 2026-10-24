"""Doctor directory: code decides specialty and clinic (arithmetic), the LLM writes the names (language).

    python -m data.synthetic.doctors        # writes data/synthetic/output/doctors.jsonl

Pack p20: seed from real columns, schema-validated, batches of 50 with a fixed seed in the prompt,
reject (never repair) rows that fail, tag every row synthetic.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pandas as pd

from data.synthetic.schemas import DoctorBatch
from data.transforms.common import REFERENCE
from services.common.llm import ModelClient

HERE = Path(__file__).resolve().parent
OUT = HERE / "output" / "doctors.jsonl"
PROMPT = (HERE / "prompts" / "doctors_v1.md").read_text()
SEED = 20261024
BATCH = 50
TOTAL = 500
MIN_PER_SPECIALTY = 10          # D5 check: every specialty has at least ten doctors
# Extra doctors on top of the minimum, for high-demand outpatient specialties (sums to 170).
EXTRA = {"General Medicine": 40, "Orthopaedics": 15, "Obstetrics & Gynaecology": 15, "Paediatrics": 15,
         "Cardiology": 12, "Dermatology": 12, "General Surgery": 12, "ENT": 10, "Gastroenterology": 10,
         "Pulmonology": 8, "Endocrinology": 8, "Neurology": 8, "Ophthalmology": 5}
# Outpatient-friendly specialties can sit in clinics; the rest sit in hospitals.
CLINIC_SPECIALTIES = {"General Medicine", "Paediatrics", "Dermatology", "ENT", "Ophthalmology", "Dentistry",
                      "Obstetrics & Gynaecology", "Physiotherapy & Rehabilitation", "Dietetics & Nutrition",
                      "Endocrinology", "Orthopaedics", "Psychiatry", "Allergy & Immunology"}


def plan() -> pd.DataFrame:
    """Deterministic rows: (specialty_id, clinic_id, city). Every site gets doctors."""
    rng = random.Random(SEED)
    spec = pd.read_csv(REFERENCE / "specialties.csv")
    sites = pd.read_csv(REFERENCE / "sites.csv")
    hospitals = sites[sites["kind"] == "hospital"]["site_id"].tolist()
    clinics = sites[sites["kind"] == "clinic"]["site_id"].tolist()
    city = dict(zip(sites["site_id"], sites["city"]))
    counts = {n: MIN_PER_SPECIALTY + EXTRA.get(n, 0) for n in spec["name"]}
    assert sum(counts.values()) == TOTAL, sum(counts.values())

    rows = []
    for _, s in spec.iterrows():
        pool = hospitals + clinics if s["name"] in CLINIC_SPECIALTIES else hospitals
        start = rng.randrange(len(pool))
        for i in range(counts[s["name"]]):
            site = pool[(start + i) % len(pool)]
            rows.append({"specialty_id": s["specialty_id"], "specialty": s["name"], "clinic_id": site, "city": city[site]})
    df = pd.DataFrame(rows).sample(frac=1, random_state=SEED).reset_index(drop=True)
    df.insert(0, "doctor_id", [f"D{n:04d}" for n in range(1, len(df) + 1)])
    return df


def generate(client: ModelClient | None = None) -> list[dict]:
    client = client or ModelClient()
    p = plan()
    done = {}
    if OUT.exists():  # resume: a failed batch reruns without shifting the rest
        done = {json.loads(l)["doctor_id"]: json.loads(l) for l in OUT.read_text().splitlines() if l.strip()}
    rejected = 0
    for b in range(0, len(p), BATCH):
        chunk = p.iloc[b:b + BATCH]
        if all(d in done for d in chunk["doctor_id"]):
            continue
        request = [{"slot": i, "specialty": r.specialty, "city": r.city} for i, r in enumerate(chunk.itertuples())]
        batch = client.structured(
            purpose=f"synthetic:doctors:batch{b // BATCH + 1}",
            system=PROMPT,
            user=f"Seed: {SEED + b}\nRequest rows:\n{json.dumps(request, ensure_ascii=False)}",
            schema=DoctorBatch, max_tokens=6000, temperature=0.9,
        )
        got = {d.slot: d for d in batch.doctors}
        with OUT.open("a") as f:
            for i, r in enumerate(chunk.itertuples()):
                d = got.get(i)
                if d is None:
                    rejected += 1
                    continue
                row = {"doctor_id": r.doctor_id, "name": d.name, "gender": d.gender, "specialty_id": r.specialty_id,
                       "clinic_id": r.clinic_id, "languages": d.languages, "years_in_practice": d.years_in_practice,
                       "synthetic": True, "prompt_version": "doctors_v1", "seed": SEED + b}
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                done[r.doctor_id] = row
    print(f"doctors: {len(done)} written, {rejected} rejected")
    done = dedupe(client, p, done)
    return list(done.values())


def dedupe(client: ModelClient, p: pd.DataFrame, done: dict, rounds: int = 3) -> dict:
    """Batches cannot see each other's names, so repeats appear. Reject the later copy of a
    repeated name (never repair it) and regenerate that row with the taken names listed."""
    for rnd in range(1, rounds + 1):
        seen, repeats = set(), []
        for did in sorted(done):
            if done[did]["name"] in seen:
                repeats.append(did)
            seen.add(done[did]["name"])
        if not repeats:
            break
        for did in repeats:
            done.pop(did)
        chunk = p[p["doctor_id"].isin(repeats)]
        request = [{"slot": i, "specialty": r.specialty, "city": r.city} for i, r in enumerate(chunk.itertuples())]
        batch = client.structured(
            purpose=f"synthetic:doctors:dedupe{rnd}", system=PROMPT,
            user=(f"Seed: {SEED + 1000 + rnd}\nThese names are already taken; do not use any of them:\n"
                  f"{json.dumps(sorted(seen), ensure_ascii=False)}\nRequest rows:\n{json.dumps(request, ensure_ascii=False)}"),
            schema=DoctorBatch, max_tokens=6000, temperature=0.9)
        got = {d.slot: d for d in batch.doctors}
        for i, r in enumerate(chunk.itertuples()):
            d = got.get(i)
            if d is not None and d.name not in seen:
                done[r.doctor_id] = {"doctor_id": r.doctor_id, "name": d.name, "gender": d.gender,
                                     "specialty_id": r.specialty_id, "clinic_id": r.clinic_id, "languages": d.languages,
                                     "years_in_practice": d.years_in_practice, "synthetic": True,
                                     "prompt_version": "doctors_v1", "seed": SEED + 1000 + rnd}
                seen.add(d.name)
        print(f"dedupe round {rnd}: {len(repeats)} repeated names rejected and regenerated")
    OUT.write_text("".join(json.dumps(done[k], ensure_ascii=False) + "\n" for k in sorted(done)))
    return done


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    generate()
