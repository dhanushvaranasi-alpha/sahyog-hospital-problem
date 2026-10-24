"""Run the W1 eval set through the real graph and score it (pack p16 targets, evals/README.md rules).

    python -m evals.run_w1 --model anthropic/claude-haiku-5.5
    python -m evals.run_w1 --model openai/gpt-6-luna

Uses the in-memory directory (same committed doctors and slot plan) and an in-memory checkpointer,
so no database is needed; the model calls are real and land in the spend ledger.
Writes evals/runs/w1_<model>_<timestamp>.json.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from evals.schema import EvalCase
from services.agent.w1.directory import InMemoryDirectory
from services.agent.w1.graph import build
from services.common.llm import ModelClient, spent_usd

SETS = Path(__file__).resolve().parent / "sets"
RUNS = Path(__file__).resolve().parent / "runs"
NOW = "2026-10-26T08:00:00+05:30"


def p95(xs: list[float]) -> float:
    xs = sorted(xs)
    return xs[max(0, int(round(0.95 * len(xs))) - 1)] if xs else 0.0


def run_case(graph, case: EvalCase) -> dict:
    cfg = {"configurable": {"thread_id": case.id}}
    t0 = time.monotonic()
    out = graph.invoke({"patient_id": "P-EVAL", "message": case.input.message, "age": case.input.age,
                        "language": "en", "now": NOW}, cfg)
    latency = time.monotonic() - t0
    intr = out.get("__interrupt__")
    if intr:
        kind = intr[0].value["type"]
        route = "clarify" if kind == "clarify" else "booking"
    else:
        route = out.get("route")
    reply = (out.get("reply") or "") + " " + (intr[0].value.get("question", "") if intr else "")
    offered = bool(intr and intr[0].value["type"] == "choose_slot")
    leaks = [w for w in case.must_not if (w in ("slot", "appointment") and offered) or
             (w == "specialty" and route == "booking") or (w not in ("slot", "appointment", "specialty") and w.lower() in reply.lower())]
    return {"id": case.id, "category": case.category, "route": route, "expected_route": case.expect.route,
            "red_flags": out.get("red_flags", []), "red_flag_source": out.get("red_flag_source"),
            "specialty": out.get("specialty"), "expected_specialty": case.expect.specialty,
            "acceptable": case.expect.acceptable_specialties, "confidence": out.get("confidence"),
            "latency_s": round(latency, 3), "leaks": leaks, "reply": reply.strip()[:300]}


def score(rows: list[dict], cases: dict[str, EvalCase]) -> dict:
    rf = [r for r in rows if cases[r["id"]].expect.red_flag]
    booking = [r for r in rows if cases[r["id"]].expect.route == "booking"]
    clarify = [r for r in rows if cases[r["id"]].expect.route == "clarify"]
    not_rf = [r for r in rows if not cases[r["id"]].expect.red_flag]
    return {
        "red_flag_recall": sum(r["route"] == "emergency_desk" for r in rf) / len(rf),
        "red_flag_false_alarms": sum(r["route"] == "emergency_desk" for r in not_rf),
        "specialty_accuracy_strict": sum(r["route"] == "booking" and r["specialty"] == r["expected_specialty"] for r in booking) / len(booking),
        "specialty_accuracy_lenient": sum(r["route"] == "booking" and r["specialty"] in r["acceptable"] for r in booking) / len(booking),
        "clarify_rate": sum(r["route"] == "clarify" for r in clarify) / len(clarify),
        "route_accuracy": sum(r["route"] == r["expected_route"] for r in rows) / len(rows),
        "leaks": sum(len(r["leaks"]) for r in rows),
        "p95_turn_latency_s": round(p95([r["latency_s"] for r in rows]), 3),
        "median_turn_latency_s": round(statistics.median(r["latency_s"] for r in rows), 3),
    }


def main(model: str) -> dict:
    cases = [EvalCase.model_validate(json.loads(l)) for l in (SETS / "w1_triage.jsonl").read_text().splitlines() if l.strip()]
    spend0 = spent_usd()
    graph = build(InMemoryDirectory(), ModelClient(primary=model, fallback=None), InMemorySaver())
    rows = [run_case(graph, c) for c in cases]
    result = {"workflow": "w1", "model": model, "cases": len(rows), "eval_set_version": 1,
              "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "metrics": score(rows, {c.id: c for c in cases}), "spend_usd": round(spent_usd() - spend0, 5),
              "rows": rows}
    RUNS.mkdir(exist_ok=True)
    out = RUNS / f"w1_{model.split('/')[-1]}_{result['run_at'][:19].replace(':', '')}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({"model": model, **result["metrics"], "spend_usd": result["spend_usd"]}, indent=2))
    for r in rows:
        if r["route"] != r["expected_route"] or (r["expected_route"] == "booking" and r["specialty"] not in r["acceptable"]):
            print(f"  MISS {r['id']} expected {r['expected_route']}/{r['expected_specialty']} got {r['route']}/{r['specialty']} (conf {r['confidence']})")
    print(f"wrote {out}")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    main(ap.parse_args().model)
