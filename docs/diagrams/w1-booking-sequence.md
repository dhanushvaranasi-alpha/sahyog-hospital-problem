# Sequence: a patient books a doctor (W1)

```mermaid
sequenceDiagram
    autonumber
    participant P as Patient app
    participant API as FastAPI gateway
    participant G as W1 graph (LangGraph)
    participant CP as Postgres checkpointer
    participant LLM as OpenRouter (Haiku 5.5)
    participant D as Scheduling (Postgres)
    P->>API: POST /v1/w1/sessions {message} + bearer token
    API->>API: verify token, rate limit, request id
    API->>G: invoke(patient_id from token, message)
    G->>G: red-flag rules (code)
    alt red flag fires
        G->>D: open emergency-desk ticket, audit
        G-->>API: route emergency_desk, reply with 112 guidance
    else no red flag
        G->>LLM: match specialty (de-identified text, strict schema)
        LLM-->>G: specialty, confidence
        G->>D: shortlist 3 doctors, next free slot
        G->>CP: checkpoint, interrupt(choose_slot)
        G-->>API: needs_input with options
        API-->>P: options
        P->>API: POST /sessions/{id}/reply {slot_id, idempotency_key}
        API->>CP: load thread, patient must match token
        API->>G: Command(resume)
        G->>D: book in one transaction (unique live booking per slot), audit, SMS stub
        G-->>API: route booked, appointment id
    end
    API-->>P: reply
```

Low confidence takes a clarify interrupt (at most two) before the shortlist; a model failure or two unclear turns goes to the front desk. A slot taken between offer and pick returns a fresh shortlist.
