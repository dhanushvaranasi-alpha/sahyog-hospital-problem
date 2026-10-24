# Data contract: `doc_chunk`

```yaml
table: doc_chunk
owner: Records service owner
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: Re-embedded when content_hash changes
sensitivity: direct
checks:
  - patient_id equals its document's patient_id (0 mismatches)
  - embedding has 1,024 dimensions
  - content_hash unique per doc_id and page
consumers:
  - W2 retrieval (patient filter in SQL)
  - Citation check
source: W2 ingest graph from document
```

**Treatment (direct):** Never leaves the boundary. Tokenise before any external call; Presidio plus Indian phone and ABHA recognisers.
