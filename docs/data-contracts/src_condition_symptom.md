# Data contract: `src_condition_symptom`

```yaml
table: src_condition_symptom
owner: Clinical safety
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: Static source snapshot
sensitivity: operational
checks:
  - (condition, symptom) unique
  - every condition is in the crosswalk
consumers:
  - W1 specialty match
source: Disease Symptom Prediction (CC BY-SA 4.0)
```

**Treatment (operational):** May leave; still audited when tied to a patient.
