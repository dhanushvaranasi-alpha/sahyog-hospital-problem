# Data contract: `audit_event`

```yaml
table: audit_event
owner: Compliance officer
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: Written in the same transaction as the read; kept one year
sensitivity: operational
checks:
  - append-only (update and delete raise)
  - every record read has one event (tested)
consumers:
  - Compliance queries (who saw this record)
  - Incident review
source: Every service
```

**Treatment (operational):** May leave; still audited when tied to a patient.
