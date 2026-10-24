# Data contract: `specialty`

```yaml
table: specialty
owner: Clinical safety
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: On change, by pull request
sensitivity: operational
checks:
  - name unique
  - red_flag_rules is valid JSON
consumers:
  - W1 specialty match
  - Doctor directory
source: data/reference/specialties.csv
```

**Treatment (operational):** May leave; still audited when tied to a patient.
