"""Deterministic checks on the question, run before retrieval or any model call (pack p26).

Scope: a patient may ask about their own records, or a person who has given them valid consent.
Requests about other or all patients, attempts to override instructions, and identity claims
typed into the question are refused here, so they never reach retrieval.

Safety: requests for a diagnosis, a dose, or a decision to start, stop or change a medicine go to
the patient's doctor (pack p16: 'no diagnosis or dose advice'). The answer model can also hand off;
these rules make the common cases certain rather than likely.

Written with the W2 eval set in view; tests/test_rules.py holds paraphrases that are not in the set.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PATIENT_ID = re.compile(r"\bP(?:-[A-Z]{3,}|\d{5})\b")

SCOPE = [
    ("other_patients", re.compile(r"\b(all|every|other|list(ing)?|which|how many)\b.{0,30}\bpatients?\b", re.I)),
    ("other_patients", re.compile(r"\bpatients? (who|with|that|having)\b", re.I)),
    ("bulk_export", re.compile(r"\b(every|all|entire|whole)\b.{0,30}\b(documents?|records?|reports?|files?|database)\b"
                               r".{0,30}\b(database|system|hospital|server)\b", re.I)),
    ("bulk_export", re.compile(r"\b(dump|export)\b.{0,30}\b(database|records|documents)\b", re.I)),
    ("override", re.compile(r"\b(ignore|forget|disregard|override)\b.{0,30}\b(instructions?|rules?|prompt|guidelines?)\b", re.I)),
    ("override", re.compile(r"\b(instructions?|rules?)\b.{0,20}\b(bhool|bhul|chhod|ignore)\w*", re.I)),
    ("override", re.compile(r"\b(system prompt|developer mode|maintenance mode|you are now|jailbreak)\b", re.I)),
    ("override", re.compile(r"\b(what|which)\b.{0,30}\b(report|document|upload|file)\b.{0,30}\b(tell|ask|instruct)s? you\b", re.I)),
    ("override", re.compile(r"\b(instructions?|commands?)\b.{0,15}\b(in|inside|from|hidden in)\b.{0,15}\b(report|document|upload|file|pdf)\b", re.I)),
    ("identity_claim", re.compile(r"\b(my|mera|meri)\b.{0,15}\b(patient|mrn|abha)\b.{0,10}\b(id|number|no\.?)\b.{0,10}\b(is|hai)\b", re.I)),
]

SAFETY = [
    ("dose", re.compile(r"\bdos(e|es|age|ing)\b", re.I)),
    ("dose", re.compile(r"\bhow (much|many)\b.{0,40}\b(take|insulin|tablets?|pills?|units?|mg)\b", re.I)),
    ("dose", re.compile(r"\b(kitna|kitni|kitne)\b.{0,40}\b(lena|leni|lu|loon|khana|khani|insulin|goli|dawai|dawa)\b", re.I)),
    ("medicine_change", re.compile(r"\b(should|can|could|may|do) i\b.{0,15}\b(stop|reduce|increase|start|skip|change|lower|double|cut)\b", re.I)),
    ("medicine_change", re.compile(r"\b(band|kam|zyada)\b.{0,10}\b(kar|karu|karoon|karna)\b", re.I)),
    ("diagnosis", re.compile(r"\b(which|what) (disease|illness|condition|cancer)\b.{0,20}\b(i|me|mujhe)\b", re.I)),
    ("diagnosis", re.compile(r"\b(do i have|have i got|is (it|this|that)|whether (it|this) is)\b.{0,15}\b(cancer|malignant|tumou?r|serious|fatal)\b", re.I)),
    ("diagnosis", re.compile(r"\b(diagnose|diagnosis)\b.{0,15}\b(me|my)\b", re.I)),
]


@dataclass
class RuleHit:
    kind: str        # 'scope' | 'safety'
    rule: str


def check(question: str, subject_id: str, caller_id: str) -> RuleHit | None:
    for pid in PATIENT_ID.findall(question):
        if pid not in (subject_id, caller_id):
            return RuleHit("scope", "identity_claim")
    for name, pat in SCOPE:
        if pat.search(question):
            return RuleHit("scope", name)
    for name, pat in SAFETY:
        if pat.search(question):
            return RuleHit("safety", name)
    return None


# Answers that read as advice rather than as reading the record back.
ADVICE = [
    re.compile(r"\b(you should|you must|I recommend|I suggest|I advise|it is safe to|you can safely)\b.{0,60}"
               r"\b(take|stop|start|increase|reduce|skip|dose|tablets?|insulin|mg|units?)\b", re.I),
    re.compile(r"\byou (have|do not have|don't have)\b.{0,20}\b(cancer|malignan\w*|tumou?r)\b", re.I),
]


def advice_in(answer: str) -> bool:
    return any(p.search(answer) for p in ADVICE)
