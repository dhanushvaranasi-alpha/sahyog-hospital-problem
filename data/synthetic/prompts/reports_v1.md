<!-- version: reports_v1 · used by data/synthetic/reports.py · output validated by schemas.ReportDraft -->
You turn a de-identified public medical transcription into a FICTIONAL patient report from Sahyog Health Network (Pune and Hyderabad, India).

Rules:
- Keep the clinical content, values and findings of the source; do not invent a new diagnosis, medicine or dose that is not in the source.
- Write it as the requested report type, with 2 to 8 short sections (for example "Clinical history", "Technique", "Findings", "Investigations"), in plain English.
- Use Indian units and conventions where natural (for example mg/dL), without changing any value's meaning.
- Do not include any names, phone numbers, dates of birth, addresses or identifiers: the system adds the header separately.
- "impression" summarises the findings in two to four sentences.

Return JSON matching the schema and nothing else.
