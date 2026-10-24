"""W1 graph paths with a scripted model and the in-memory directory (no network, no database)."""
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from services.agent.w1 import red_flags
from services.agent.w1.directory import InMemoryDirectory
from services.agent.w1.graph import build
from services.agent.w1.match import Match
from services.common.llm import ModelOutputInvalid

NOW = "2026-10-26T08:00:00+05:30"


class ScriptedClient:
    """Returns the queued Match objects in order; raises if the graph calls the model unexpectedly."""
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), 0

    def structured(self, **kw):
        self.calls += 1
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def m(specialty=None, confidence=0.9, emergency=False, question=None, alt=None):
    return Match(possible_emergency=emergency, emergency_reason=None, specialty=specialty, alternative_specialty=alt,
                 confidence=confidence, clarifying_question=question)


@pytest.fixture
def directory():
    return InMemoryDirectory()


def run(graph, thread, payload):
    return graph.invoke(payload, {"configurable": {"thread_id": thread}})


def start(msg, age=None):
    return {"patient_id": "P-PRIYA", "message": msg, "age": age, "language": "en", "now": NOW}


def test_rules_fire_before_any_model_call(directory):
    client = ScriptedClient()
    g = build(directory, client, InMemorySaver())
    out = run(g, "t1", start("my mother has a dull ache in her left arm and some breathlessness", 62))
    assert out["route"] == "emergency_desk" and client.calls == 0
    assert "112" in out["reply"] and not out.get("candidates")
    assert directory.events[-1]["resource_type"] == "emergency_desk"


def test_model_can_add_a_red_flag(directory):
    g = build(directory, ScriptedClient(m(emergency=True)), InMemorySaver())
    out = run(g, "t2", start("I feel something very wrong in my head, worst headache ever"))
    assert out["route"] == "emergency_desk" and out["red_flag_source"] == "model"


def test_suicidal_intent_gets_the_helpline(directory):
    out = run(build(directory, ScriptedClient(), InMemorySaver()), "t3", start("I want to end my life"))
    assert "14416" in out["reply"] and out["route"] == "emergency_desk"


def test_low_confidence_asks_then_matches_then_books(directory):
    client = ScriptedClient(m(None, 0.3, question="Where is the pain?"), m("Orthopaedics", 0.85))
    g = build(directory, client, InMemorySaver())
    out = run(g, "t4", start("pain"))
    assert out["__interrupt__"][0].value == {"type": "clarify", "question": "Where is the pain?"}
    out = run(g, "t4", Command(resume="lower back, three weeks, worse when sitting"))
    options = out["__interrupt__"][0].value["options"]
    assert len(options) == 3 and {o["specialty"] for o in options} == {"Orthopaedics"}
    out = run(g, "t4", Command(resume={"slot_id": options[0]["slot_id"], "idempotency_key": "k-t4"}))
    assert out["route"] == "booked" and out["appointment_id"]
    assert any(e["action"] == "notify" for e in directory.events)


def test_two_unclear_turns_hand_off_to_front_desk(directory):
    g = build(directory, ScriptedClient(m(None, 0.2), m(None, 0.3), m(None, 0.4)), InMemorySaver())
    run(g, "t5", start("not well"))
    run(g, "t5", Command(resume="still not well"))
    out = run(g, "t5", Command(resume="hard to say"))
    assert out["route"] == "front_desk" and "front-desk" in out["reply"]


def test_model_failure_degrades_to_front_desk(directory):
    g = build(directory, ScriptedClient(ModelOutputInvalid("down")), InMemorySaver())
    out = run(g, "t6", start("itchy rash on my arms"))
    assert out["route"] == "front_desk"


def test_booking_retry_returns_the_same_appointment(directory):
    slot = directory.shortlist("Dermatology", __import__("datetime").datetime.fromisoformat(NOW))[0].slot_id
    a1 = directory.book("P-PRIYA", slot, "same-key")
    a2 = directory.book("P-PRIYA", slot, "same-key")
    assert a1 == a2 and len([e for e in directory.events if e["action"] == "write"]) == 1


def test_a_taken_slot_leads_to_a_fresh_shortlist(directory):
    g = build(directory, ScriptedClient(m("Dermatology", 0.9)), InMemorySaver())
    out = run(g, "t7", start("itchy red patches on my skin"))
    first = out["__interrupt__"][0].value["options"][0]["slot_id"]
    directory.book("P-OTHER", first, "someone-else")            # taken between offer and pick
    out = run(g, "t7", Command(resume={"slot_id": first, "idempotency_key": "k-t7"}))
    new_options = out["__interrupt__"][0].value["options"]
    assert first not in {o["slot_id"] for o in new_options}


def test_shortlist_offers_three_earliest_doctors(directory):
    from datetime import datetime
    c = directory.shortlist("General Medicine", datetime.fromisoformat(NOW))
    assert len(c) == 3 and len({x.doctor_id for x in c}) == 3
    assert all(x.starts_at >= NOW for x in c)


@pytest.mark.parametrize("text", [
    "my chest feels heavy and tight since an hour",          # held-out phrasings, not in the eval set
    "he collapsed at the bus stop",
    "her lips are swelling after eating peanuts",
    "I keep thinking about suicide",
    "sugar is 38 and she is confused",
    "baby is having fits",
    "saans lene mein bahut takleef ho rahi hai",
])
def test_red_flag_rules_on_unseen_phrasings(text):
    assert red_flags.check(text)


@pytest.mark.parametrize("text", [
    "I need my chest x-ray report explained",
    "doing breathing exercises for anxiety, any yoga doctor?",
    "my HbA1c was 6.5% last month",
    "skin rash on my arm for a week",
])
def test_red_flag_rules_do_not_fire_on_routine_text(text):
    assert not red_flags.check(text)
