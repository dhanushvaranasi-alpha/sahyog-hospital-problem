# Data contract: `slot`

```yaml
table: slot
owner: Scheduling service owner
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: Availability cached at most 30 s
sensitivity: operational
checks:
  - (doctor_id, starts_at) unique
  - 16 slots per doctor per working day
  - every site has slots every working day
consumers:
  - W1 shortlist tool
  - Booking transaction
source: data/synthetic/slots.py (plain code)
```

**Treatment (operational):** May leave; still audited when tied to a patient.
