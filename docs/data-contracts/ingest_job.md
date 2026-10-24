# Data contract: `ingest_job`

```yaml
table: ingest_job
owner: Platform
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: Updated at every state change
sensitivity: operational
checks:
  - status in (queued, running, done, failed)
  - no job running longer than 10 minutes
consumers:
  - Upload status endpoint
  - Operations dashboard
source: RQ worker
```

**Treatment (operational):** May leave; still audited when tied to a patient.
