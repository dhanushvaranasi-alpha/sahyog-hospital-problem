# Data contract: `condition_specialty`

```yaml
table: condition_specialty
owner: Clinical safety
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: On change, by pull request
sensitivity: operational
checks:
  - every row reviewed (reviewed_by and reviewed_on not null)
  - covers every condition in src_condition_symptom
consumers:
  - W1 specialty match
  - Red-flag rules (emergency_condition)
source: data/reference/condition_specialty_crosswalk.csv; drafted by the AI assistant, reviewed by a human
```

**Treatment (operational):** May leave; still audited when tied to a patient.
