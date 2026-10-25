"""PHI tagging with a local token map (pack p21; architecture decision 9).

Three layers, applied in this order:
1. Known identifiers: values we already hold for the people involved (the patient row, and the
   header fields of the report being ingested: name, phone, ABHA, MRN, patient id). Exact matching
   catches these every time, whatever the model or the NER would make of them.
2. Deterministic recognisers for identifier formats (Indian phone, ABHA, MRN, email, patient id),
   registered with Presidio as pattern recognisers.
3. Presidio's spaCy NER for PERSON, used on free text typed by people (questions) only, and only
   for capitalised spans (see _name_spans). On the
   100 synthetic report bodies it returned 55 distinct PERSON strings at score >= 0.5 and none was
   a person: they were drug names, eponyms and section words (Mobitz, Xylocaine, Transthoracic).
   Masking those would delete the facts patients ask about, so report bodies get layers 1 and 2.

Each identifier becomes a typed token such as <PERSON_1>. The token map stays inside the hospital
boundary (table doc_phi_token, or the request state); `reidentify` puts values back into the answer
shown to the entitled user. Only tokenised text is sent to the external model.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache

from services.common.scrub import PATTERNS

TOKEN = re.compile(r"<([A-Z_]+)_(\d+)>")


@dataclass
class TokenMap:
    """token -> (entity type, original value). Same value always maps to the same token."""
    tokens: dict[str, tuple[str, str]] = field(default_factory=dict)

    def token_for(self, entity: str, value: str) -> str:
        for tok, (ent, val) in self.tokens.items():
            if ent == entity and val.lower() == value.lower():
                return tok
        n = 1 + sum(1 for ent, _ in self.tokens.values() if ent == entity)
        tok = f"<{entity}_{n}>"
        self.tokens[tok] = (entity, value)
        return tok

    def merge(self, other: "TokenMap") -> None:
        for tok, (ent, val) in other.tokens.items():
            self.tokens.setdefault(tok, (ent, val))


def _name_variants(name: str) -> list[str]:
    """Full name first, then each part of at least 3 letters (so 'Sunita' alone is caught too)."""
    parts = [p for p in re.split(r"\s+", name.strip()) if len(p) >= 3]
    return [name.strip()] + parts if len(parts) > 1 else [name.strip()]


def known_identifiers(*, name: str | None = None, phone: str | None = None, abha: str | None = None,
                      mrn: str | None = None, patient_id: str | None = None) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if name:
        out += [("PERSON", v) for v in _name_variants(name)]
    for ent, val in (("PHONE", phone), ("ABHA", abha), ("MRN", mrn), ("PATIENT_ID", patient_id)):
        if val:
            out.append((ent, val))
            if ent == "PHONE":
                digits = re.sub(r"\D", "", val)[-10:]
                out.append((ent, digits))                       # same number written without +91 / spaces
    return out


@lru_cache(maxsize=1)
def _analyzer():
    """Presidio analyzer with the Indian identifier recognisers. None if the spaCy model is missing."""
    if os.environ.get("PHI_NER", "on").lower() == "off":
        return None
    try:
        from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
        from presidio_analyzer.nlp_engine import NlpEngineProvider
        model = os.environ.get("PHI_SPACY_MODEL", "en_core_web_lg")
        nlp = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": model}]}).create_engine()
        engine = AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"])
        for label, pat in PATTERNS:
            engine.registry.add_recognizer(PatternRecognizer(
                supported_entity=label, patterns=[Pattern(label.lower(), pat.pattern, 0.9)]))
        return engine
    except Exception:
        return None


def deidentify(text: str, known: list[tuple[str, str]] | None = None, tokens: TokenMap | None = None,
               ner: bool = False) -> tuple[str, TokenMap]:
    """Replace identifiers in `text` with tokens. Returns the tokenised text and the (shared) token map."""
    tokens = tokens or TokenMap()
    # 1. known identifiers, longest first so a full name wins over its parts
    for ent, val in sorted(known or [], key=lambda kv: -len(kv[1])):
        if not val.strip():
            continue
        pat = re.compile(rf"(?<![\w-]){re.escape(val)}(?![\w-])", re.I)
        text = pat.sub(lambda m, e=ent: tokens.token_for(e, m.group(0)), text)
    # 2. identifier formats
    for label, pat in PATTERNS:
        text = pat.sub(lambda m, e=label: tokens.token_for(e, m.group(0)), text)
    # 3. NER names, for free text typed by people
    if ner:
        engine = _analyzer()
        if engine is not None:
            for start, end in sorted(_name_spans(engine, text), reverse=True):
                text = text[:start] + tokens.token_for("PERSON", text[start:end]) + text[end:]
    return text, tokens


def _name_spans(engine, text: str) -> list[tuple[int, int]]:
    """PERSON spans from NER, kept only when every word is capitalised. English NER on Hindi-English
    text tags ordinary lowercase words ('aaya hai', 'kitna insulin lena chahiye') as names; real
    names are written capitalised. A trailing possessive ('s) is left outside the span."""
    out = []
    for h in engine.analyze(text, language="en", entities=["PERSON"]):
        start, end = h.start, h.end
        span = text[start:end]
        if span.endswith("'s"):
            end -= 2
            span = span[:-2]
        words = span.split()
        if h.score < 0.85 or not words or TOKEN.search(span) or not all(w[:1].isupper() for w in words):
            continue
        out.append((start, end))
    return out


def reidentify(text: str, tokens: TokenMap) -> str:
    return TOKEN.sub(lambda m: tokens.tokens.get(m.group(0), ("", m.group(0)))[1], text)


def person_names(text: str) -> list[str]:
    """PERSON spans found by NER in free text (used to spot questions about another patient)."""
    engine = _analyzer()
    if engine is None:
        return []
    return [text[s:e] for s, e in _name_spans(engine, text)]
