"""Synthetic report PDFs: the LLM rewrites a cleaned public transcription as a report (language),
code adds the identifying header and renders the PDF (layout). 100 reports for 49 patients,
mixed 40 lab / 35 radiology / 15 cardiology / 10 discharge summaries (assumption A07).

    python -m data.synthetic.reports            # LLM step -> output/reports.jsonl (committed)
    python -m data.synthetic.reports --render   # JSON -> output/pdfs/*.pdf (git-ignored, deterministic)

The header deliberately carries name, phone, ABHA number and MRN, so the egress scrubber
(PR #6) has real identifiers to find.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pandas as pd
from fpdf import FPDF

from data.synthetic import patients as patients_mod
from data.synthetic.schemas import ReportDraft
from data.transforms.common import PROCESSED, REFERENCE

HERE = Path(__file__).resolve().parent
OUT = HERE / "output" / "reports.jsonl"
PDF_DIR = HERE / "output" / "pdfs"
PROMPT_VERSION = "reports_v2"
PROMPT = (HERE / "prompts" / f"{PROMPT_VERSION}.md").read_text()
SEED = 20261024
# Report type is chosen by what the source note IS, not by its label: the transcription
# de-duplication keeps one label per note, so most imaging notes carry a clinical label.
LAB_SECTION = r"(LABORATORY (DATA|STUDIES|VALUES|FINDINGS|RESULTS)|LABS|LAB DATA|LAB RESULTS)\s*:"
CARDIO_TITLE = r"\b(Echocardiogra|ECG|EKG|Electrocardiogra|Stress test|Holter|Cardiac cath|Carotid)"
IMAGING_TITLE = r"\b(MRI|CT|X-?ray|Ultrasound|Sonogra|Mammogra|Doppler|Angiogra|Radiograph|Bone scan|Venogram|Arteriogra|Myelogra)"
# Mix follows assumption A07: lab first, then radiology; cardiology and discharge summaries after.
TARGET_MIX = {"lab": 40, "radiology": 35, "cardiology": 15, "discharge summary": 10}
# The demo personas: Priya's mother (62, diabetic) and Priya (34).
PERSONA_PLAN = {"P-SUNITA": ["lab", "lab", "cardiology", "radiology"], "P-PRIYA": ["lab", "radiology"]}
PERSONA_TITLES = {("P-SUNITA", "radiology"): r"chest", ("P-SUNITA", "cardiology"): r"echocardiogra",
                  ("P-PRIYA", "radiology"): r"ultrasound"}
OTHER_PATIENTS = 47
PER_PATIENT = 2


def classify(notes: pd.DataFrame) -> pd.Series:
    title = notes["title"].fillna("")
    out = pd.Series(None, index=notes.index, dtype="object")
    out[notes["text"].str.contains(LAB_SECTION, regex=True)] = "lab"
    out[title.str.contains(IMAGING_TITLE, case=False, regex=True)] = "radiology"
    out[title.str.contains(CARDIO_TITLE, case=False, regex=True)] = "cardiology"
    out[notes["label"] == "Discharge Summary"] = "discharge summary"
    return out


def plan() -> pd.DataFrame:
    rng = random.Random(SEED)
    notes = pd.read_parquet(PROCESSED / "transcription_note.parquet")
    notes = notes[notes["text"].str.len().between(400, 6000)].copy()
    notes["report_type"] = classify(notes)
    notes = notes.dropna(subset=["report_type"])
    diabetic = notes["text"].str.contains(r"glucose|HbA1c|A1c|diabet", case=False, regex=True)

    pts = patients_mod.build()
    others = pts[~pts["patient_id"].isin(PERSONA_PLAN)].sample(OTHER_PATIENTS, random_state=SEED)["patient_id"].tolist()
    persona_types = [t for ts in PERSONA_PLAN.values() for t in ts]
    remaining = {k: v - persona_types.count(k) for k, v in TARGET_MIX.items()}
    other_types = [t for t, n in remaining.items() for _ in range(n)]
    rng.shuffle(other_types)
    assignments = [(pid, t) for pid, ts in PERSONA_PLAN.items() for t in ts]
    assignments += [(pid, other_types.pop()) for pid in others for _ in range(PER_PATIENT)]

    used, rows = set(), []
    for k, (pid, rtype) in enumerate(assignments, start=1):
        pool = notes[(notes["report_type"] == rtype) & ~notes["note_id"].isin(used)]
        # Keep the demo personas clinically coherent (62-year-old diabetic mother; 34-year-old daughter).
        if pid == "P-SUNITA" and rtype == "lab":
            pool = pool[diabetic.reindex(pool.index, fill_value=False)]
        flt = PERSONA_TITLES.get((pid, rtype))
        if flt:
            pool = pool[pool["title"].fillna("").str.contains(flt, case=False, regex=True)]
        nid = int(pool.sample(1, random_state=SEED + k)["note_id"].iloc[0])
        used.add(nid)
        rows.append({"report_id": f"R{k:04d}", "patient_id": pid, "source_note_id": nid, "report_type": rtype,
                     "mrn": f"SH-{rng.randrange(10**7, 10**8)}",
                     "report_date": (pd.Timestamp("2026-06-01") + pd.Timedelta(days=rng.randrange(0, 140))).date().isoformat()})
    return pd.DataFrame(rows)


def generate(client=None) -> int:
    from services.common.llm import ModelClient
    client = client or ModelClient()
    notes = pd.read_parquet(PROCESSED / "transcription_note.parquet").set_index("note_id")
    existing = [json.loads(l) for l in OUT.read_text().splitlines() if l.strip()] if OUT.exists() else []
    # Reuse a paid draft when the same source note and report type appear in the plan.
    # Reuse a paid draft only if it still passes the current schema (v2 rejects copied ages/pronouns).
    cache = {}
    for r in existing:
        try:
            ReportDraft.model_validate(r["draft"])
            cache[(r["source_note_id"], r["report_type"])] = (r["draft"], r.get("prompt_version", "reports_v1"))
        except Exception:
            pass
    reused = generated = 0
    rows = []
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for r in plan().itertuples(index=False):
        key = (r.source_note_id, r.report_type)
        if key in cache:
            (draft, version), reused = cache[key], reused + 1
        else:
            src = notes.loc[r.source_note_id, "text"][:4000]
            extra = ("Build the report from the laboratory values in the source; list each test with its value and unit."
                     if r.report_type == "lab" else "")
            draft = client.structured(
                purpose=f"synthetic:report:{r.report_id}", system=PROMPT,
                user=f"Report type: {r.report_type}\n{extra}\nSource transcription:\n{src}",
                schema=ReportDraft, max_tokens=3500, temperature=0.4).model_dump()
            version = PROMPT_VERSION
            cache[key], generated = (draft, version), generated + 1
        rows.append({**r._asdict(), "draft": draft, "prompt_version": version, "seed": SEED, "synthetic": True})
        OUT.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows))
    print(f"reports: {generated} generated, {reused} reused from earlier runs, {len(rows)} in plan")
    return generated


def _latin1(s: str) -> str:
    return s.replace("–", "-").replace("—", "-").replace("’", "'").replace("‘", "'") \
            .replace("“", '"').replace("”", '"').replace("•", "-").encode("latin-1", "replace").decode("latin-1")


def render(row: dict, patient: dict, site_name: str, out_dir: Path = PDF_DIR) -> Path:
    d = ReportDraft.model_validate(row["draft"])
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, _latin1(site_name), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, "SYNTHETIC DOCUMENT - fictional patient, generated for the Sahyog Care Companion engagement",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    header = [("Patient", patient["name"]), ("Age / Sex", f"{patient['age']} / {patient['gender']}"),
              ("Phone", patient["phone"]), ("ABHA", patient["abha_id"]), ("MRN", row["mrn"]),
              ("Report date", row["report_date"]), ("Report ID", row["report_id"])]
    for k, v in header:
        pdf.cell(35, 6, f"{k}:"); pdf.cell(0, 6, _latin1(str(v)), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 13)
    pdf.multi_cell(0, 7, _latin1(d.title), new_x="LMARGIN", new_y="NEXT")
    for s in d.sections:
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 6, _latin1(s.heading), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, _latin1(s.body), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "Impression", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5, _latin1(d.impression), new_x="LMARGIN", new_y="NEXT")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{row['report_id']}_{row['patient_id']}.pdf"
    pdf.output(str(path))
    return path


def render_all() -> int:
    pts = patients_mod.build().set_index("patient_id")
    sites = pd.read_csv(REFERENCE / "sites.csv")
    by_city = {c: g["name"].tolist() for c, g in sites[sites["kind"] == "hospital"].groupby("city")}
    rows = [json.loads(l) for l in OUT.read_text().splitlines() if l.strip()]
    for row in rows:
        p = pts.loc[row["patient_id"]].to_dict()
        site = by_city[p["city"]][int(row["report_id"][1:]) % len(by_city[p["city"]])]
        render(row, p, site)
    print(f"rendered {len(rows)} PDFs to {PDF_DIR}")
    return len(rows)


if __name__ == "__main__":
    if "--render" in sys.argv:
        render_all()
    else:
        generate()
