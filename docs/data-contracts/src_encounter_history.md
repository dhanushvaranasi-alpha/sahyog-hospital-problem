# Data contract: `src_encounter_history`

```yaml
table: src_encounter_history
owner: Data
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: Static source snapshot
sensitivity: quasi
checks:
  - discharged_on >= admitted_on (0 violations)
  - no billing or insurance columns
consumers:
  - Patient generator
source: Healthcare Dataset (CC0)
```

**Treatment (quasi):** Leaves only generalised: age band instead of birth date, district instead of pincode.
