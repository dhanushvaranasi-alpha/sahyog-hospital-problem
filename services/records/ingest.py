"""W2 Ingest graph (architecture §3): parse PDF -> tag PHI -> chunk -> embed -> index.

Runs on the RQ worker (services/records/jobs.py), never inside an HTTP request. Re-ingesting a
file is a no-op (content hash per patient). A document whose header names a different patient
from the one it is being filed under is refused, so an upload cannot plant records in someone
else's file.

    python -m services.records.ingest --synthetic            # index the 100 synthetic reports
    python -m services.records.ingest --synthetic --queue    # same, through Redis + the worker
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import uuid
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from services.common.embed import Embedder
from services.common.phi import TokenMap, deidentify, known_identifiers
from services.records import injection
from services.records.parse import ParsedReport, parse_pdf, split_long
from services.records.store import ChunkRow, DocumentRow, RecordStore

REPO = Path(__file__).resolve().parents[2]
SYNTHETIC_PDFS = REPO / "data" / "synthetic" / "output" / "pdfs"


class IngestRejected(ValueError):
    pass


class IngestState(TypedDict, total=False):
    path: str
    patient_id: str
    doc_type: str
    content_hash: str
    doc_id: str
    existing: bool
    parsed: ParsedReport
    tokens: TokenMap
    title: str
    chunks: list[ChunkRow]
    injection_removed: int


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_ingest_graph(store: RecordStore, embedder: Embedder):
    def check(state: IngestState) -> IngestState:
        h = _sha256(state["path"])
        existing = store.document_by_hash(state["patient_id"], h)
        if existing:
            return {"content_hash": h, "doc_id": existing.doc_id, "existing": True}
        if store.patient(state["patient_id"]) is None:
            raise IngestRejected(f"unknown patient {state['patient_id']}")
        return {"content_hash": h, "doc_id": str(uuid.uuid4()), "existing": False}

    def parse(state: IngestState) -> IngestState:
        parsed = parse_pdf(state["path"])
        if not parsed.sections:
            raise IngestRejected("no text found (scanned PDFs are not supported yet)")
        owner = store.patient(state["patient_id"])
        named_id = parsed.header.get("patient id")
        named = parsed.header.get("patient")
        if named_id and named_id != owner.patient_id:
            raise IngestRejected("document names a different patient id")
        if named and named.strip().lower() != owner.name.strip().lower():
            raise IngestRejected("document names a different patient")
        return {"parsed": parsed}

    def tag_phi(state: IngestState) -> IngestState:
        owner = store.patient(state["patient_id"])
        h = state["parsed"].header
        known = known_identifiers(name=owner.name, phone=owner.phone, abha=owner.abha_id, patient_id=owner.patient_id)
        known += known_identifiers(name=h.get("patient"), phone=h.get("phone"), abha=h.get("abha"), mrn=h.get("mrn"),
                                   patient_id=h.get("patient id"))
        tokens = TokenMap()
        title, tokens = deidentify(state["parsed"].title, known, tokens)
        removed = 0
        for s in state["parsed"].sections:
            if injection.find(s.body):
                s.body, gone = injection.strip(s.body)
                removed += len(gone)
            s.body, tokens = deidentify(s.body, known, tokens)
        return {"tokens": tokens, "title": title, "injection_removed": removed}

    def chunk(state: IngestState) -> IngestState:
        p = state["parsed"]
        ref = p.report_ref or Path(state["path"]).stem
        chunks = []
        for s in p.sections:
            if not s.body.strip():
                continue
            for part in split_long(s.body):
                # Each chunk carries its document context, so retrieval can match 'my echo report'.
                text = f"{state['title']} | {s.heading}\n{part}"
                chunks.append(ChunkRow(doc_id=state["doc_id"], patient_id=state["patient_id"], page=s.page,
                                       section=s.heading, text=text,
                                       content_hash=hashlib.sha256(text.encode()).hexdigest(),
                                       source_ref=ref, report_date=p.report_date, title=state["title"]))
        if not chunks:
            raise IngestRejected("nothing left to index")
        return {"chunks": chunks}

    def embed(state: IngestState) -> IngestState:
        vecs = embedder.embed([c.text for c in state["chunks"]])
        for c, v in zip(state["chunks"], vecs):
            c.embedding = v
        return {"chunks": state["chunks"]}

    def index(state: IngestState) -> IngestState:
        p = state["parsed"]
        doc = DocumentRow(doc_id=state["doc_id"], patient_id=state["patient_id"], type=state.get("doc_type", "report"),
                          uri=str(state["path"]), source_ref=p.report_ref or Path(state["path"]).stem,
                          report_date=p.report_date if p.report_date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.report_date) else None,
                          title=state["title"], content_hash=state["content_hash"],
                          injection_removed=state.get("injection_removed", 0))
        store.add_document(doc, state["chunks"], state["tokens"].tokens)
        return {}

    g = StateGraph(IngestState)
    for name, fn in [("check", check), ("parse", parse), ("tag_phi", tag_phi), ("chunk", chunk), ("embed", embed),
                     ("index", index)]:
        g.add_node(name, fn)
    g.add_edge(START, "check")
    g.add_conditional_edges("check", lambda s: END if s.get("existing") else "parse")
    g.add_edge("parse", "tag_phi")
    g.add_edge("tag_phi", "chunk")
    g.add_edge("chunk", "embed")
    g.add_edge("embed", "index")
    g.add_edge("index", END)
    return g.compile()


def ingest_file(store: RecordStore, embedder: Embedder, path: str | Path, patient_id: str,
                doc_type: str = "report") -> dict:
    out = build_ingest_graph(store, embedder).invoke({"path": str(path), "patient_id": patient_id, "doc_type": doc_type})
    return {"doc_id": out["doc_id"], "existing": out.get("existing", False),
            "chunks": len(out.get("chunks", [])), "injection_removed": out.get("injection_removed", 0)}


def synthetic_files() -> list[tuple[Path, str]]:
    """(path, patient_id) for the generated reports; file names are <report_id>_<patient_id>.pdf."""
    return [(p, p.stem.split("_", 1)[1]) for p in sorted(SYNTHETIC_PDFS.glob("R*_*.pdf"))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true", help="index data/synthetic/output/pdfs")
    ap.add_argument("--queue", action="store_true", help="enqueue on Redis for the worker instead of running here")
    args = ap.parse_args()
    if not args.synthetic:
        ap.error("nothing to do: pass --synthetic")
    from dotenv import load_dotenv
    load_dotenv()
    files = synthetic_files()
    if args.queue:
        from services.records.jobs import enqueue_ingest
        for path, pid in files:
            print(enqueue_ingest(str(path), pid))
        return
    import psycopg

    from services.common.embed import default_embedder
    from services.records.store import PostgresRecordStore
    embedder = default_embedder()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        store = PostgresRecordStore(conn)
        new = 0
        for path, pid in files:
            r = ingest_file(store, embedder, path, pid)
            new += not r["existing"]
        print(f"{len(files)} files, {new} newly indexed; embedding cache hits {embedder.hits}, misses {embedder.misses}")


if __name__ == "__main__":
    main()
