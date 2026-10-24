# Data contract: `encounter`

```yaml
table: encounter
owner: Records service owner
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: Real time
sensitivity: clinical
checks:
  - patient_id not null
  - started_at not in the future
consumers:
  - W3 scribe (Pro)
source: Consultations
```

**Treatment (clinical):** Leaves only de-identified; the token map stays on-premise.
