# Data contract: `clinical_note`

```yaml
table: clinical_note
owner: Clinical safety
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: Persisted only at signature; signed notes are immutable
sensitivity: clinical
checks:
  - signed_at set before a note is readable as final
  - (encounter_id, version) unique
  - no molecule absent from the transcript (eval)
consumers:
  - Patient record
  - Pharmacy (prescription lines)
source: W3 scribe (Pro)
```

**Treatment (clinical):** Leaves only de-identified; the token map stays on-premise.
