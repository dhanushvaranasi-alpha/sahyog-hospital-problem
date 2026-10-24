"""Pydantic models shared by the generators and the ingest code (pack p20: the schema sits between LLM and code)."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LANGS = Literal["en", "hi", "mr", "te"]


class Strict(BaseModel):
    """additionalProperties: false in the JSON schema; OpenAI-family providers refuse schemas without it."""
    model_config = ConfigDict(extra="forbid")


class DoctorDraft(Strict):
    slot: int = Field(description="Row number from the request, echoed back unchanged")
    name: str = Field(min_length=5, max_length=60, description="Doctor's full name, starting with 'Dr. '")
    gender: Literal["female", "male"]
    languages: list[LANGS] = Field(min_length=1, max_length=4)
    years_in_practice: int = Field(ge=1, le=45)

    @field_validator("name")
    @classmethod
    def starts_with_dr(cls, v: str) -> str:
        if not v.startswith("Dr. "):
            raise ValueError("name must start with 'Dr. '")
        return v

    @field_validator("languages")
    @classmethod
    def english_included(cls, v: list[str]) -> list[str]:
        if "en" not in v:
            raise ValueError("every doctor speaks English in this network")
        return list(dict.fromkeys(v))


class DoctorBatch(Strict):
    doctors: list[DoctorDraft]


class ReportSection(Strict):
    heading: str = Field(min_length=2, max_length=60)
    body: str = Field(min_length=10, max_length=2500)


class ReportDraft(Strict):
    title: str = Field(min_length=5, max_length=120)
    report_type: Literal["lab", "radiology", "cardiology", "discharge summary"]
    sections: list[ReportSection] = Field(min_length=2, max_length=8)
    impression: str = Field(min_length=10, max_length=1200, description="Findings in plain clinical words; no new diagnosis")

    @model_validator(mode="after")
    def no_demographics_in_body(self) -> "ReportDraft":
        """The header carries age and sex; text copied from a source note about another person must not contradict it."""
        text = " ".join([self.title, self.impression] + [f"{x.heading} {x.body}" for x in self.sections])
        if AGE_RE.search(text):
            raise ValueError("report text states an age; refer to 'the patient' instead")
        if PRONOUN_RE.search(text):
            raise ValueError("report text uses a gendered pronoun or title; refer to 'the patient' instead")
        return self


AGE_RE = re.compile(r"\b\d{1,3}[- ](year|yr)s?[- ]old\b|\baged? \d{1,3}\b|\b\d{1,3}\s*(y/o|yo)\b", re.I)
PRONOUN_RE = re.compile(r"\b(he|she|his|hers?|him|himself|herself|Mr|Mrs|Ms)\b", re.I)
