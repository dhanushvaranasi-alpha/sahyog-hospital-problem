<!-- version: doctors_v1 · used by data/synthetic/doctors.py · output validated by schemas.DoctorBatch -->
You write rows for a FICTIONAL doctor directory of Sahyog Health Network, a hospital network in Pune and Hyderabad, India. Every person is invented.

For each request row, return one doctor with:
- name: a realistic, invented Indian full name starting with "Dr. ", plausible for the row's city (Marathi names are common in Pune, Telugu names in Hyderabad, plus names from across India). Never use a famous person's name. Do not repeat a name within the batch.
- gender: "female" or "male"; aim for an even split across the batch.
- languages: ISO codes from en, hi, mr, te. Always include "en". Pune doctors usually add "mr" and/or "hi"; Hyderabad doctors usually add "te" and/or "hi".
- years_in_practice: an integer from 1 to 45 that is plausible for the specialty.
- slot: echo the row number unchanged.

Return JSON matching the schema, with exactly one doctor per request row and nothing else.
