"""Faithfulness judge: ragas 0.4.3 Faithfulness (architecture decision 18).

ragas splits an answer into atomic statements, then checks each statement against the excerpts
(natural-language inference). Score = supported statements / all statements. An answer counts as
faithful only at 1.0: one unsupported claim fails it, the same rule the human grader used.

The judge calls OpenRouter through the same key, budget hard stop and spend ledger as every other
model call: an httpx response hook records each call's tokens and cost in data/llm_ledger.jsonl.
Only de-identified text is judged (the excerpts and the model's draft answer, before tokens are
restored), so nothing identifying leaves the boundary.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from services.common.llm import BASE_URL, BudgetExceeded, _record, price_for, spent_usd

PURPOSE = "judge:faithfulness"

# The answer prompt requires a closing hand-off to the patient's doctor ("your doctor will go through
# this with you"). No report contains that sentence, so the judge counted it as an unsupported claim
# on almost every answer. It is a required instruction to the patient, not a statement about the
# record, so it is removed before judging.
_DOC = r"(?:your|their|her|his|a|the treating) doctor (?:will|can|may) (?:go through|go over|explain|review|discuss)"
# a whole sentence that is only the hand-off ...
HANDOFF_SENTENCE = re.compile(rf"(?:(?<=[.!?])|^)\s*{_DOC}[^.!?]*[.!?]", re.I)
# ... or a trailing clause on a sentence that also states facts: keep the facts, drop the clause
HANDOFF_CLAUSE = re.compile(rf",?\s*(?:and|which|so)?\s*{_DOC}[^.!?]*(?=[.!?])", re.I)


def strip_handoff(answer: str) -> str:
    out = HANDOFF_SENTENCE.sub("", answer)
    out = HANDOFF_CLAUSE.sub("", out)
    return re.sub(r"\s{2,}", " ", out).strip()


def _ledger_hook(model: str):
    async def on_response(response: httpx.Response) -> None:
        started = response.request.extensions.get("sahyog_started", time.monotonic())
        await response.aread()
        try:
            body = json.loads(response.content)
            usage = body.get("usage") or {}
            served = body.get("model") or model
        except Exception:
            usage, served = {}, model
        inp, out = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        try:
            p = price_for(model)
            cost = inp * p.usd_per_input_token + out * p.usd_per_output_token
        except Exception:
            cost = 0.0
        _record({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "trace_id": uuid.uuid4().hex,
                 "purpose": PURPOSE, "model": model, "served_model": served, "attempt": 1, "input_tokens": inp,
                 "output_tokens": out, "cost_usd": round(cost, 8), "latency_s": round(time.monotonic() - started, 3),
                 "schema_valid": response.status_code == 200, "finish_reason": None,
                 "error": None if response.status_code == 200 else f"http {response.status_code}"})

    async def on_request(request: httpx.Request) -> None:
        request.extensions["sahyog_started"] = time.monotonic()

    return on_request, on_response


@dataclass
class Verdict:
    score: float
    faithful: bool
    statements: list[dict]          # [{"statement", "verdict" (1 supported / 0 not), "reason"}]


class FaithfulnessJudge:
    def __init__(self, model: str | None = None, budget_usd: float | None = None):
        from openai import AsyncOpenAI
        from ragas.llms import llm_factory
        from ragas.metrics.collections import Faithfulness

        self.model = model or os.environ.get("JUDGE_MODEL") or os.environ["LLM_PRIMARY_MODEL"]
        self.budget = budget_usd if budget_usd is not None else float(os.environ.get("LLM_BUDGET_USD_HARD_STOP", "2.00"))
        req, resp = _ledger_hook(self.model)
        client = AsyncOpenAI(base_url=BASE_URL, api_key=os.environ["OPENROUTER_API_KEY"], max_retries=2, timeout=60,
                             http_client=httpx.AsyncClient(event_hooks={"request": [req], "response": [resp]}))
        # ragas defaults to max_tokens=1024, which truncated the statement list on long answers
        self.metric = Faithfulness(llm=llm_factory(self.model, client=client, max_tokens=4096, temperature=0.0))

    async def ajudge(self, question: str, answer: str, excerpts: str) -> Verdict:
        if spent_usd() >= self.budget:
            raise BudgetExceeded(f"spent {spent_usd():.4f} USD >= hard stop {self.budget:.2f} USD")
        # The same two steps as Faithfulness.ascore, kept separately so the per-statement verdicts are visible.
        answer = strip_handoff(answer)
        statements = await self.metric._create_statements(question, answer)
        if not statements:
            return Verdict(score=float("nan"), faithful=False, statements=[])
        verdicts = await self.metric._create_verdicts(statements, excerpts)
        score = float(self.metric._compute_score(verdicts))
        rows = [{"statement": v.statement, "verdict": int(v.verdict), "reason": v.reason} for v in verdicts.statements]
        return Verdict(score=score, faithful=score >= 1.0, statements=rows)

    def judge(self, question: str, answer: str, excerpts: str) -> Verdict:
        return asyncio.run(self.ajudge(question, answer, excerpts))
