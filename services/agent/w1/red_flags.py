"""Red-flag gate: deterministic rules first (pack p14, p25; assumption A01).

Rules are code so recall is auditable: every fired rule id is logged. The model runs second and
may ADD a flag, never remove one. Patterns cover English and common Hindi-English phrasing (A04).
A rule that is too eager costs a phone call; a rule that misses costs a life, so the bias is to fire.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    id: str
    label: str
    pattern: re.Pattern


def _r(rid: str, label: str, *alternatives: str) -> Rule:
    return Rule(rid, label, re.compile("|".join(f"(?:{a})" for a in alternatives), re.I))


RULES: list[Rule] = [
    _r("RF01", "chest pain or pressure",
       r"\bchest\b.{0,40}\b(pain|tight\w*|pressure|crush\w*|heav\w*|squeez\w*)",
       r"\b(pain|tight\w*|pressure|crush\w*|squeez\w*)\b.{0,25}\bchest\b",
       r"\b(seen[ae]|chhati|chaati)\b.{0,25}\b(dard|dabav|bhari)"),
    _r("RF02", "difficulty breathing",
       r"\b(can'?t|cannot|can not|not able to|unable to|difficult\w* to|struggl\w* to)\s+breathe",
       r"\bbreathless(ness)?\b", r"\bshort(ness)?\s+of\s+breath", r"\bdifficulty\s+breathing",
       r"\bsaa?ns\b.{0,20}\b(nahi|phool|lene\s+mein|ruk)"),
    _r("RF03", "arm or jaw pain with cardiac signs",
       r"\b(left\s+arm|arm|jaw)\b.{0,60}\b(sweat\w*|breath\w*|chest)",
       r"\b(sweat\w*|breath\w*|chest)\b.{0,60}\b(left\s+arm|jaw)\b"),
    _r("RF04", "stroke signs",
       r"\bface\b.{0,30}\b(droop\w*|drop\w*|crooked|uneven)", r"\bslurr\w*\s+speech|\bspeech\b.{0,20}\bslurr\w*",
       r"\b(weak\w*|numb\w*)\b.{0,20}\bone\s+side", r"\bone\s+side\b.{0,30}\b(weak\w*|numb\w*|droop\w*)",
       r"\b(haath|hath|pair|pao|pair)\b.{0,40}\bkaam\s+nahi", r"\bbolne\s+mein\s+(dikkat|takleef|pareshani)",
       r"\b(lakwa|paralys\w*)\b"),
    _r("RF05", "heavy bleeding",
       r"\bbleed\w*\b.{0,40}\b(won'?t|wont|doesn'?t|does not|not|can'?t)\s+stop", r"\b(heavy|severe|lot of)\s+bleed\w*",
       r"\bbleeding\s+a\s+lot", r"\b(bahut|zyada)\s+khoon|\bkhoon\b.{0,20}\b(ruk\s+nahi|band\s+nahi)"),
    _r("RF06", "loss of consciousness",
       r"\b(fainted|unconscious|unresponsive|passed\s+out|collapsed)\b", r"\bnot\s+waking\b|\bwon'?t\s+wake",
       r"\bbehosh\b", r"\bvery\s+drowsy\b.{0,30}\bconfus\w*"),
    _r("RF07", "suicidal intent",
       r"\b(end|ending|take|taking)\s+(my|his|her|their)\s+(own\s+)?life", r"\bkill\s+(my|him|her)self",
       r"\bsuicid\w*", r"\b(don'?t|do not)\s+want\s+to\s+(live|be\s+alive)", r"\bwant\s+to\s+die\b",
       r"\bjeena\s+nahi\b|\bmarna\s+chahta|\bmarna\s+chahti"),
    _r("RF08", "severe low blood sugar",
       r"\b(sugar|glucose)\b.{0,40}\b([1-5]\d)\b(?!\s*%)", r"\blow\s+sugar\b.{0,40}\b(confus\w*|shak\w*|faint\w*)"),
    _r("RF09", "seizure", r"\b(seizure|convuls\w*|fits)\b", r"\bdaura\s+pad"),
    _r("RF10", "severe allergic reaction", r"\b(throat|tongue|lips?)\b.{0,20}\bswell\w*", r"\banaphyla\w*"),
]

EMERGENCY_REPLY = ("These symptoms need urgent attention now. Please call 112 or go to the nearest emergency "
                   "department. I have alerted Sahyog's emergency desk; a nurse will call you within two minutes.")
SUICIDE_REPLY = ("I'm really sorry you're feeling this way, and I'm glad you told me. Please talk to someone right now: "
                 "call Tele-MANAS on 14416 or 1800-891-4416 (free, 24x7), or call 112 if you are in immediate danger. "
                 "I have alerted Sahyog's emergency desk so a person can reach you.")


def check(text: str) -> list[str]:
    """Return the ids of every rule that fires on the patient's words."""
    return [r.id for r in RULES if r.pattern.search(text)]


def reply_for(rule_ids: list[str]) -> str:
    return SUICIDE_REPLY if "RF07" in rule_ids else EMERGENCY_REPLY
