"""What the API needs from the outside world, behind one object, so tests swap in memory versions.

ProductionDeps: Postgres pool (directory, records, ingest jobs), Postgres checkpointer for W1
threads (decision 2), Redis (rate limits, ingest queue), the model client and the local embedder.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Protocol

REPO = Path(__file__).resolve().parents[2]


class Deps(Protocol):
    client: object
    embedder: object
    checkpointer: object
    limiter: object
    upload_dir: Path

    def directory(self) -> Iterator: ...
    def records(self) -> Iterator: ...
    def enqueue(self, path: str, patient_id: str) -> str: ...
    def job_status(self, job_id: str) -> dict | None: ...
    def health(self) -> dict: ...


class ProductionDeps:
    def __init__(self):
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
        from redis import Redis

        from services.api.ratelimit import RedisLimiter
        from services.common.embed import default_embedder
        from services.common.llm import ModelClient

        url = os.environ["DATABASE_URL"]
        self.pool = ConnectionPool(url, min_size=1, max_size=10, open=True)
        # LangGraph's saver needs autocommit connections returning dict rows
        self.cp_pool = ConnectionPool(url, min_size=1, max_size=5, open=True,
                                      kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row})
        self.checkpointer = PostgresSaver(self.cp_pool)
        self.checkpointer.setup()
        self.redis = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
        self.limiter = RedisLimiter(self.redis)
        self.client = ModelClient()
        self.embedder = default_embedder()
        self.upload_dir = Path(os.environ.get("UPLOAD_DIR", REPO / "data" / "uploads"))

    @contextmanager
    def directory(self):
        from services.agent.w1.directory import PostgresDirectory
        with self.pool.connection() as conn:
            yield PostgresDirectory(conn)

    @contextmanager
    def records(self):
        from services.records.store import PostgresRecordStore
        with self.pool.connection() as conn:
            yield PostgresRecordStore(conn)

    def enqueue(self, path: str, patient_id: str) -> str:
        from services.records.jobs import enqueue_ingest
        return enqueue_ingest(path, patient_id, doc_type="upload")

    def job_status(self, job_id: str) -> dict | None:
        from services.records.jobs import job_status
        return job_status(job_id)

    def health(self) -> dict:
        out = {}
        try:
            with self.pool.connection() as conn:
                conn.execute("SELECT 1")
            out["postgres"] = "ok"
        except Exception as e:
            out["postgres"] = f"error: {type(e).__name__}"
        try:
            self.redis.ping()
            out["redis"] = "ok"
        except Exception as e:
            out["redis"] = f"error: {type(e).__name__}"
        return out
