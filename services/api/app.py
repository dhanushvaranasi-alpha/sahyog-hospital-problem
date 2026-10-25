"""FastAPI gateway (architecture §2): auth stub, rate limit, request ids, one router per workflow.

    uvicorn --factory services.api.app:create_production_app --port 8000

Identity always comes from the bearer token, never from the request body: W1 books for the token's
patient, W2 answers for the token's patient (as themselves or as a consented caregiver), and an
upload is filed under the token's patient.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict, Field

from services.api.auth import AuthError, Caller, verify

IST = timezone(timedelta(hours=5, minutes=30))
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class W1Start(Strict):
    message: str = Field(min_length=1, max_length=2000)
    age: int | None = Field(default=None, ge=0, le=110)
    language: Literal["en", "hi-en", "hi", "mr"] = "en"


class W1Reply(Strict):
    answer: str | None = Field(default=None, max_length=2000)     # to a clarifying question
    slot_id: str | None = None                                    # to the slot choice
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)


class W2Question(Strict):
    question: str = Field(min_length=1, max_length=2000)
    subject_patient_id: str | None = None                         # whose records; default: the caller


def create_app(deps) -> FastAPI:
    app = FastAPI(title="Sahyog Care Companion", version="0.1.0")

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response

    def caller(authorization: str | None = Header(default=None)) -> Caller:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(401, "missing bearer token")
        try:
            return verify(authorization.split(" ", 1)[1].strip())
        except AuthError as e:
            raise HTTPException(401, str(e)) from None

    def patient(c: Caller = Depends(caller)) -> Caller:
        if c.role != "patient":
            raise HTTPException(403, "patient token required")
        return c

    def limit(group: str):
        def check(c: Caller = Depends(caller)) -> None:
            ok, retry = deps.limiter.hit(c.sub, group)
            if not ok:
                raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": str(retry)})
        return check

    @app.get("/health")
    def health():
        checks = deps.health()
        ok = all(v == "ok" for v in checks.values())
        return JSONResponse({"status": "ok" if ok else "degraded", **checks}, status_code=200 if ok else 503)

    # ---------- W1 Find my doctor ----------
    w1 = APIRouter(prefix="/v1/w1", tags=["W1 Find my doctor"])

    def w1_view(thread_id: str, out: dict) -> dict:
        intr = out.get("__interrupt__")
        if intr:
            return {"thread_id": thread_id, "status": "needs_input", "prompt": intr[0].value}
        return {"thread_id": thread_id, "status": "done", "route": out.get("route"), "reply": out.get("reply"),
                "appointment_id": out.get("appointment_id"), "ticket_id": out.get("ticket_id")}

    @w1.post("/sessions", dependencies=[Depends(limit("w1"))])
    def w1_start(body: W1Start, c: Caller = Depends(patient)):
        from services.agent.w1.graph import build
        thread_id = uuid.uuid4().hex
        with deps.directory() as d:
            g = build(d, deps.client, deps.checkpointer)
            out = g.invoke({"patient_id": c.patient_id, "message": body.message, "age": body.age,
                            "language": body.language, "now": datetime.now(IST).isoformat(timespec="seconds")},
                           {"configurable": {"thread_id": thread_id}})
        return w1_view(thread_id, out)

    @w1.post("/sessions/{thread_id}/reply", dependencies=[Depends(limit("w1"))])
    def w1_reply(thread_id: str, body: W1Reply, c: Caller = Depends(patient)):
        from services.agent.w1.graph import build
        cfg = {"configurable": {"thread_id": thread_id}}
        with deps.directory() as d:
            g = build(d, deps.client, deps.checkpointer)
            snap = g.get_state(cfg)
            if not snap.values or snap.values.get("patient_id") != c.patient_id:
                raise HTTPException(404, "no such session")         # same answer for someone else's thread
            if not snap.interrupts:
                raise HTTPException(409, "session is not waiting for input")
            kind = snap.interrupts[0].value["type"]
            if kind == "clarify":
                if not body.answer:
                    raise HTTPException(422, "answer required")
                resume = body.answer
            else:
                if not (body.slot_id and body.idempotency_key):
                    raise HTTPException(422, "slot_id and idempotency_key required")
                resume = {"slot_id": body.slot_id, "idempotency_key": body.idempotency_key}
            out = g.invoke(Command(resume=resume), cfg)
        return w1_view(thread_id, out)

    # ---------- W2 My records ----------
    w2 = APIRouter(prefix="/v1/w2", tags=["W2 My records"])

    @w2.post("/questions", dependencies=[Depends(limit("w2"))])
    def w2_ask(body: W2Question, request: Request, c: Caller = Depends(patient)):
        from services.agent.w2.graph import ask, build_ask_graph
        with deps.records() as store:
            g = build_ask_graph(store, deps.client, deps.embedder)
            out = ask(g, caller_id=c.patient_id, subject_id=body.subject_patient_id or c.patient_id,
                      question=body.question, trace_id=request.state.request_id)
        return {k: out[k] for k in ("route", "reply", "citations")}

    @w2.post("/uploads", status_code=202, dependencies=[Depends(limit("upload"))])
    async def w2_upload(file: UploadFile = File(...), c: Caller = Depends(patient)):
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "file larger than 10 MB")
        if not data.startswith(b"%PDF-"):
            raise HTTPException(415, "only PDF reports are accepted")
        folder = deps.upload_dir / c.patient_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{hashlib.sha256(data).hexdigest()}.pdf"
        path.write_bytes(data)
        job_id = deps.enqueue(str(path), c.patient_id)
        return {"job_id": job_id, "status_url": f"/v1/w2/uploads/{job_id}"}

    @w2.get("/uploads/{job_id}")
    def w2_upload_status(job_id: str, c: Caller = Depends(patient)):
        st = deps.job_status(job_id)
        if not st or st.get("patient_id") != c.patient_id:
            raise HTTPException(404, "no such upload")
        return {k: st.get(k) for k in ("job_id", "status", "doc_id", "error", "updated_at")}

    app.include_router(w1)
    app.include_router(w2)
    return app


def create_production_app() -> FastAPI:
    from dotenv import load_dotenv

    from services.api.deps import ProductionDeps
    load_dotenv()
    return create_app(ProductionDeps())
