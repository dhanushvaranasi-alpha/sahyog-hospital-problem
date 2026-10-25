"""W2 Ask graph (pack p26; architecture §3):

    access -> guard -> retrieve -> answer -> verify -> finish
       |        |         |                    |
     refuse   refuse    not_in_record       not_in_record / handoff
              handoff

- access:   caller_id comes from auth, never from the text. Own records, or a consent row that is
            valid now (expired and revoked consents are refused). Plain code.
- guard:    deterministic scope and safety rules (rules.py) before any retrieval.
- retrieve: the subject's chunks only, ranked in one query with the patient filter (store.search).
- answer:   one model call over de-identified excerpts; the question is de-identified too.
- verify:   reject, never repair: every citation must name a retrieved report, every number in the
            answer must appear in the excerpts, and advice wording sends the question to a doctor.
- finish:   tokens are put back for the entitled reader; one audit_event per document read.
"""
from __future__ import annotations

import re
import time
import uuid
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from services.agent.w2 import rules
from services.agent.w2.answer import answer as answer_call
from services.agent.w2.answer import format_excerpts
from services.common.embed import Embedder
from services.common.llm import BudgetExceeded, ModelClient, ModelOutputInvalid
from services.common.phi import TOKEN, TokenMap, deidentify, known_identifiers, person_names, reidentify
from services.records.store import ChunkRow, RecordStore

Route = Literal["answer", "not_in_record", "handoff_doctor", "refuse", "unavailable"]
TOP_K = 8

REFUSE_REPLY = ("I can only share your own records, or the records of someone who has given you consent "
                "to see them. I can't help with that request.")
HANDOFF_REPLY = ("That's a question for your doctor: I can't give a diagnosis or advise on medicines or doses. "
                 "I've noted it for your care team, and you can also raise it at your next visit.")
UNAVAILABLE_REPLY = "I can't answer that right now. Please try again shortly, or ask the front desk."
NOT_FOUND_REPLY = "I couldn't find that in the reports on your file. Your doctor can help if you think something is missing."


class W2State(TypedDict, total=False):
    caller_id: str
    caller_role: str
    subject_id: str
    question: str
    trace_id: str
    grant: str
    purpose: str
    rule: str | None
    route: Route
    reason: str | None
    tokens: dict[str, tuple[str, str]]
    question_deid: str
    chunks: list[ChunkRow]
    draft: dict
    reply: str
    citations: list[dict]
    audit_ids: list[int]


NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*")


def ungrounded_numbers(text: str, corpus: str) -> list[str]:
    return [n for n in NUMBER.findall(text)
            if not re.search(rf"(?<![\d.]){re.escape(n)}(?![\d])", corpus)]


