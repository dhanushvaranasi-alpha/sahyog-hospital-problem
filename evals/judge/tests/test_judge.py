"""Judge plumbing without model calls: hand-off stripping and the calibration set."""
import json
from pathlib import Path

import pytest

from evals.judge.judge import strip_handoff

HERE = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("answer,expected", [
    ("Your INR was 1.4. Your doctor will go through what this means for you.", "Your INR was 1.4."),
    ("The score was 79, and your doctor will go through what it means for you.", "The score was 79."),
    ("It notes lung nodules, which your doctor will go through with you.", "It notes lung nodules."),
    ("Your doctor can explain this. The INR was 1.4.", "The INR was 1.4."),
    ("The report says your doctor changed the dose to 5 mg.", "The report says your doctor changed the dose to 5 mg."),
])
def test_strip_handoff_keeps_facts(answer, expected):
    assert strip_handoff(answer) == expected


def test_calibration_set_shape():
    items = [json.loads(l) for l in (HERE / "calibration_items.jsonl").read_text().splitlines() if l.strip()]
    grades = json.loads((HERE / "human_grades.json").read_text())["grades"]
    assert len(items) == 20 and len({i["id"] for i in items}) == 20
    assert sum(i["perturbation"] is not None for i in items) == 6
    assert set(grades) <= {i["id"] for i in items}
    assert set(grades.values()) <= {"Faithful", "Not faithful"}
