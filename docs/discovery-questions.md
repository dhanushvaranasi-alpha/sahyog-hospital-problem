# D2 — Discovery questions

Ten questions, each tied to the decision its answer unlocks (pack p9). Three are taken from the pack's list (marked **pack**); seven are this team's own.

No client answers are available for this engagement. Each question is therefore closed with a working assumption in `docs/assumptions.md`, with how it will be validated and the fallback if it proves wrong.

| # | Question | Unlocks | Origin | Closed by |
|---|---|---|---|---|
| Q1 | What must happen when a patient reports chest pain at night? | The red-flag rule list and the escalation path | pack | A01 |
| Q2 | Which system is the source of truth for the appointment book? | Whether the assistant writes bookings or only proposes them | pack | A02 |
| Q3 | Who owns an incident when the assistant misleads a patient? | The audit trail, review queue and escalation owner | pack | A03 |
| Q4 | What share of patients type in Hindi, Marathi or a Hindi-English mix today? | Whether a language-detection node is needed, and the language mix of the W1 eval set | own | A04 |
| Q5 | How long should a caregiver's consent last by default, and can the patient revoke it instantly? | The default expiry and revocation path in the consent table | own | A05 |
| Q6 | How long may a slot be held while a patient decides between doctors? | The interrupt timeout in W1 and when a held slot is released | own | A06 |
| Q7 | Which report types make up most uploads: lab, radiology, discharge summaries, prescriptions? | The chunking strategy and the mix of synthetic reports | own | A07 |
| Q8 | Which identifiers appear in uploaded reports beyond name and phone, such as ABHA numbers, hospital MRNs or lab accession ids? | The custom recognisers added to Presidio before egress | own | A08 |
| Q9 | Does any clinic book more than one patient into a slot? | A free-or-taken flag versus a capacity per slot | own | A09 |
| Q10 | Should a patient's questions cover reports from every Sahyog site, or only the site they visit? | The retrieval scope across hospitals and clinics | own | A10 |
