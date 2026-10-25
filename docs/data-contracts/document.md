# Data contract: `document`

```yaml
table: document
owner: Records service owner
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: Status visible within 60 s of upload (E3-S1)
sensitivity: direct
checks:
  - patient_id not null (100%)
  - phi_status in (pending, tagged, failed)
  - uri resolves to a stored file (100%)
  - (patient_id, content_hash) unique: re-upload is a no-op
  - header patient matches patient_id, else refused
  - a patient's upload is erasable on request with every derived copy (CR-001, tested)
consumers:
  - W2 ingest
  - W2 ask (citations)
source: Patient uploads; 100 synthetic reports
```

**Treatment (direct):** Never leaves the boundary. Tokenise before any external call; Presidio plus Indian phone and ABHA recognisers.
