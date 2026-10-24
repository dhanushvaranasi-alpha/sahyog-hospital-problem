# Data contract: `medicine`

```yaml
table: medicine
owner: Pharmacy
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: Monthly
sensitivity: operational
checks:
  - price_inr > 0 (100%)
  - pack size parsed (>= 99%)
  - medicine_id unique
consumers:
  - W3 stock flags (Pro)
  - Substitute listing (Pro)
source: A-Z Medicine Dataset of India (CC BY-SA 4.0)
```

**Treatment (operational):** May leave; still audited when tied to a patient.
