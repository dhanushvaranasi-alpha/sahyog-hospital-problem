# Data contract: `consent`

```yaml
table: consent
owner: Compliance officer
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: Checked on every read; no caching
sensitivity: quasi
checks:
  - expires_at not null (100%)
  - no read allowed after expires_at or revoked_at (tested)
  - grantee_id is a known patient or staff id (100%)
consumers:
  - Records service access check
  - Audit queries
source: Created by the patient; persona row seeded
```

**Treatment (quasi):** Leaves only generalised: age band instead of birth date, district instead of pincode.
