-- Sahyog Care Companion schema (pack p18 entity model + Clinic and AuditEvent).
-- Idempotent: runs on first start of an empty volume, and again from data/load.py.
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------- Reference ----------
CREATE TABLE IF NOT EXISTS clinic (
    site_id            text PRIMARY KEY,
    name               text NOT NULL,
    kind               text NOT NULL CHECK (kind IN ('hospital', 'clinic')),
    city               text NOT NULL,
    parent_hospital_id text REFERENCES clinic (site_id)
);

CREATE TABLE IF NOT EXISTS specialty (
    specialty_id   text PRIMARY KEY,
    name           text NOT NULL UNIQUE,
    red_flag_rules jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS condition_specialty (
    condition                text PRIMARY KEY,
    display_name             text NOT NULL,
    specialty_id             text NOT NULL REFERENCES specialty,
    alternative_specialty_id text REFERENCES specialty,
    emergency_condition      boolean NOT NULL,
    drafted_by               text NOT NULL,
    reviewed_by              text,
    reviewed_on              date
);

CREATE TABLE IF NOT EXISTS medicine (
    medicine_id  bigint PRIMARY KEY,
    brand_name   text NOT NULL,
    manufacturer text,
    composition  text NOT NULL,
    pack_label   text,
    pack_qty     numeric,
    pack_unit    text,
    price_inr    numeric NOT NULL CHECK (price_inr > 0),
    discontinued boolean NOT NULL
);
CREATE INDEX IF NOT EXISTS medicine_composition_idx ON medicine (composition);

-- ---------- People and scheduling ----------
CREATE TABLE IF NOT EXISTS patient (
    patient_id text PRIMARY KEY,
    abha_id    text UNIQUE,
    name       text NOT NULL,
    dob        date,
    phone      text,
    language   text NOT NULL DEFAULT 'en',      -- BCP-47 tag; nothing assumes English (p4)
    synthetic  boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS doctor (
    doctor_id         text PRIMARY KEY,
    name              text NOT NULL,
    specialty_id      text NOT NULL REFERENCES specialty,
    clinic_id         text NOT NULL REFERENCES clinic (site_id),
    languages         text[] NOT NULL DEFAULT '{en}',
    years_in_practice int CHECK (years_in_practice >= 0),
    synthetic         boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS slot (
    slot_id   bigserial PRIMARY KEY,
    doctor_id text NOT NULL REFERENCES doctor,
    clinic_id text NOT NULL REFERENCES clinic (site_id),
    starts_at timestamptz NOT NULL,
    capacity  int NOT NULL DEFAULT 1 CHECK (capacity > 0),   -- A09: one per slot today
    synthetic boolean NOT NULL DEFAULT true,
    UNIQUE (doctor_id, starts_at)
);

CREATE TABLE IF NOT EXISTS appointment (
    appt_id         bigserial PRIMARY KEY,
    patient_id      text NOT NULL REFERENCES patient,
    slot_id         bigint NOT NULL REFERENCES slot,
    status          text NOT NULL CHECK (status IN ('booked', 'cancelled', 'attended', 'no_show')),
    idempotency_key text NOT NULL UNIQUE,                     -- E2-S2: retries return the same row
    booked_by       text NOT NULL,                            -- 'assistant' or a front-desk user
    created_at      timestamptz NOT NULL DEFAULT now()
);
-- E2-S4 / A09: a slot holds at most one live booking.
CREATE UNIQUE INDEX IF NOT EXISTS appointment_one_live_booking_per_slot
    ON appointment (slot_id) WHERE status = 'booked';

-- ---------- Consent and records ----------
CREATE TABLE IF NOT EXISTS consent (
    consent_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id text NOT NULL REFERENCES patient,
    grantee_id text NOT NULL,
    scope      text NOT NULL,                                 -- e.g. 'records:read'
    purpose    text NOT NULL,
    expires_at timestamptz NOT NULL,                          -- consent is a row, never a checkbox (p5)
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document (
    doc_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id  text NOT NULL REFERENCES patient,
    type        text NOT NULL,
    uri         text NOT NULL,
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    phi_status  text NOT NULL DEFAULT 'pending' CHECK (phi_status IN ('pending', 'tagged', 'failed')),
    synthetic   boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS doc_chunk (
    chunk_id     bigserial PRIMARY KEY,
    doc_id       uuid NOT NULL REFERENCES document ON DELETE CASCADE,
    patient_id   text NOT NULL REFERENCES patient,           -- denormalised: the scope filter runs in SQL (p31)
    page         int NOT NULL,
    text         text NOT NULL,
    content_hash text NOT NULL,
    embedding    vector(1024)
);
CREATE INDEX IF NOT EXISTS doc_chunk_patient_idx ON doc_chunk (patient_id);
CREATE INDEX IF NOT EXISTS doc_chunk_embedding_idx ON doc_chunk USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS ingest_job (
    job_id     text PRIMARY KEY,                              -- RQ job id
    doc_id     uuid REFERENCES document,
    status     text NOT NULL CHECK (status IN ('queued', 'running', 'done', 'failed')),
    error      text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- ---------- Care delivery (W3 tables, Pro tier) ----------
CREATE TABLE IF NOT EXISTS encounter (
    encounter_id   bigserial PRIMARY KEY,
    appt_id        bigint REFERENCES appointment,
    patient_id     text NOT NULL REFERENCES patient,
    started_at     timestamptz NOT NULL,
    transcript_uri text
);

CREATE TABLE IF NOT EXISTS clinical_note (
    note_id      bigserial PRIMARY KEY,
    encounter_id bigint NOT NULL REFERENCES encounter,
    doctor_id    text NOT NULL REFERENCES doctor,
    soap_json    jsonb NOT NULL,
    signed_at    timestamptz,                                 -- NULL = draft; nothing auto-signs (p5)
    version      int NOT NULL DEFAULT 1,
    content_hash text NOT NULL,
    UNIQUE (encounter_id, version)
);

CREATE TABLE IF NOT EXISTS medicine_stock (
    clinic_id   text NOT NULL REFERENCES clinic (site_id),
    medicine_id bigint NOT NULL REFERENCES medicine,
    qty         int NOT NULL CHECK (qty >= 0),
    as_of       timestamptz NOT NULL,
    PRIMARY KEY (clinic_id, medicine_id)
);

CREATE TABLE IF NOT EXISTS prescription (
    rx_id         bigserial PRIMARY KEY,
    note_id       bigint NOT NULL REFERENCES clinical_note,
    medicine_id   bigint REFERENCES medicine,
    dose          text,
    substitute_ok boolean NOT NULL DEFAULT false
);

-- ---------- Audit: append-only ----------
CREATE TABLE IF NOT EXISTS audit_event (
    event_id      bigserial PRIMARY KEY,
    at            timestamptz NOT NULL DEFAULT now(),
    actor_id      text NOT NULL,
    actor_role    text NOT NULL,
    purpose       text NOT NULL,
    action        text NOT NULL,                              -- 'read', 'write', 'handoff', ...
    resource_type text NOT NULL,
    resource_id   text NOT NULL,
    trace_id      text
);
CREATE INDEX IF NOT EXISTS audit_event_resource_idx ON audit_event (resource_type, resource_id, at);

CREATE OR REPLACE FUNCTION audit_event_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_event is append-only';
END $$;
DROP TRIGGER IF EXISTS audit_event_no_update ON audit_event;
CREATE TRIGGER audit_event_no_update BEFORE UPDATE OR DELETE ON audit_event
    FOR EACH ROW EXECUTE FUNCTION audit_event_immutable();

-- ---------- Source history (cleaned public data, read-only inputs) ----------
CREATE TABLE IF NOT EXISTS src_appointment_history (
    history_id         bigint PRIMARY KEY,
    source_patient_ref text NOT NULL,
    gender             text,
    age                int CHECK (age BETWEEN 0 AND 110),
    scheduled_at       timestamptz NOT NULL,
    appointment_day    timestamptz NOT NULL,
    lead_days          int NOT NULL CHECK (lead_days >= 0),
    sms_received       boolean NOT NULL,
    clinic_id          text NOT NULL REFERENCES clinic (site_id),
    attended           boolean NOT NULL
);

CREATE TABLE IF NOT EXISTS src_encounter_history (
    encounter_ref  bigint PRIMARY KEY,
    patient_name   text NOT NULL,
    age            int,
    gender         text,
    blood_type     text,
    condition      text,
    admission_type text,
    admitted_on    date NOT NULL,
    discharged_on  date NOT NULL CHECK (discharged_on >= admitted_on),
    medication     text,
    test_result    text,
    hospital_id    text NOT NULL REFERENCES clinic (site_id)
);

CREATE TABLE IF NOT EXISTS src_condition_symptom (
    condition text NOT NULL REFERENCES condition_specialty,
    symptom   text NOT NULL,
    severity  int,
    PRIMARY KEY (condition, symptom)
);

CREATE TABLE IF NOT EXISTS src_transcription_note (
    note_id     int PRIMARY KEY,
    title       text,
    label       text NOT NULL,
    specialty   text REFERENCES specialty (name),
    doc_type    text NOT NULL,
    description text,
    text        text NOT NULL,
    keywords    text
);
