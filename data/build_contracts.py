"""Write D4: one data contract per table, from the spec below (template: pack p53).

    python -m data.build_contracts      # -> docs/data-contracts/*.md
"""
from __future__ import annotations

from data.transforms.common import REPO

OUT = REPO / "docs" / "data-contracts"
SCHEMA_VERSION = 1
CHANGE_RULE = "Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check."

# sensitivity: direct | quasi | clinical | operational (pack p21). The highest class in the table wins.
SPEC = {
    "patient": dict(owner="Records service owner", sensitivity="direct", freshness="On change; read at request time",
        checks=["patient_id unique (0 duplicates)", "phone matches +91 and 10 digits (100%)",
                "abha_id matches NN-NNNN-NNNN-NNNN (100%)", "synthetic = true for every row in this build (100%)"],
        consumers=["W1 booking (patient_id from auth)", "W2 retrieval scope", "Consent checks"],
        source="Generated from src_encounter_history ages and genders; names from data/synthetic/names.py"),
    "consent": dict(owner="Compliance officer", sensitivity="quasi", freshness="Checked on every read; no caching",
        checks=["expires_at not null (100%)", "no read allowed after expires_at or revoked_at (tested)",
                "grantee_id is a known patient or staff id (100%)"],
        consumers=["Records service access check", "Audit queries"], source="Created by the patient; persona row seeded"),
    "document": dict(owner="Records service owner", sensitivity="direct", freshness="Status visible within 60 s of upload (E3-S1)",
        checks=["patient_id not null (100%)", "phi_status in (pending, tagged, failed)", "uri resolves to a stored file (100%)"],
        consumers=["W2 ingest", "W2 ask (citations)"], source="Patient uploads; 100 synthetic reports"),
    "doc_chunk": dict(owner="Records service owner", sensitivity="direct",
        freshness="Re-embedded when content_hash changes",
        checks=["patient_id equals its document's patient_id (0 mismatches)", "embedding has 1,024 dimensions",
                "content_hash unique per doc_id and page"],
        consumers=["W2 retrieval (patient filter in SQL)", "Citation check"],
        source="W2 ingest graph from document"),
    "ingest_job": dict(owner="Platform", sensitivity="operational", freshness="Updated at every state change",
        checks=["status in (queued, running, done, failed)", "no job running longer than 10 minutes"],
        consumers=["Upload status endpoint", "Operations dashboard"], source="RQ worker"),
    "appointment": dict(owner="Scheduling service owner", sensitivity="operational",
        freshness="Real time; tied to a patient, so reads are audited",
        checks=["idempotency_key unique (0 duplicates)", "at most one live booking per slot (unique index)",
                "status in (booked, cancelled, attended, no_show)"],
        consumers=["W1 booking", "Front-desk override", "No-show metrics"], source="W1 graph; front desk"),
    "slot": dict(owner="Scheduling service owner", sensitivity="operational", freshness="Availability cached at most 30 s",
        checks=["(doctor_id, starts_at) unique", "16 slots per doctor per working day", "every site has slots every working day"],
        consumers=["W1 shortlist tool", "Booking transaction"], source="data/synthetic/slots.py (plain code)"),
    "doctor": dict(owner="Scheduling service owner", sensitivity="operational", freshness="Daily",
        checks=["at least 10 doctors per specialty", "no repeated names", "languages include en (100%)", "synthetic = true"],
        consumers=["W1 shortlist", "Report headers"], source="data/synthetic/doctors.py (code plan + LLM names)"),
    "clinic": dict(owner="Platform", sensitivity="operational", freshness="On change",
        checks=["6 hospitals and 22 clinics", "every clinic has a parent hospital"],
        consumers=["All services"], source="data/reference/sites.csv"),
    "specialty": dict(owner="Clinical safety", sensitivity="operational", freshness="On change, by pull request",
        checks=["name unique", "red_flag_rules is valid JSON"], consumers=["W1 specialty match", "Doctor directory"],
        source="data/reference/specialties.csv"),
    "condition_specialty": dict(owner="Clinical safety", sensitivity="operational", freshness="On change, by pull request",
        checks=["every row reviewed (reviewed_by and reviewed_on not null)", "covers every condition in src_condition_symptom"],
        consumers=["W1 specialty match", "Red-flag rules (emergency_condition)"],
        source="data/reference/condition_specialty_crosswalk.csv; drafted by the AI assistant, reviewed by a human"),
    "medicine": dict(owner="Pharmacy", sensitivity="operational", freshness="Monthly",
        checks=["price_inr > 0 (100%)", "pack size parsed (>= 99%)", "medicine_id unique"],
        consumers=["W3 stock flags (Pro)", "Substitute listing (Pro)"], source="A-Z Medicine Dataset of India (CC BY-SA 4.0)"),
    "medicine_stock": dict(owner="Pharmacy", sensitivity="operational",
        freshness="Nightly CSV today (stock age shown on every flag); API later (AD-5)",
        checks=["qty >= 0", "as_of within the last 36 hours, else flagged unknown"],
        consumers=["W3 stock check (Pro)"], source="Pharmacy stock feed (Pro tier)"),
    "encounter": dict(owner="Records service owner", sensitivity="clinical", freshness="Real time",
        checks=["patient_id not null", "started_at not in the future"], consumers=["W3 scribe (Pro)"], source="Consultations"),
    "clinical_note": dict(owner="Clinical safety", sensitivity="clinical",
        freshness="Persisted only at signature; signed notes are immutable",
        checks=["signed_at set before a note is readable as final", "(encounter_id, version) unique",
                "no molecule absent from the transcript (eval)"],
        consumers=["Patient record", "Pharmacy (prescription lines)"], source="W3 scribe (Pro)"),
    "prescription": dict(owner="Clinical safety", sensitivity="clinical", freshness="With its signed note",
        checks=["note_id refers to a signed note", "substitute_ok decided by a human"], consumers=["Pharmacy"],
        source="W3 scribe (Pro)"),
    "audit_event": dict(owner="Compliance officer", sensitivity="operational",
        freshness="Written in the same transaction as the read; kept one year",
        checks=["append-only (update and delete raise)", "every record read has one event (tested)"],
        consumers=["Compliance queries (who saw this record)", "Incident review"], source="Every service"),
    "src_appointment_history": dict(owner="Data", sensitivity="quasi", freshness="Static source snapshot",
        checks=["age between 0 and 110", "lead_days >= 0", "rows in - dropped = rows out"],
        consumers=["No-show risk signal"], source="Medical Appointment No Shows (CC BY-NC-SA 4.0)"),
    "src_encounter_history": dict(owner="Data", sensitivity="quasi", freshness="Static source snapshot",
        checks=["discharged_on >= admitted_on (0 violations)", "no billing or insurance columns"],
        consumers=["Patient generator"], source="Healthcare Dataset (CC0)"),
    "src_condition_symptom": dict(owner="Clinical safety", sensitivity="operational", freshness="Static source snapshot",
        checks=["(condition, symptom) unique", "every condition is in the crosswalk"],
        consumers=["W1 specialty match"], source="Disease Symptom Prediction (CC BY-SA 4.0)"),
    "src_transcription_note": dict(owner="Data", sensitivity="clinical", freshness="Static source snapshot",
        checks=["text unique after layout repair", "every label mapped"],
        consumers=["Synthetic report generator", "W3 dictation seeds (Pro)"], source="Medical Transcriptions (CC0)"),
}

