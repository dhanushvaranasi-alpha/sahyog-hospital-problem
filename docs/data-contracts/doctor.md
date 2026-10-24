# Data contract: `doctor`

```yaml
table: doctor
owner: Scheduling service owner
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: Daily
sensitivity: operational
checks:
  - at least 10 doctors per specialty
  - no repeated names
  - languages include en (100%)
  - synthetic = true
consumers:
  - W1 shortlist
  - Report headers
source: data/synthetic/doctors.py (code plan + LLM names)
```

**Treatment (operational):** May leave; still audited when tied to a patient.
