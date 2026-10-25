"""Step 1 of judge calibration: run 20 new questions (not in the W2 eval set) through the real Ask
graph and save each answer with the exact excerpts the model saw.

    python -m evals.judge.make_answers --model anthropic/claude-haiku-5.5
"""
from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from evals.run_w2 import build_store
from services.agent.w2.answer import format_excerpts
from services.agent.w2.graph import build_ask_graph
from services.common.embed import default_embedder
from services.common.llm import ModelClient

HERE = Path(__file__).resolve().parent


def main(model: str) -> None:
    embedder = default_embedder()
    store = build_store(embedder)
    graph = build_ask_graph(store, ModelClient(primary=model, fallback=None), embedder)
    out = []
    for line in (HERE / "questions.jsonl").read_text().splitlines():
        q = json.loads(line)
        s = graph.invoke({"caller_id": q["patient_id"], "subject_id": q["patient_id"], "caller_role": "patient",
                          "question": q["question"], "trace_id": uuid.uuid4().hex})
        out.append({**q, "route": s["route"], "draft": s.get("draft", {}).get("answer"), "reply": s["reply"],
                    "excerpts": format_excerpts(s.get("chunks", [])), "model": model})
        print(q["id"], s["route"], (s.get("draft") or {}).get("answer", "")[:100])
    (HERE / "answers.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    main(ap.parse_args().model)