TREATMENT = {
    "direct": "Never leaves the boundary. Tokenise before any external call; Presidio plus Indian phone and ABHA recognisers.",
    "quasi": "Leaves only generalised: age band instead of birth date, district instead of pincode.",
    "clinical": "Leaves only de-identified; the token map stays on-premise.",
    "operational": "May leave; still audited when tied to a patient.",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for table, s in SPEC.items():
        md = [f"# Data contract: `{table}`", "", "```yaml",
              f"table: {table}", f"owner: {s['owner']}", f"schema_version: {SCHEMA_VERSION}", f"change_rule: {CHANGE_RULE}",
              f"freshness: {s['freshness']}", f"sensitivity: {s['sensitivity']}", "checks:"]
        md += [f"  - {c}" for c in s["checks"]]
        md += ["consumers:"] + [f"  - {c}" for c in s["consumers"]]
        md += [f"source: {s['source']}", "```", "", f"**Treatment ({s['sensitivity']}):** {TREATMENT[s['sensitivity']]}", ""]
        (OUT / f"{table}.md").write_text("\n".join(md))
        rows.append(f"| [`{table}`]({table}.md) | {s['owner']} | {s['sensitivity']} | {s['freshness']} |")
    index = ["# D4: Data contracts", "",
             f"{len(SPEC)} contracts, one per table, written on the pack's template (p53) by `python -m data.build_contracts`.",
             "The sensitivity class decides what may cross the hospital boundary (pack p21).", "",
             "| Table | Owner (role) | Sensitivity | Freshness |", "|---|---|---|---|", *rows, "",
             "## Sensitivity classes", "", "| Class | Treatment |", "|---|---|",
             *[f"| {k} | {v} |" for k, v in TREATMENT.items()], "",
             "## Compliance sign-off of the class column", "",
             "Signed off by: _pending_ · Date: _pending_", ""]
    (OUT / "README.md").write_text("\n".join(index))
    print(f"wrote {len(SPEC)} contracts to {OUT}")


if __name__ == "__main__":
    main()
