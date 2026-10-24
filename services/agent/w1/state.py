from __future__ import annotations

from typing import Literal, TypedDict

Route = Literal["emergency_desk", "clarify", "front_desk", "choose_slot", "booked"]


class W1State(TypedDict, total=False):
    # inputs (patient_id comes from the auth context, never from the model)
    patient_id: str | None
    message: str
    age: int | None
    language: str | None
    now: str                      # ISO time used for slot search; injected so runs are reproducible
    # working state
    history: list[str]
    red_flags: list[str]
    red_flag_source: Literal["rules", "model"] | None
    specialty: str | None
    alternative: str | None
    confidence: float | None
    clarify_count: int
    clarifying_question: str | None
    candidates: list[dict]
    appointment_id: str | None
    ticket_id: str | None
    route: Route
    reply: str
