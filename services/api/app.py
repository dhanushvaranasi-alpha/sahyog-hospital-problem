"""FastAPI gateway (architecture §2): auth stub, rate limit, request ids, one router per workflow.

    uvicorn --factory services.api.app:create_production_app --port 8000

Identity always comes from the bearer token, never from the request body: W1 books for the token's
patient, W2 answers for the token's patient (as themselves or as a consented caregiver), and an
upload is filed under the token's patient.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict, Field

from services.api.auth import AuthError, Caller, mint, verify

STATIC = Path(__file__).resolve().parent / "static"
# Demo personas the patient web page may sign in as when DEMO_MODE=true (never in production)
DEMO_PERSONAS = ("P-PRIYA", "P-SUNITA", "P00637")

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


class ConsentGrant(Strict):
    grantee_id: str = Field(min_length=1, max_length=64)
    days: int = Field(default=90, ge=1, le=365)
    purpose: Literal["caregiver"] = "caregiver"


class DemoLogin(Strict):
    patient_id: str = Field(min_length=1, max_length=64)


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

    # ---------- Patient web page (services/api/static) ----------
    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.post("/demo/token", include_in_schema=False)
    def demo_token(body: DemoLogin):
        """Sign-in stand-in for the demo page: off unless DEMO_MODE=true, and only for the synthetic personas."""
        if os.environ.get("DEMO_MODE", "").lower() != "true":
            raise HTTPException(404, "not found")
        if body.patient_id not in DEMO_PERSONAS:
            raise HTTPException(403, "not a demo persona")
        return {"token": mint(body.patient_id, "patient", body.patient_id, ttl_s=3600), "expires_in": 3600}

    @app.get("/v1/me")
    def me(c: Caller = Depends(caller)):
        name = None
        if c.patient_id:
            with deps.records() as store:
                p = store.patient(c.patient_id)
                name = p.name if p else None
        return {"sub": c.sub, "role": c.role, "patient_id": c.patient_id, "name": name}

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

    # ---------- CR-001: DPDP erasure and consent withdrawal (self-set change request) ----------
    @w2.get("/documents")
    def w2_documents(c: Caller = Depends(patient)):
        with deps.records() as store:
            docs = store.documents(c.patient_id)
        return [{"doc_id": d.doc_id, "type": d.type, "report_id": d.source_ref, "report_date": d.report_date,
                 "title": d.title, "erasable": d.type == "upload"} for d in docs]

    @w2.delete("/documents/{doc_id}")
    def w2_erase(doc_id: str, c: Caller = Depends(patient)):
        from services.records.erasure import ErasureRefused, erase_upload
        with deps.records() as store:
            try:
                r = erase_upload(store, patient_id=c.patient_id, doc_id=doc_id, actor_id=c.sub,
                                 upload_dir=deps.upload_dir, embedder=deps.embedder)
            except LookupError:
                raise HTTPException(404, "no such document") from None
            except ErasureRefused as e:
                raise HTTPException(409, str(e)) from None
        return {"erased": r.doc_id, "chunks_removed": r.chunks_removed, "file_removed": r.file_removed}

    @w2.post("/consents", status_code=201)
    def w2_grant(body: ConsentGrant, c: Caller = Depends(patient)):
        from services.records.erasure import grant_consent
        with deps.records() as store:
            try:
                cid = grant_consent(store, subject_id=c.patient_id, grantee_id=body.grantee_id, days=body.days,
                                    actor_id=c.sub, purpose=body.purpose)
            except (LookupError, ValueError) as e:
                raise HTTPException(422, str(e)) from None
        return {"consent_id": cid, "grantee_id": body.grantee_id, "days": body.days}

    @w2.get("/consents")
    def w2_consents(c: Caller = Depends(patient)):
        """Consents this patient has given, and records this patient may read for someone else."""
        with deps.records() as store:
            rows = store.consents_for(c.patient_id)
            names = {}
            for r in rows:
                for pid in (r["patient_id"], r["grantee_id"]):
                    if pid not in names:
                        p = store.patient(pid)
                        names[pid] = p.name if p else pid
        given = [{**r, "grantee_name": names[r["grantee_id"]]} for r in rows if r["patient_id"] == c.patient_id]
        received = [{**r, "patient_name": names[r["patient_id"]]} for r in rows if r["grantee_id"] == c.patient_id]
        return {"given": given, "received": received}

    @w2.delete("/consents/{grantee_id}")
    def w2_withdraw(grantee_id: str, c: Caller = Depends(patient)):
        from services.records.erasure import withdraw_consent
        with deps.records() as store:
            n = withdraw_consent(store, subject_id=c.patient_id, grantee_id=grantee_id, actor_id=c.sub)
        return {"withdrawn": n}

    app.include_router(w1)
    app.include_router(w2)
    return app


def create_production_app() -> FastAPI:
    from dotenv import load_dotenv

    from services.api.deps import ProductionDeps
    load_dotenv()
    return create_app(ProductionDeps())
