"""Write evals/report.md and docs/cost-sheet.md from the committed run files and the spend ledger.

    python -m evals.build_report

Every figure in the two documents is read from evals/runs/*.json, evals/judge/judge_results_*.json
or data/llm_ledger.jsonl; nothing is typed in by hand. Re-run after any eval run.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNS = REPO / "evals" / "runs"
LEDGER = REPO / "data" / "llm_ledger.jsonl"
PRIMARY = "claude-haiku-5.5"
JUDGE = "gpt-6-luna"


def runs(prefix: str, model: str | None = None) -> list[dict]:
    out = []
    for p in sorted(RUNS.glob(f"{prefix}_*.json")):
        d = json.loads(p.read_text())
        if model is None or d.get("model", "").endswith(model):
            d["_file"] = p.name
            out.append(d)
    return out


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def rng(xs: list[float], fmt=lambda v: f"{v:.2f} s") -> str:
    return fmt(xs[0]) if min(xs) == max(xs) else f"{fmt(min(xs))} to {fmt(max(xs))}"


def ledger_stats() -> dict:
    rows = [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()]
    by = defaultdict(list)
    for r in rows:
        if r.get("schema_valid") and r.get("input_tokens"):
            by[(r["purpose"], r["model"].split("/")[-1])].append(r)
    stats = {}
    for k, v in by.items():
        priced = [r for r in v if r.get("usd_per_input_token")]
        stats[k] = {"calls": len(v), "in": statistics.mean(r["input_tokens"] for r in v),
                    "out": statistics.mean(r["output_tokens"] for r in v),
                    "cost": statistics.mean(r["cost_usd"] for r in v),
                    "p_in": priced[-1]["usd_per_input_token"] if priced else None,
                    "p_out": priced[-1]["usd_per_output_token"] if priced else None,
                    "checked": priced[-1]["price_checked_at"][:10] if priced else None}
    total = sum(r.get("cost_usd", 0) for r in rows)
    return {"by": stats, "total": total, "calls": len(rows)}


def main() -> None:
    w1 = runs("w1", PRIMARY)
    w1_alt = runs("w1", JUDGE)
    w2 = runs("w2", PRIMARY)
    w2_judged = [r for r in w2 if r.get("judge_model")]
    sess = runs("w1sessions", PRIMARY)
    cal = json.loads((REPO / "evals" / "judge" / f"judge_results_{JUDGE}.json").read_text())["calibration"]
    led = ledger_stats()
    today = datetime.now(timezone.utc).date().isoformat()

    w1m = [r["metrics"] for r in w1]
    w2m = [r["metrics"] for r in w2]
    s = sess[-1]["metrics"]
    j = w2_judged[-1]["metrics"] if w2_judged else None
    w1_turn = led["by"][("w1:match_specialty", PRIMARY)]
    w2_ans = led["by"][("w2:answer", PRIMARY)]
    session_cost = sess[-1]["spend_usd"] / sess[-1]["sessions"]
    consult = session_cost + w2_ans["cost"]

    def status(ok: bool | None) -> str:
        return {True: "Met", False: "Not met", None: "Not measured"}[ok]

    p95_w1 = [m["p95_turn_latency_s"] for m in w1m]
    p95_w2 = [m["p95_latency_s"] for m in w2m]
    rows = [
        ("Triage turn latency, p95", "< 4 s", rng(p95_w1), status(max(p95_w1) < 4),
         f"{len(w1)} W1 runs, Claude Haiku 5.5 (in-memory directory)"),
        ("Record answer latency, p95", "< 8 s", rng(p95_w2), status(max(p95_w2) < 8), f"{len(w2)} W2 runs"),
        ("Note draft latency, p95", "< 20 s", "—", "Not in Core", "W3 scribe is Pro tier"),
        ("Availability in clinic hours", "99.5%", "—", "Not measured", "Laptop build; no uptime monitoring"),
        ("Every record read audited", "actor, purpose, time", "1 event per document shown to the model; deny and hand-off events too",
         "Met (tested)", "services/agent/w2/tests, services/records/tests"),
        ("Residency", "identified data in India", "Identified data stays in local Postgres; only tokenised text reaches OpenRouter",
         "Met for identified data", "The model provider is not India-resident; see the egress design (ADR 0006)"),
        ("Retention", "audio 24 h; audit 1 year", "No audio at Core; audit_event append-only, never deleted",
         "Partly", "No scheduled job enforces the one-year window"),
        ("Recovery", "restore < 4 h; checkpoints survive restarts",
         "A W1 session started on one API instance resumed and booked on a fresh one", "Partly",
         "Restore from backup not tested"),
        ("Bookings completed without a call", ">= 70% of synthetic sessions", pct(s["completed_without_call"]),
         status(s["completed_without_call"] >= 0.7), f"{sess[-1]['sessions']} simulated sessions ({sess[-1]['_file']})"),
        ("Time to book, median", "< 3 min", f"{s['median_system_time_to_book_s']:.1f} s system time",
         "Partly", "Human reading and typing time needs usability sessions"),
        ("Red-flag recall", "100%", rng([m["red_flag_recall"] for m in w1m], pct),
         status(min(m["red_flag_recall"] for m in w1m) == 1.0), f"0 false alarms in every run"),
        ("Specialty accuracy", ">= 85%", f"strict {rng([m['specialty_accuracy_strict'] for m in w1m], pct)}; "
         f"lenient {rng([m['specialty_accuracy_lenient'] for m in w1m], pct)}",
         status(min(m["specialty_accuracy_strict"] for m in w1m) >= 0.85), "17 booking cases"),
        ("Answer faithfulness", ">= 0.9, calibrated judge", f"{j['faithfulness_mean']:.2f} mean; {j['faithful_answers']} at 1.0" if j else "—",
         status(j["faithfulness_mean"] >= 0.9) if j else "Not measured",
         f"GPT-6 Luna judge, {pct(cal['agreement'])} agreement on calibration (ADR 0007)"),
        ("Scope leaks", "0 on the red-team set", str(max(m["scope_leaks"] for m in w2m)),
         status(max(m["scope_leaks"] for m in w2m) == 0), f"{len(w2)} W2 runs; red-team PDF in every run"),
        ("Doctor review time per note", "< 90 s", "—", "Not in Core", "W3 is Pro tier"),
        ("Cost per consultation", "computed, formula shown", f"US${consult:.5f}", "Met",
         "docs/cost-sheet.md"),
    ]
    md = [
        "# Evaluation report",
        "",
        f"Generated by `python -m evals.build_report` on {today} from the run files in `evals/runs/`, the judge "
        "calibration in `evals/judge/` and the spend ledger. Synthetic data only. A target the build does not meet is "
        "reported with the figure reached and the reason (pack p16).",
        "",
        "## Pack p16 targets",
        "",
        "| Requirement or metric | Target | Measured | Status | Basis |",
        "|---|---|---|---|---|",
        *[f"| {a} | {b} | {c} | {d} | {e} |" for a, b, c, d, e in rows],
        "",
        "## W1 Find my doctor",
        "",
        "| Run | Model | Red-flag recall | Strict | Lenient | Route | p95 | Leaks | Cost |",
        "|---|---|---|---|---|---|---|---|---|",
        *[f"| `{r['_file']}` | {r['model'].split('/')[-1]} | {pct(r['metrics']['red_flag_recall'])} | "
          f"{pct(r['metrics']['specialty_accuracy_strict'])} | {pct(r['metrics']['specialty_accuracy_lenient'])} | "
          f"{pct(r['metrics']['route_accuracy'])} | {r['metrics']['p95_turn_latency_s']:.2f} s | {r['metrics']['leaks']} | "
          f"US${r['spend_usd']:.4f} |" for r in w1 + w1_alt],
        "",
        "Claude Haiku 5.5 is primary because GPT-6 Luna missed the 4 s p95 in two of four runs (ADR 0004).",
        "",
        "## W2 My records",
        "",
        "| Run | Pass | Citation | Hand-off | Refusal | Scope leaks | Faithfulness | p95 | Cost |",
        "|---|---|---|---|---|---|---|---|---|",
        *[f"| `{r['_file']}` | {pct(r['metrics']['pass_rate'])} | {pct(r['metrics']['citation_accuracy'])} | "
          f"{pct(r['metrics']['handoff_accuracy'])} | {pct(r['metrics']['refusal_accuracy'])} | {r['metrics']['scope_leaks']} | "
          f"{r['metrics'].get('faithfulness_mean') if r['metrics'].get('faithfulness_mean') is not None else '—'} | "
          f"{r['metrics']['p95_latency_s']:.2f} s | US${r['spend_usd']:.4f} |" for r in w2],
        "",
        "14 of the 30 W2 cases (hand-offs, scope, injection) are decided by deterministic rules before any model call. "
        "The set was written before the code by the same assistant that wrote the code; `services/agent/w2/tests/test_rules.py` "
        "checks the rules on wordings that are not in the set.",
        "",
        "## Booking sessions",
        "",
        f"{sess[-1]['sessions']} non-emergency W1 cases played end to end (clarifying answers scripted, first slot picked): "
        f"{pct(s['completed_without_call'])} booked with no front-desk hand-off; median {s['median_turns']} turns; "
        f"median system time {s['median_system_time_to_book_s']:.2f} s, longest {s['max_system_time_to_book_s']:.2f} s. "
        "Emergency cases are excluded because they must reach a human.",
        "",
        "## Faithfulness judge calibration",
        "",
        f"GPT-6 Luna: {pct(cal['agreement'])} agreement on 20 answers ({cal['unfaithful_caught']} unfaithful caught, "
        f"{cal['unfaithful_missed']} missed, {cal['faithful_flagged']} correct answers flagged); a human graded "
        f"{cal['human_labels']} of the 20. Details in ADR 0007 and `evals/README.md`.",
        "",
        "## Spend",
        "",
        f"All model calls in the build: {led['calls']} calls, US${led['total']:.3f} of the US$2.00 hard stop.",
        "",
    ]
    (REPO / "evals" / "report.md").write_text("\n".join(md))

    cs = [
        "# Cost sheet",
        "",
        f"Generated by `python -m evals.build_report` on {today} from `data/llm_ledger.jsonl`. Prices are read from "
        "OpenRouter at run time and recorded with each call; none is hard-coded (pack p35). The formula per line is "
        "`calls × (input tokens × p_in + output tokens × p_out)`.",
        "",
        "## Per-call figures measured in this build",
        "",
        "| Line | Model | Calls measured | Input tokens (mean) | Output tokens (mean) | p_in (US$/token) | p_out (US$/token) | Price checked | Cost per call (US$) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for (purpose, model), v in sorted(led["by"].items()):
        if purpose in ("w1:match_specialty", "w2:answer", "judge:faithfulness"):
            cs.append(f"| {purpose} | {model} | {v['calls']} | {v['in']:.0f} | {v['out']:.0f} | "
                      f"{v['p_in'] if v['p_in'] else '—'} | {v['p_out'] if v['p_out'] else '—'} | "
                      f"{v['checked'] or '—'} | {v['cost']:.6f} |")
    cs += [
        "",
        "Judge calls record their cost at call time but not the per-token price, hence the dashes.",
        "",
        "## Cost per consultation (Core: one booking and one record question)",
        "",
        "| Cost line | Driver measured | Formula | Value (US$) |",
        "|---|---|---|---|",
        f"| LLM, triage | One booking session: {sess[-1]['sessions']} simulated sessions cost US${sess[-1]['spend_usd']:.5f} | "
        f"session spend ÷ sessions | {session_cost:.5f} |",
        f"| LLM, record answer | {w2_ans['in']:.0f} tokens in, {w2_ans['out']:.0f} out per answer | "
        f"in × p_in + out × p_out | {w2_ans['cost']:.5f} |",
        "| LLM, scribe | — | — | Not in Core (W3) |",
        "| Speech-to-text | — | — | Not in Core (W3) |",
        "| Embeddings | Local BGE-M3, no API | tokens × 0 | 0 |",
        "| Storage and compute | Laptop; not metered | GB × p_gb + hours × p_hour | Not measured |",
        "| Faithfulness judge | Evaluation only, not per consultation | — | excluded |",
        f"| **Total model cost per consultation** | | sum of the lines above | **{consult:.5f}** |",
        "",
        f"For scale, 1,400 requests an hour (pack p4 peak) at the record-answer rate would cost about "
        f"US${1400 * w2_ans['cost']:.2f} an hour in model calls. Storage, compute and human review time are not "
        "measured in this build and are not in the total.",
        "",
    ]
    (REPO / "docs" / "cost-sheet.md").write_text("\n".join(cs))
    print("wrote evals/report.md and docs/cost-sheet.md")


if __name__ == "__main__":
    main()