def build_ask_graph(store: RecordStore, client: ModelClient | None, embedder: Embedder):
    def audit(state: W2State, action: str, resource_type: str, resource_id: str) -> int:
        return store.audit(actor_id=state["caller_id"], actor_role=state.get("caller_role", "patient"),
                           purpose=state.get("purpose", "self"), action=action, resource_type=resource_type,
                           resource_id=resource_id, trace_id=state.get("trace_id"))

    def access(state: W2State) -> W2State:
        g = store.grant(state["subject_id"], state["caller_id"])
        purpose = "self" if g.state == "self" else f"caregiver:{g.consent_id}" if g.state == "valid" else "none"
        if g.state in ("self", "valid"):
            return {"grant": g.state, "purpose": purpose}
        return {"grant": g.state, "purpose": purpose, "route": "refuse", "reason": f"consent {g.state}"}

    def guard(state: W2State) -> W2State:
        hit = rules.check(state["question"], state["subject_id"], state["caller_id"])
        if hit is None:
            allowed = set()
            for pid in (state["subject_id"], state["caller_id"]):
                p = store.patient(pid)
                if p:
                    allowed |= {p.name.lower(), *p.name.lower().split()}
            for name in person_names(state["question"]):
                if name.lower() not in allowed and store.patients_named(name):
                    hit = rules.RuleHit("scope", "names_another_patient")
                    break
        if hit is None:
            return {"rule": None}
        route: Route = "refuse" if hit.kind == "scope" else "handoff_doctor"
        return {"rule": hit.rule, "route": route, "reason": f"rule {hit.rule}"}

    def retrieve(state: W2State) -> W2State:
        tokens = TokenMap()
        for pid in (state["subject_id"], state["caller_id"]):
            p = store.patient(pid)
            if p:
                for ent, val in known_identifiers(name=p.name, phone=p.phone, abha=p.abha_id, patient_id=p.patient_id):
                    tokens.token_for(ent, val)
        known = [(ent, val) for ent, val in tokens.tokens.values()]
        q, tokens = deidentify(state["question"], known, tokens, ner=True)
        qvec = embedder.embed([q])[0]
        chunks = store.search(state["subject_id"], qvec, TOP_K)
        # Documents number their tokens independently; map them onto this request's token map.
        doc_tokens = store.tokens(sorted({c.doc_id for c in chunks}))
        for c in chunks:
            m = doc_tokens.get(c.doc_id, {})
            c.text = TOKEN.sub(lambda t, m=m: tokens.token_for(*m[t.group(0)]) if t.group(0) in m else t.group(0), c.text)
            c.title = TOKEN.sub(lambda t, m=m: tokens.token_for(*m[t.group(0)]) if t.group(0) in m else t.group(0), c.title)
        out: W2State = {"question_deid": q, "tokens": dict(tokens.tokens), "chunks": chunks}
        if not chunks:
            out.update(route="not_in_record", reason="no documents on file")
        return out

    def answer(state: W2State) -> W2State:
        docs = store.documents(state["subject_id"])
        relation = "the patient" if state["grant"] == "self" else "a family member with the patient's valid consent"
        try:
            a = answer_call(client, state["question_deid"], state["chunks"], docs, relation)
        except (ModelOutputInvalid, BudgetExceeded) as e:
            return {"route": "unavailable", "reason": type(e).__name__}
        return {"draft": a.model_dump()}

    def verify(state: W2State) -> W2State:
        d = state["draft"]
        refs = {c.source_ref for c in state["chunks"]}
        if d["route"] == "handoff_doctor" or rules.advice_in(d["answer"]):
            return {"route": "handoff_doctor", "reason": "model handoff" if d["route"] == "handoff_doctor" else "advice wording"}
        if d["route"] == "not_in_record":
            return {"route": "not_in_record", "reason": "model: not in record"}
        cited = [c for c in d["citations"] if c["report_id"] in refs]
        if not cited or len(cited) != len(d["citations"]):
            return {"route": "not_in_record", "reason": "citation not among retrieved reports"}
        corpus = format_excerpts(state["chunks"]) + "\n" + state["question_deid"]
        bad = ungrounded_numbers(d["answer"], corpus)
        if bad:
            return {"route": "not_in_record", "reason": f"numbers not in excerpts: {bad[:3]}"}
        return {"route": "answer", "citations": cited}

    def finish(state: W2State) -> W2State:
        route = state["route"]
        ids: list[int] = []
        if route == "refuse":
            reply = REFUSE_REPLY
            ids.append(audit(state, "deny", "patient_records", state["subject_id"]))
        elif route == "handoff_doctor":
            reply = HANDOFF_REPLY
            ids.append(audit(state, "handoff", "patient_records", state["subject_id"]))
        elif route == "not_in_record":
            reply = NOT_FOUND_REPLY
        elif route == "unavailable":
            reply = UNAVAILABLE_REPLY
        else:
            reply = reidentify(state["draft"]["answer"], TokenMap(dict(state.get("tokens", {}))))
        # every document whose text was shown to the model is a read of that record
        for doc_id in sorted({c.doc_id for c in state.get("chunks", [])} if "draft" in state else set()):
            ids.append(audit(state, "read", "document", doc_id))
        return {"reply": reply, "citations": state.get("citations", []) if route == "answer" else [], "audit_ids": ids}

    g = StateGraph(W2State)
    for name, fn in [("access", access), ("guard", guard), ("retrieve", retrieve), ("answer", answer),
                     ("verify", verify), ("finish", finish)]:
        g.add_node(name, fn)
    g.add_edge(START, "access")
    g.add_conditional_edges("access", lambda s: "finish" if s.get("route") else "guard")
    g.add_conditional_edges("guard", lambda s: "finish" if s.get("route") else "retrieve")
    g.add_conditional_edges("retrieve", lambda s: "finish" if s.get("route") else "answer")
    g.add_conditional_edges("answer", lambda s: "finish" if s.get("route") else "verify")
    g.add_edge("verify", "finish")
    g.add_edge("finish", END)
    return g.compile()


def ask(graph, *, caller_id: str, subject_id: str, question: str, caller_role: str = "patient",
        trace_id: str | None = None) -> dict:
    started = time.monotonic()
    out = graph.invoke({"caller_id": caller_id, "caller_role": caller_role, "subject_id": subject_id,
                        "question": question, "trace_id": trace_id or uuid.uuid4().hex})
    return {"route": out["route"], "reply": out["reply"], "citations": out.get("citations", []),
            "reason": out.get("reason"), "audit_ids": out.get("audit_ids", []),
            "retrieved": [c.source_ref for c in out.get("chunks", [])],
            "latency_s": round(time.monotonic() - started, 3)}
