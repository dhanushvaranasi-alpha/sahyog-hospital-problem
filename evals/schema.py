"""Eval case format (pack p45): every case names its source and its author, so a failing case
can be argued about and a passing one trusted. Sets live in evals/sets/*.jsonl."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- W1 Find my doctor ----------
class W1Input(Strict):
    message: str = Field(min_length=1)
    age: int | None = Field(default=None, ge=0, le=110)
    language: Literal["en", "hi-en"] = "en"


class W1Expect(Strict):
    red_flag: bool
    route: Literal["emergency_desk", "booking", "clarify"]
    specialty: str | None = None                     # primary: strict accuracy
    acceptable_specialties: list[str] = []           # primary + alternatives: lenient accuracy


# ---------- W2 My records ----------
class Consent(Strict):
    patient_id: str
    grantee_id: str
    state: Literal["valid", "expired", "revoked"]


class W2Input(Strict):
    caller_patient_id: str                           # identity from auth, never from the prompt
    subject_patient_id: str                          # whose records the question is about
    question: str = Field(min_length=1)
    language: Literal["en", "hi-en"] = "en"
    uploads: list[str] = []                          # extra documents uploaded by the caller (red-team)
    consents: list[Consent] = []                     # fixtures beyond the seeded persona consent


class W2Expect(Strict):
    route: Literal["answer", "not_in_record", "handoff_doctor", "refuse"]
    cites: list[str] = []                            # report ids the answer must cite
    answer_contains: list[str] = []                  # strings that must appear in the answer


class EvalCase(Strict):
    id: str = Field(pattern=r"^w[12]-\d{3}$")
    workflow: Literal["w1", "w2"]
    category: str
    input: W1Input | W2Input
    expect: W1Expect | W2Expect
    must_not: list[str] = []                         # strings that must never appear in the output
    source: str                                      # where the case comes from (pack page, report id, assumption)
    added_by: str
    version: int = 1
