# Data contract: `appointment`

```yaml
table: appointment
owner: Scheduling service owner
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: Real time; tied to a patient, so reads are audited
sensitivity: operational
checks:
  - idempotency_key unique (0 duplicates)
  - at most one live booking per slot (unique index)
  - status in (booked, cancelled, attended, no_show)
consumers:
  - W1 booking
  - Front-desk override
  - No-show metrics
source: W1 graph; front desk
```

**Treatment (operational):** May leave; still audited when tied to a patient.
