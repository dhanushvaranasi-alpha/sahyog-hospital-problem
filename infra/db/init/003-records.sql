-- W2 My records (PR #7): columns the ingest graph fills, and the local PHI token map.
-- Idempotent: data/load.py applies every init script on each run.

ALTER TABLE document ADD COLUMN IF NOT EXISTS source_ref        text;          -- report id printed on the document
ALTER TABLE document ADD COLUMN IF NOT EXISTS report_date       date;
ALTER TABLE document ADD COLUMN IF NOT EXISTS title             text;          -- de-identified
ALTER TABLE document ADD COLUMN IF NOT EXISTS content_hash      text;          -- sha256 of the file: re-upload is a no-op
ALTER TABLE document ADD COLUMN IF NOT EXISTS injection_removed int NOT NULL DEFAULT 0;
CREATE UNIQUE INDEX IF NOT EXISTS document_patient_hash_uq ON document (patient_id, content_hash);

ALTER TABLE doc_chunk ADD COLUMN IF NOT EXISTS section text;

-- token -> original value for one document. Stays inside the hospital boundary; only tokens leave.
CREATE TABLE IF NOT EXISTS doc_phi_token (
    doc_id      uuid NOT NULL REFERENCES document ON DELETE CASCADE,
    token       text NOT NULL,
    entity_type text NOT NULL,
    value       text NOT NULL,
    PRIMARY KEY (doc_id, token)
);
