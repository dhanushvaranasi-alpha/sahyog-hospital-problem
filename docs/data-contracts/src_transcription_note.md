# Data contract: `src_transcription_note`

```yaml
table: src_transcription_note
owner: Data
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: Static source snapshot
sensitivity: clinical
checks:
  - text unique after layout repair
  - every label mapped
consumers:
  - Synthetic report generator
  - W3 dictation seeds (Pro)
source: Medical Transcriptions (CC0)
```

**Treatment (clinical):** Leaves only de-identified; the token map stays on-premise.
