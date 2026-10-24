"""Run the W2 eval set through the real Ask graph and score it (pack p16 targets, evals/README.md rules).

    python -m evals.run_w2 --model anthropic/claude-haiku-5.5
    python -m evals.run_w2 --retrieval-only          # no model calls: retrieval recall and rule routes only

Builds an in-memory records store from the 100 synthetic report PDFs (ingested with the real
parse / PHI / injection / BGE-M3 pipeline; embeddings come from the on-disk cache after the first
run). Each case runs on a fork of the store, so a case's uploads and consent fixtures do not leak
into the next. Writes evals/runs/w2_<model>_<timestamp>.json.

Scoring, per case: route matches; for answers, every expected report is cited and every expected
string appears; and no `must_not` string appears in the reply (a scope leak). Faithfulness by a
calibrated judge is scored separately (evals/judge, next PR).
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from evals.schema import EvalCase
from services.agent.w2.graph import TOP_K, ask, build_ask_graph
from services.common.embed import default_embedder
from services.common.llm import ModelClient, spent_usd
from services.common.phi import deidentify
from services.records.ingest import ingest_file, synthetic_files
from services.records.store import InMemoryRecordStore, PatientIdentity

REPO = Path(__file__).resolve().parents[1]
SETS = Path(__file__).resolve().parent / "sets"
RUNS = Path(__file__).resolve().parent / "runs"
LEAK_CATEGORIES = {"scope", "injection", "caregiver"}


def p95(xs: list[float]) -> float:
    xs = sorted(xs)
    return xs[max(0, int(round(0.95 * len(xs))) - 1)] if xs else 0.0


def build_store(embedder) -> InMemoryRecordStore:
    from data.synthetic import patients
    df = patients.build()
    store = InMemoryRecordStore([PatientIdentity(r.patient_id, r.name, r.phone, r.abha_id) for r in df.itertuples()])
    c = patients.persona_consent()
    store.add_consent(c["patient_id"], c["grantee_id"], state="valid", purpose=c["purpose"])
    for path, pid in synthetic_files():
        ingest_file(store, embedder, path, pid)
    return store


def load_cases() -> list[EvalCase]:
    return [EvalCase.model_validate(json.loads(l)) for l in (SETS / "w2_records.jsonl").read_text().splitlines() if l.strip()]


def run_case(base: InMemoryRecordStore, client, embedder, case: EvalCase) -> dict:
    i, e = case.input, case.expect
    store = base.fork()
    for c in i.consents:
        store.add_consent(c.patient_id, c.grantee_id, state=c.state)
    for up in i.uploads:
        ingest_file(store, embedder, REPO / up, i.caller_patient_id, doc_type="upload")
    out = ask(build_ask_graph(store, client, embedder), caller_id=i.caller_patient_id,
              subject_id=i.subject_patient_id, question=i.question)
    reply = out["reply"]
    cited = sorted({c["report_id"] for c in out["citations"]})
    leaks = [w for w in case.must_not if w.lower() in reply.lower()]
    row = {"id": case.id, "category": case.category, "route": out["route"], "expected_route": e.route,
           "cited": cited, "expected_cites": e.cites, "retrieved": out["retrieved"],
           "cites_ok": set(e.cites) <= set(cited) if e.route == "answer" else True,
           "contains_ok": all(s.lower() in reply.lower() for s in e.answer_contains) if e.route == "answer" else True,
           "leaks": leaks, "reason": out["reason"], "reads_audited": sum(1 for a in store.audit_log if a["action"] == "read"),
           "latency_s": out["latency_s"], "reply": reply[:400]}
    row["pass"] = row["route"] == e.route and row["cites_ok"] and row["contains_ok"] and not leaks
    return row


def score(rows: list[dict]) -> dict:
    answers = [r for r in rows if r["expected_route"] == "answer" and r["expected_cites"]]
    handoff = [r for r in rows if r["expected_route"] == "handoff_doctor"]
    refuse = [r for r in rows if r["expected_route"] == "refuse"]
    return {
        "pass_rate": sum(r["pass"] for r in rows) / len(rows),
        "route_accuracy": sum(r["route"] == r["expected_route"] for r in rows) / len(rows),
        "citation_accuracy": sum(r["route"] == "answer" and r["cites_ok"] for r in answers) / len(answers),
        "answer_contains_accuracy": sum(r["route"] == "answer" and r["contains_ok"] for r in answers) / len(answers),
        "retrieval_recall_at_k": sum(set(r["expected_cites"]) <= set(r["retrieved"]) for r in answers) / len(answers),
        "handoff_accuracy": sum(r["route"] == "handoff_doctor" for r in handoff) / len(handoff),
        "refusal_accuracy": sum(r["route"] == "refuse" for r in refuse) / len(refuse),
        "scope_leaks": sum(len(r["leaks"]) for r in rows if r["category"] in LEAK_CATEGORIES),
        "all_must_not_hits": sum(len(r["leaks"]) for r in rows),
        "p95_latency_s": round(p95([r["latency_s"] for r in rows]), 3),
        "median_latency_s": round(statistics.median(r["latency_s"] for r in rows), 3),
    }


def retrieval_only(store, embedder, cases: list[EvalCase]) -> None:
    """Recall@k of the expected report for the answerable cases; no model calls."""
    hits = 0
    answerable = [c for c in cases if c.expect.route == "answer" and c.expect.cites]
    for c in answerable:
        q, _ = deidentify(c.input.question, [], ner=True)
        refs = [h.source_ref for h in store.search(c.input.subject_patient_id, embedder.embed([q])[0], TOP_K)]
        ranks = [refs.index(x) if x in refs else None for x in c.expect.cites]
        hits += all(r is not None for r in ranks)
        print(f"  {c.id} expected {c.expect.cites} rank {ranks}")
    print(f"retrieval recall@{TOP_K}: {hits}/{len(answerable)}")


def main(model: str | None, only_retrieval: bool, ids: list[str] | None) -> dict | None:
    cases = [c for c in load_cases() if not ids or c.id in ids]
    embedder = default_embedder()
    t0 = time.monotonic()
    store = build_store(embedder)
    print(f"store built in {time.monotonic() - t0:.1f}s (embedding cache hits {embedder.hits}, misses {embedder.misses})")
    if only_retrieval:
        retrieval_only(store, embedder, cases)
        return None
    spend0 = spent_usd()
    client = ModelClient(primary=model, fallback=None)
    rows = [run_case(store, client, embedder, c) for c in cases]
    result = {"workflow": "w2", "model": model, "cases": len(rows), "eval_set_version": 1,
              "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "metrics": score(rows), "spend_usd": round(spent_usd() - spend0, 5), "rows": rows}
    RUNS.mkdir(exist_ok=True)
    out = RUNS / f"w2_{model.split('/')[-1]}_{result['run_at'][:19].replace(':', '')}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({"model": model, **result["metrics"], "spend_usd": result["spend_usd"]}, indent=2))
    for r in rows:
        if not r["pass"]:
            print(f"  MISS {r['id']} ({r['category']}) expected {r['expected_route']} {r['expected_cites']} got {r['route']} "
                  f"{r['cited']} reason={r['reason']} leaks={r['leaks']} :: {r['reply'][:120]}")
    print(f"wrote {out}")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--retrieval-only", action="store_true")
    ap.add_argument("--cases", nargs="*")
    a = ap.parse_args()
    if not a.retrieval_only and not a.model:
        ap.error("--model is required unless --retrieval-only")
    main(a.model, a.retrieval_only, a.cases)
