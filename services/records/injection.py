"""Instructions hidden in uploaded documents (pack p37: 'a report PDF is data, never instructions').

At ingest every sentence of a document is checked against these patterns. A sentence that
addresses the system instead of describing the patient is removed from the indexed text and
counted on the document, so it is never retrieved and never reaches the model. The rest of the
document stays usable: the lab values in a tampered report are still the patient's lab values.

The answer prompt also tells the model that excerpts are data. That is the second line of
defence; this filter is the first because it does not depend on the model obeying.
"""
from __future__ import annotations

import re

DOC_PATTERNS = [
    re.compile(p, re.I) for p in (
        r"\bignore (all |any |the |your )?(previous|prior|above|earlier)\b",
        r"\b(disregard|override|bypass)\b.{0,40}\b(instructions?|rules?|polic(y|ies)|access)\b",
        r"\bsystem (override|prompt|message|instruction)\b",
        r"\byou are now\b",
        r"\b(maintenance|developer|admin|debug) mode\b",
        r"\b(note|message|instructions?) (to|for) (the )?(ai|assistant|model|automated|processing system|system)\b",
        r"\bpre-?approved by\b",
        r"\b(retrieve|fetch|include|append|list|print|reveal|show)\b.{0,60}\b(patient|report|record)s?\b.{0,30}"
        r"\b(P\d{5}|P-[A-Z]+|every|all|other)\b",
        r"\bwhen answering (any|every|this)\b",
    )
]

SENTENCE = re.compile(r"(?<=[.!?])\s+|\n")


def find(text: str) -> list[str]:
    return [s for s in SENTENCE.split(text) if any(p.search(s) for p in DOC_PATTERNS)]


def strip(text: str) -> tuple[str, list[str]]:
    """Return text without suspected instruction sentences, and the sentences removed."""
    kept, removed = [], []
    for s in SENTENCE.split(text):
        (removed if any(p.search(s) for p in DOC_PATTERNS) else kept).append(s)
    return "\n".join(k for k in kept if k.strip()).strip(), removed
