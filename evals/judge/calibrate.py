"""Calibrate the faithfulness judge against human grades before it is used (pack p46, decision 18).

calibration_items.jsonl: 20 answers to questions that are not in the W2 eval set, with the exact
excerpts the answer model saw. Six were deliberately altered (a number, a drug, a reversed finding,
an added claim) so that both classes are present; the grader was not told which (`perturbation`).
human_grades.json: the human's verdicts. Two candidate judges (Claude Haiku 5.5, GPT-6 Luna) were run;
the human reviewed every item on which they disagreed. Items without a human grade take the planted
label: altered = not faithful, unaltered = faithful.

    python -m evals.judge.calibrate --model anthropic/claude-haiku-5.5

Passes when the judge disagrees with the reference on at most 2 of 20 items. Writes judge_results_<model>.json.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from evals.judge.judge import FaithfulnessJudge, strip_handoff
from services.common.llm import spent_usd

HERE = Path(__file__).resolve().parent
MAX_DISAGREEMENTS = 2


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


CACHE = HERE / ".judge_cache.json"         # resume after an interrupted run; git-ignored


async def judge_all(judge: FaithfulnessJudge, items: list[dict], limit: int | None) -> list[dict]:
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    done = 0
    for it in items:                       # sequential: keeps the budget check exact
        key = f"{judge.model}|{it['id']}|{_digest(strip_handoff(it['answer']))}"
        if key in cache:
            continue
        if limit is not None and done >= limit:
            break
        v = await judge.ajudge(it["question"], it["answer"], it["excerpts"])
        cache[key] = {"id": it["id"], "score": v.score, "judge_faithful": v.faithful, "statements": v.statements}
        CACHE.write_text(json.dumps(cache))
        done += 1
        print(f"{it['id']} score={v.score:.2f} faithful={v.faithful}", flush=True)
    return [cache[k] for it in items for k in [f"{judge.model}|{it['id']}|{_digest(strip_handoff(it['answer']))}"] if k in cache]


def main(model: str, limit: int | None = None) -> dict | None:
    items = [json.loads(l) for l in (HERE / "calibration_items.jsonl").read_text().splitlines() if l.strip()]
    spend0 = spent_usd()
    results = asyncio.run(judge_all(FaithfulnessJudge(model=model), items, limit))
    if len(results) < len(items):
        print(f"{len(results)}/{len(items)} judged; run again to continue")
        return None
    report: dict = {"model": model, "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "items": len(items), "spend_usd": round(spent_usd() - spend0, 5), "results": results}
    # Reference label per item: the human grade where there is one, otherwise the planted label
    # (an altered answer is not faithful; an unaltered one is presumed faithful).
    grades = json.loads((HERE / "human_grades.json").read_text())["grades"]
    by_id = {it["id"]: it for it in items}
    rows = []
    for r in results:
        if r["id"] in grades:
            ref, source = grades[r["id"]] == "Faithful", "human"
        else:
            ref, source = by_id[r["id"]].get("perturbation") is None, "planted"
        rows.append({"id": r["id"], "reference_faithful": ref, "label_source": source,
                     "judge_faithful": r["judge_faithful"], "agree": ref == r["judge_faithful"]})
    disagreements = [x["id"] for x in rows if not x["agree"]]
    report["calibration"] = {
        "agreement": (len(rows) - len(disagreements)) / len(rows), "disagreements": disagreements,
        "unfaithful_caught": sum(not x["reference_faithful"] and not x["judge_faithful"] for x in rows),
        "unfaithful_missed": sum(not x["reference_faithful"] and x["judge_faithful"] for x in rows),
        "faithful_flagged": sum(x["reference_faithful"] and not x["judge_faithful"] for x in rows),
        "human_labels": sum(x["label_source"] == "human" for x in rows),
        "passes": len(disagreements) <= MAX_DISAGREEMENTS,
        "rule": f"at most {MAX_DISAGREEMENTS} of {len(rows)} disagreements", "rows": rows}
    print(json.dumps({k: v for k, v in report["calibration"].items() if k != "rows"}, indent=2))
    out = HERE / f"judge_results_{model.split('/')[-1]}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"spend {report['spend_usd']} USD; wrote {out}")
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--limit", type=int, help="judge at most this many new items in this run")
    a = ap.parse_args()
    main(a.model, a.limit)
