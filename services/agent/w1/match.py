"""Specialty match: one model call against the reviewed crosswalk (pack p25: 'match specialty').

The model sees the 33 network specialties and the 41 conditions with their usual symptoms and its
reviewed specialty. It returns a specialty, an alternative, a confidence and, when unsure, one
clarifying question. It may also raise an emergency the rules missed; it can never clear one.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator

from data.transforms.common import PROCESSED, REFERENCE
from services.common.llm import ModelClient
from services.common.scrub import scrub

PROMPT_VERSION = "w1_match_v1"


@lru_cache(maxsize=1)
def specialties() -> list[str]:
    return pd.read_csv(REFERENCE / "specialties.csv")["name"].tolist()


@lru_cache(maxsize=1)
def crosswalk_text() -> str:
    xw = pd.read_csv(REFERENCE / "condition_specialty_crosswalk.csv", dtype=str, keep_default_na=False)
    sym = pd.read_parquet(PROCESSED / "condition_symptom.parquet")
    top = (sym.sort_values("severity", ascending=False).groupby("condition")["symptom"]
           .apply(lambda s: ", ".join(x.replace("_", " ") for x in s.head(8))))
    lines = []
    for r in xw.itertuples():
        alt = f" (or {r.alternative_specialty})" if r.alternative_specialty else ""
        lines.append(f"- {r.display_name}: {top.get(r.condition, '')} -> {r.specialty}{alt}")
    return "\n".join(lines)


class Match(BaseModel):
    model_config = ConfigDict(extra="forbid")
    possible_emergency: bool = Field(description="True only if the words suggest an emergency needing care now")
    emergency_reason: str | None = None
    specialty: str | None = Field(description="Exactly one name from the specialty list, or null when unsure")
    alternative_specialty: str | None = None
    confidence: float = Field(ge=0, le=1)
    clarifying_question: str | None = Field(default=None, description="One short question when confidence < 0.6")

    @field_validator("specialty", "alternative_specialty")
    @classmethod
    def known_specialty(cls, v: str | None) -> str | None:
        if v is not None and v not in specialties():
            raise ValueError(f"unknown specialty {v!r}")
        return v


def system_prompt() -> str:
    return f"""You route a patient of Sahyog Health Network (Pune and Hyderabad, India) to ONE outpatient specialty.
You never diagnose and never name a disease to the patient. Patients may write in English or Hindi-English.

Specialties (use one of these names exactly):
{", ".join(specialties())}

Reviewed guide: usual symptoms -> specialty (or alternative):
{crosswalk_text()}

Rules:
- Pick the specialty a front-desk nurse would book for these symptoms; use the guide when it fits.
- confidence is your probability that the specialty is right. If the message is too vague to choose
  (for example "not feeling well" or a single word), set confidence below 0.6, specialty null, and ask
  ONE short clarifying question about the main symptom, where it is and how long it has lasted.
- Set possible_emergency true only for signs that need care within the hour (for example chest pain,
  trouble breathing, stroke signs, heavy bleeding, fainting, self-harm thoughts). Otherwise false.
Return JSON matching the schema."""


def match(client: ModelClient, history: list[str], age: int | None) -> Match:
    words = scrub(" | ".join(history))
    user = f"Patient age: {age if age is not None else 'not given'}\nPatient's words (oldest first): {words}"
    return client.structured(purpose="w1:match_specialty", system=system_prompt(), user=user, schema=Match,
                             max_tokens=400, temperature=0.0)
