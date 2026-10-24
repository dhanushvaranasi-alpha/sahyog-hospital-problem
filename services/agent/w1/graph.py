"""W1 Find my doctor (pack p25): intake -> red-flag rules -> specialty match -> shortlist -> patient picks
(interrupt) -> book and notify. Red flags leave the graph for a human; two unclear turns hand off to the
front desk; a model failure degrades to the front desk rather than guessing (p36).
"""
from __future__ import annotations

from datetime import datetime

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from services.agent.w1 import red_flags
from services.agent.w1.directory import Directory, SlotTaken, as_dict
from services.agent.w1.match import match as match_specialty
from services.agent.w1.state import W1State
from services.common.llm import BudgetExceeded, ModelClient, ModelOutputInvalid

CONFIDENCE_FLOOR = 0.6       # p14: below this, ask one clarifying question
MAX_CLARIFY = 2              # p25: at most two, then the front desk
DEFAULT_QUESTION = "Could you tell me your main symptom, where it is, and how long you have had it?"
FRONT_DESK_REPLY = "I'd like a member of our front-desk team to help you choose the right doctor. They will call you shortly."


def build(directory: Directory, client: ModelClient, checkpointer=None):
    def intake(s: W1State) -> W1State:
        return {"history": [s["message"]], "clarify_count": 0, "red_flags": [], "red_flag_source": None}

    def red_flag_check(s: W1State) -> W1State:
        fired = red_flags.check(" ".join(s["history"]))
        return {"red_flags": fired, "red_flag_source": "rules" if fired else None}

    def match(s: W1State) -> W1State:
        try:
            m = match_specialty(client, s["history"], s.get("age"))
        except (ModelOutputInvalid, BudgetExceeded) as e:
            return {"route": "front_desk", "specialty": None, "confidence": None,
                    "reply": FRONT_DESK_REPLY, "clarifying_question": f"model unavailable: {type(e).__name__}"}
        if m.possible_emergency:   # the model may add a red flag, never remove one
            return {"red_flags": ["MODEL"], "red_flag_source": "model"}
        return {"specialty": m.specialty, "alternative": m.alternative_specialty, "confidence": m.confidence,
                "clarifying_question": m.clarifying_question}

    def emergency(s: W1State) -> W1State:
        ticket = directory.handoff("emergency_desk", s.get("patient_id"),
                                   {"rules": s["red_flags"], "source": s["red_flag_source"]})
        return {"route": "emergency_desk", "ticket_id": ticket, "reply": red_flags.reply_for(s["red_flags"]),
                "candidates": []}

    def clarify(s: W1State) -> W1State:
        question = s.get("clarifying_question") or DEFAULT_QUESTION
        answer = interrupt({"type": "clarify", "question": question})
        return {"history": s["history"] + [str(answer)], "clarify_count": s.get("clarify_count", 0) + 1,
                "route": "clarify"}

    def front_desk(s: W1State) -> W1State:
        ticket = directory.handoff("front_desk", s.get("patient_id"), {"history": s["history"][-3:]})
        return {"route": "front_desk", "ticket_id": ticket, "reply": FRONT_DESK_REPLY}

    def shortlist(s: W1State) -> W1State:
        now = datetime.fromisoformat(s["now"])
        cands = directory.shortlist(s["specialty"], now, 3, s.get("language"))
        if not cands and s.get("alternative"):
            cands = directory.shortlist(s["alternative"], now, 3, s.get("language"))
        return {"candidates": [as_dict(c) for c in cands]}

    def choose_slot(s: W1State) -> W1State:
        options = s["candidates"]
        choice = interrupt({"type": "choose_slot", "specialty": s["specialty"], "options": options})
        slot_id, key = choice["slot_id"], choice["idempotency_key"]
        if slot_id not in {c["slot_id"] for c in options}:
            return {"route": "front_desk", "reply": FRONT_DESK_REPLY}
        try:
            appt = directory.book(s["patient_id"], slot_id, key)
        except SlotTaken:
            return {"route": "choose_slot", "candidates": [], "appointment_id": None}
        chosen = next(c for c in options if c["slot_id"] == slot_id)
        msg = (f"Booked: {chosen['doctor_name']} ({chosen['specialty']}) at {chosen['clinic_name']}, "
               f"{chosen['starts_at']}. Appointment {appt}.")
        directory.notify(s["patient_id"], msg)
        return {"route": "booked", "appointment_id": appt, "reply": msg}

    def after_rules(s: W1State) -> str:
        return "emergency" if s["red_flags"] else "match"

    def after_match(s: W1State) -> str:
        if s.get("red_flags"):
            return "emergency"
        if s.get("route") == "front_desk":
            return "front_desk"
        if s.get("specialty") and (s.get("confidence") or 0) >= CONFIDENCE_FLOOR:
            return "shortlist"
        return "clarify" if s.get("clarify_count", 0) < MAX_CLARIFY else "front_desk"

    def after_shortlist(s: W1State) -> str:
        return "choose_slot" if s["candidates"] else "front_desk"

    def after_choose(s: W1State) -> str:
        if s.get("route") == "choose_slot":          # slot taken meanwhile: fresh shortlist
            return "shortlist"
        return END

    g = StateGraph(W1State)
    for name, fn in [("intake", intake), ("red_flag_check", red_flag_check), ("match", match),
                     ("emergency", emergency), ("clarify", clarify), ("front_desk", front_desk),
                     ("shortlist", shortlist), ("choose_slot", choose_slot)]:
        g.add_node(name, fn)
    g.add_edge(START, "intake")
    g.add_edge("intake", "red_flag_check")
    g.add_conditional_edges("red_flag_check", after_rules, ["emergency", "match"])
    g.add_conditional_edges("match", after_match, ["emergency", "front_desk", "shortlist", "clarify"])
    g.add_edge("clarify", "red_flag_check")
    g.add_conditional_edges("shortlist", after_shortlist, ["choose_slot", "front_desk"])
    g.add_conditional_edges("choose_slot", after_choose, ["shortlist", END])
    g.add_edge("emergency", END)
    g.add_edge("front_desk", END)
    return g.compile(checkpointer=checkpointer)
