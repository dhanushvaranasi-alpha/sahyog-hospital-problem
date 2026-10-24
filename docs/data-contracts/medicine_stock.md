# Data contract: `medicine_stock`

```yaml
table: medicine_stock
owner: Pharmacy
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: Nightly CSV today (stock age shown on every flag); API later (AD-5)
sensitivity: operational
checks:
  - qty >= 0
  - as_of within the last 36 hours, else flagged unknown
consumers:
  - W3 stock check (Pro)
source: Pharmacy stock feed (Pro tier)
```

**Treatment (operational):** May leave; still audited when tied to a patient.
