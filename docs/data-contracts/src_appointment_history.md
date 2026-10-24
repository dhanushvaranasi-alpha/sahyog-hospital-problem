# Data contract: `src_appointment_history`

```yaml
table: src_appointment_history
owner: Data
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: Static source snapshot
sensitivity: quasi
checks:
  - age between 0 and 110
  - lead_days >= 0
  - rows in - dropped = rows out
consumers:
  - No-show risk signal
source: Medical Appointment No Shows (CC BY-NC-SA 4.0)
```

**Treatment (quasi):** Leaves only generalised: age band instead of birth date, district instead of pincode.
