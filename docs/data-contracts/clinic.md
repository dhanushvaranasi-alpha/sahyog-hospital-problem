# Data contract: `clinic`

```yaml
table: clinic
owner: Platform
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: On change
sensitivity: operational
checks:
  - 6 hospitals and 22 clinics
  - every clinic has a parent hospital
consumers:
  - All services
source: data/reference/sites.csv
```

**Treatment (operational):** May leave; still audited when tied to a patient.
