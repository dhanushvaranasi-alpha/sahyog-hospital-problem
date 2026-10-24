# ADR 0006 — PHI tagging: known identifiers and patterns everywhere, name NER on typed questions only

```yaml
title: Report bodies are tokenised by exact known identifiers plus identifier patterns; spaCy name detection runs only on text people type
context: Pack p21 requires that identifiers never leave the boundary, and names Presidio. Presidio's default PERSON detection uses spaCy NER. Run over the 100 synthetic report bodies (en_core_web_lg, score >= 0.5) it returned 55 distinct PERSON strings, and none was a person: drug names, eponyms and section words such as Mobitz, Xylocaine, Gelfoam, Transthoracic, Willis and one place name. Masking them would delete the facts patients ask about.
options:
  - name: Presidio defaults on everything
    cost: Catches unknown names, but masks clinical terms in reports, so answers lose drug and test names
  - name: Known identifiers + pattern recognisers on reports; NER also on typed questions
    cost: A name in a report body that is not the patient's own and not in the header is not masked; mitigated because reports are filed per patient and the header block (name, phone, ABHA, MRN) is never indexed
  - name: No NER at all
    cost: Simplest, but a patient typing someone else's name would send it to the model
decision: Option 2. Known identifiers come from the patient row and the document header; patterns cover Indian phone, ABHA, MRN, email and patient id (Presidio PatternRecognizers). Questions also get PERSON NER at score >= 0.85, kept only for capitalised spans, which doubles as the check for questions naming another patient. The capitalisation filter came from the W2 questions: English NER tagged ordinary Hindi-English words as names ('aaya hai, kitna insulin lena chahiye'). Revisit when real reports with clinician or relative names in the body enter the set.
consequences: Tokens such as <PERSON_1> are kept in doc_phi_token (inside the boundary) and restored only in the reply to an entitled reader. The 100 synthetic reports produced 0 tokens because identifiers appear only in their headers; the red-team upload and typed questions exercise the token path in tests. NER still misses some names inside Hindi-English sentences ('Sunita ki saari reports'); the consent check and the scope rules, not NER, are what stop those requests.
versions_pinned: presidio-analyzer == 2.2.364; spaCy model en_core_web_lg 3.8.0
checked_on: 2026-10-25
status: accepted
```
