-- API gateway (PR #8): an upload's status is shown only to the patient who uploaded it.
ALTER TABLE ingest_job ADD COLUMN IF NOT EXISTS patient_id text REFERENCES patient;
CREATE INDEX IF NOT EXISTS ingest_job_patient_idx ON ingest_job (patient_id);
