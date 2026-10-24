"""One client for every model call (house rule 6: schema, timeout, fallback, trace id).

- OpenRouter through the OpenAI-compatible client, so the vendor is a config value (ADR 0001).
- Output is validated against a pydantic schema; a reply that fails validation is rejected, not repaired.
- Every call is written to an append-only spend ledger; a call that would start above the
  hard stop raises BudgetExceeded before any request is sent (architecture decision 15).
- Prices come from OpenRouter's model list at run time and are recorded with the date (pack p35);
  no price is hard-coded in the repository.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Type, TypeVar

import httpx
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ValidationError

REPO = Path(__file__).resolve().parents[2]
load_dotenv(REPO / ".env")

LEDGER = Path(os.environ.get("LLM_LEDGER_PATH", REPO / "data" / "llm_ledger.jsonl"))
BASE_URL = "https://openrouter.ai/api/v1"
T = TypeVar("T", bound=BaseModel)


class BudgetExceeded(RuntimeError):
    pass


class ModelOutputInvalid(RuntimeError):
    pass


@dataclass(frozen=True)
class Price:
    model: str
    usd_per_input_token: float
    usd_per_output_token: float
    checked_at: str


_PRICE_CACHE: dict[str, Price] = {}


def price_for(model: str) -> Price:
    if model not in _PRICE_CACHE:
        resp = httpx.get(f"{BASE_URL}/models", timeout=20)
        resp.raise_for_status()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for m in resp.json()["data"]:
            p = m.get("pricing", {})
            try:
                _PRICE_CACHE[m["id"]] = Price(m["id"], float(p["prompt"]), float(p["completion"]), now)
            except (KeyError, TypeError, ValueError):
                continue
    if model not in _PRICE_CACHE:
        raise RuntimeError(f"no OpenRouter price for {model}; refusing to call a model we cannot cost")
    return _PRICE_CACHE[model]


def spent_usd() -> float:
    if not LEDGER.exists():
        return 0.0
    return sum(json.loads(line)["cost_usd"] for line in LEDGER.read_text().splitlines() if line.strip())


def _record(entry: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def strict_json_schema(schema: dict) -> dict:
    """OpenAI-family providers require every object to list ALL its properties as required and to forbid
    extra properties. Optional fields stay optional by allowing null; pydantic still validates the reply."""
    import copy

    def fix(node):
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                props = node.get("properties", {})
                node["required"] = list(props)
                node["additionalProperties"] = False
                for v in props.values():
                    v.pop("default", None)
            for v in node.values():
                fix(v)
        elif isinstance(node, list):
            for v in node:
                fix(v)
        return node

    return fix(copy.deepcopy(schema))


class ModelClient:
    def __init__(self, primary: str | None = None, fallback: str | None = None, timeout_s: float = 60.0,
                 budget_usd: float | None = None):
        self.primary = primary or os.environ["LLM_PRIMARY_MODEL"]
        self.fallback = fallback or os.environ.get("LLM_FALLBACK_MODEL")
        self.budget_usd = budget_usd if budget_usd is not None else float(os.environ.get("LLM_BUDGET_USD_HARD_STOP", "2.00"))
        client = OpenAI(base_url=BASE_URL, api_key=os.environ["OPENROUTER_API_KEY"], timeout=timeout_s, max_retries=0)
        if os.environ.get("LANGSMITH_TRACING", "").lower() == "true":
            try:
                from langsmith.wrappers import wrap_openai
                client = wrap_openai(client)
            except ImportError:
                pass
        self._client = client

    def structured(self, *, purpose: str, system: str, user: str, schema: Type[T], max_tokens: int = 2000,
                   temperature: float = 0.7, attempts_per_model: int = 2) -> T:
        """Return `schema` parsed from the model's JSON reply, trying primary then fallback."""
        last_error: Exception | None = None
        for model in [m for m in (self.primary, self.fallback) if m]:
            for attempt in range(1, attempts_per_model + 1):
                if spent_usd() >= self.budget_usd:
                    raise BudgetExceeded(f"spent {spent_usd():.4f} USD >= hard stop {self.budget_usd:.2f} USD")
                trace_id = uuid.uuid4().hex
                started = time.monotonic()
                try:
                    resp = self._client.chat.completions.create(
                        model=model,
                        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                        response_format={"type": "json_schema",
                                         "json_schema": {"name": schema.__name__,
                                                                         "schema": strict_json_schema(schema.model_json_schema())}},
                        max_tokens=max_tokens,
                        temperature=temperature,
                        extra_headers={"X-Title": "sahyog-care-companion"},
                    )
                except Exception as e:  # network, rate limit, provider error -> next attempt / model
                    last_error = e
                    _record({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "trace_id": trace_id,
                             "purpose": purpose, "model": model, "attempt": attempt, "input_tokens": 0,
                             "output_tokens": 0, "cost_usd": 0.0, "latency_s": round(time.monotonic() - started, 3),
                             "schema_valid": False, "finish_reason": None, "error": f"provider: {str(e)[:300]}"})
                    time.sleep(min(2 ** attempt, 8))
                    continue
                usage = resp.usage
                price = price_for(model)
                cost = usage.prompt_tokens * price.usd_per_input_token + usage.completion_tokens * price.usd_per_output_token
                content = resp.choices[0].message.content or ""
                ok, error = True, None
                try:
                    parsed = schema.model_validate_json(content)
                except ValidationError as e:
                    ok, last_error = False, e
                    error = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:3])
                _record({
                    "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "trace_id": trace_id, "purpose": purpose, "model": model, "attempt": attempt,
                    "input_tokens": usage.prompt_tokens, "output_tokens": usage.completion_tokens,
                    "usd_per_input_token": price.usd_per_input_token, "usd_per_output_token": price.usd_per_output_token,
                    "price_checked_at": price.checked_at, "cost_usd": round(cost, 8),
                    "latency_s": round(time.monotonic() - started, 3), "schema_valid": ok,
                    "finish_reason": resp.choices[0].finish_reason, "error": error,
                })
                if ok:
                    return parsed
        raise ModelOutputInvalid(f"{purpose}: no valid reply from {self.primary} or {self.fallback}: {last_error}")
