"""Minimal egress scrubber for free text sent to an external model (pack p21: identifiers never leave).

Deterministic patterns for the identifier formats this system issues or sees: Indian phone numbers,
ABHA numbers, hospital MRNs, emails and patient ids. The Presidio-based scrubber with its token map
(PR #7, records workflow) replaces this module behind the same function.
"""
from __future__ import annotations

import re

PATTERNS = [
    ("PHONE", re.compile(r"(?:\+91[\s-]?)?\b[6-9]\d{4}[\s-]?\d{5}\b")),
    ("ABHA", re.compile(r"\b\d{2}-\d{4}-\d{4}-\d{4}\b")),
    ("MRN", re.compile(r"\bSH-\d{6,10}\b", re.I)),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")),
    ("PATIENT_ID", re.compile(r"\bP(?:-[A-Z]+|\d{5})\b")),
]


def scrub(text: str) -> str:
    for label, pat in PATTERNS:
        text = pat.sub(f"[{label}]", text)
    return text
