# Sequence: a patient asks about a report (W2)

```mermaid
sequenceDiagram
    autonumber
    participant P as Patient or caregiver app
    participant API as FastAPI gateway
    participant G as W2 Ask graph
    participant R as Records service (Postgres + pgvector)
    participant E as BGE-M3 (local)
    participant LLM as OpenRouter (Haiku 5.5)
    P->>API: POST /v1/w2/questions {question, subject_patient_id?} + bearer token
    API->>G: invoke(caller from token, subject)
    G->>R: consent check (self, valid, expired, revoked)
    alt no valid consent
        G->>R: audit deny
        G-->>API: refuse
    else allowed
        G->>G: scope and safety rules (code)
        G->>G: de-identify question (tokens)
        G->>E: embed question
        G->>R: search WHERE patient_id = subject, exact ranking
        R-->>G: chunks (already de-identified)
        G->>LLM: answer from excerpts, cite report id and page
        LLM-->>G: draft with citations
        G->>G: verify: citations retrieved, numbers in excerpts, no advice
        G->>G: restore tokens for the entitled reader
        G->>R: audit one read per document shown to the model
        G-->>API: answer, not in record, hand-off or refuse
    end
    API-->>P: reply with citations
```

Uploads take a separate path: `POST /v1/w2/uploads` stores the PDF and returns a job id; the RQ worker parses it, tags PHI, removes instruction sentences, chunks, embeds and indexes it.
