# ADR 0002 — Report ingest on a Redis + RQ worker

```yaml
title: Uploads are queued in Redis and ingested by an RQ worker; the API returns a job id and a status endpoint
context: The client never wants an HTTP connection held open for a PDF (p36) and needs a visible upload status within 60 seconds (E3-S1). Ingest runs parsing, PHI tagging, chunking and local embedding, which is slow on CPU.
options:
  - name: FastAPI background task + job table
    cost: No extra service; but ingest shares the API process, so a slow embed slows requests, and jobs are lost on restart
  - name: Redis + RQ worker
    cost: One more container (Redis) and a worker process; ingest scales apart from the API and survives API restarts
  - name: Celery with a broker
    cost: Most features (retries, scheduling), but the heaviest setup for a single queue at this scale
decision: Redis + RQ. The same Redis serves the 30-second slot-availability cache (p31). Revisit when ingest needs parallel fan-out across documents (Architect tier, Send API).
consequences: docker-compose runs Redis; a worker process joins the stack. Job status is read from RQ and mirrored to an ingest_job row for audit. Matches the pack's container view (p23), removing one deviation.
versions_pinned: redis == 8.1.0 (client); rq == 2.12.0; image redis:8.10.2-alpine
checked_on: 2026-10-24
status: accepted
```
