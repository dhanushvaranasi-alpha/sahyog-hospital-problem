# Data contract: `patient`

```yaml
table: patient
owner: Records service owner
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: On change; read at request time
sensitivity: direct
checks:
  - patient_id unique (0 duplicates)
  - phone matches +91 and 10 digits (100%)
  - abha_id matches NN-NNNN-NNNN-NNNN (100%)
  - synthetic = true for every row in this build (100%)
consumers:
  - W1 booking (patient_id from auth)
  - W2 retrieval scope
  - Consent checks
source: Generated from src_encounter_history ages and genders; names from data/synthetic/names.py
```

**Treatment (direct):** Never leaves the boundary. Tokenise before any external call; Presidio plus Indian phone and ABHA recognisers.
