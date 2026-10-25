"""Ingest jobs on Redis + RQ (architecture decision 11): an upload returns a job id at once; the
worker runs the ingest graph and records progress in `ingest_job`, which the status endpoint reads.

    rq worker ingest --url $REDIS_URL        # start a worker (macOS: add --worker-class rq.SimpleWorker)
"""
from __future__ import annotations

import os

import psycopg
from redis import Redis
from rq import Queue

QUEUE = "ingest"


def _queue() -> Queue:
    return Queue(QUEUE, connection=Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0")))


def _set_status(conn, job_id: str, status: str, doc_id: str | None = None, error: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ingest_job (job_id, doc_id, status, error) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (job_id) DO UPDATE SET status = EXCLUDED.status, doc_id = coalesce(EXCLUDED.doc_id, ingest_job.doc_id), "
            "error = EXCLUDED.error, updated_at = now()", (job_id, doc_id, status, error))
    conn.commit()


def enqueue_ingest(path: str, patient_id: str, doc_type: str = "report") -> str:
    job = _queue().enqueue(run_ingest, path, patient_id, doc_type, job_timeout=600)
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        _set_status(conn, job.id, "queued")
    return job.id


def run_ingest(path: str, patient_id: str, doc_type: str = "report") -> dict:
    """Executed by the worker process."""
    from rq import get_current_job

    from services.common.embed import default_embedder
    from services.records.ingest import ingest_file
    from services.records.store import PostgresRecordStore

    job = get_current_job()
    job_id = job.id if job else "local"
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        _set_status(conn, job_id, "running")
        try:
            result = ingest_file(PostgresRecordStore(conn), default_embedder(), path, patient_id, doc_type)
        except Exception as e:
            conn.rollback()
            _set_status(conn, job_id, "failed", error=str(e)[:500])
            raise
        _set_status(conn, job_id, "done", doc_id=result["doc_id"])
        return result


def job_status(job_id: str) -> dict | None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute("SELECT job_id, doc_id, status, error, created_at, updated_at FROM ingest_job WHERE job_id = %s",
                    (job_id,))
        r = cur.fetchone()
    if not r:
        return None
    return {"job_id": r[0], "doc_id": str(r[1]) if r[1] else None, "status": r[2], "error": r[3],
            "created_at": r[4].isoformat(), "updated_at": r[5].isoformat()}
