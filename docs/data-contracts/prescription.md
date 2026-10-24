# Data contract: `prescription`

```yaml
table: prescription
owner: Clinical safety
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: With its signed note
sensitivity: clinical
checks:
  - note_id refers to a signed note
  - substitute_ok decided by a human
consumers:
  - Pharmacy
source: W3 scribe (Pro)
```

**Treatment (clinical):** Leaves only de-identified; the token map stays on-premise.
