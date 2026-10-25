"""Simulated booking sessions for the p16 demo metric "bookings completed without a call".

    python -m evals.run_sessions --model anthropic/claude-haiku-5.5

Each of the 20 non-emergency W1 cases is played as a full session through the real graph: the
patient's first message; scripted answers to any clarifying question (sets/w1_session_followups.jsonl,
written on 25 Oct 2026 after the graph existed, so they are not part of the pre-code eval set);
then the first slot offered is picked with an idempotency key. A session counts as completed when
it ends booked with no hand-off to the front desk. Emergency cases are excluded: they must reach a
human. Time is system time only (sum of graph turns); a patient's reading and typing time needs
usability sessions and is not measured here.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from evals.run_w1 import NOW, RUNS, SETS
from evals.schema import EvalCase
from services.agent.w1.directory import InMemoryDirectory
from services.agent.w1.graph import build
from services.common.llm import ModelClient, spent_usd


def play(graph, case: EvalCase, followups: list[str]) -> dict:
    cfg = {"configurable": {"thread_id": f"s-{case.id}"}}
    t0 = time.monotonic()
    out = graph.invoke({"patient_id": "P-EVAL", "message": case.input.message, "age": case.input.age,
                        "language": case.input.language, "now": NOW}, cfg)
    turns, answers = 1, list(followups)
    while out.get("__interrupt__") and turns < 6:
        prompt = out["__interrupt__"][0].value
        if prompt["type"] == "clarify":
            resume = answers.pop(0) if answers else "I don't know"
        else:
            resume = {"slot_id": prompt["options"][0]["slot_id"], "idempotency_key": f"sess-{case.id}"}
        out = graph.invoke(Command(resume=resume), cfg)
        turns += 1
    return {"id": case.id, "route": out.get("route"), "booked": out.get("route") == "booked",
            "specialty": out.get("specialty"), "turns": turns, "system_s": round(time.monotonic() - t0, 3)}


def main(model: str) -> dict:
    cases = [EvalCase.model_validate(json.loads(l)) for l in (SETS / "w1_triage.jsonl").read_text().splitlines() if l.strip()]
    cases = [c for c in cases if c.expect.route != "emergency_desk"]
    follow = {json.loads(l)["case_id"]: json.loads(l)["followups"]
              for l in (SETS / "w1_session_followups.jsonl").read_text().splitlines() if l.strip()}
    spend0 = spent_usd()
    graph = build(InMemoryDirectory(), ModelClient(primary=model, fallback=None), InMemorySaver())
    rows = [play(graph, c, follow.get(c.id, [])) for c in cases]
    booked = [r for r in rows if r["booked"]]
    result = {"workflow": "w1_sessions", "model": model, "sessions": len(rows),
              "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "metrics": {"completed_without_call": len(booked) / len(rows),
                          "median_system_time_to_book_s": round(statistics.median(r["system_s"] for r in booked), 3) if booked else None,
                          "max_system_time_to_book_s": max((r["system_s"] for r in booked), default=None),
                          "median_turns": statistics.median(r["turns"] for r in rows)},
              "spend_usd": round(spent_usd() - spend0, 5), "rows": rows}
    RUNS.mkdir(exist_ok=True)
    out = RUNS / f"w1sessions_{model.split('/')[-1]}_{result['run_at'][:19].replace(':', '')}.json"
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps({**result["metrics"], "spend_usd": result["spend_usd"]}, indent=2))
    for r in rows:
        if not r["booked"]:
            print(f"  NOT BOOKED {r['id']} route={r['route']} turns={r['turns']}")
    print(f"wrote {out}")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    main(ap.parse_args().model)
