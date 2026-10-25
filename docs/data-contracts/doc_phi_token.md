# Data contract: `doc_phi_token`

```yaml
table: doc_phi_token
owner: Records service owner
schema_version: 1
change_rule: Additive changes (new nullable column) by pull request; anything else needs an ADR and a consumer check.
freshness: Written with its document in one transaction; deleted with it
sensitivity: direct
checks:
  - (doc_id, token) unique
  - every token in a doc_chunk.text resolves (tested)
  - never sent to an external service (only tokens leave)
consumers:
  - W2 ask re-identification for the entitled reader
source: W2 ingest graph, tag_phi step
```

**Treatment (direct):** Never leaves the boundary. Tokenise before any external call; Presidio plus Indian phone and ABHA recognisers.
