"""The pack's checks (p19) on the real downloaded data. Skipped until data/raw/ exists."""
import json

import pandas as pd
import pytest

from data.transforms import run
from data.transforms.common import PROCESSED, RAW, REFERENCE

pytestmark = pytest.mark.skipif(not (RAW / "MANIFEST.sha256").exists(), reason="run data/fetch_datasets.sh first")


@pytest.fixture(scope="module")
def report():
    return run.main()


def test_every_tally_balances(report):
    for source, r in report.items():
        assert r["balanced"], source


def test_no_shows_clean(report):
    df = pd.read_parquet(PROCESSED / "appointment_history.parquet")
    assert (df["age"] >= 0).all() and (df["age"] <= 110).all()
    assert (df["lead_days"] >= 0).all()


def test_encounter_date_order_violations_are_zero(report):
    df = pd.read_parquet(PROCESSED / "encounter_history.parquet")
    assert (pd.to_datetime(df["discharged_on"]) >= pd.to_datetime(df["admitted_on"])).all()


def test_pack_size_regex_coverage(report):
    df = pd.read_parquet(PROCESSED / "medicine.parquet")
    sample = df.sample(200, random_state=7)
    assert sample["pack_qty"].notna().mean() >= 0.95  # the pack's 95% bar on a 200-row sample
    assert df["pack_qty"].notna().mean() >= 0.99


def test_crosswalk_covers_every_condition(report):
    conditions = set(pd.read_parquet(PROCESSED / "condition_symptom.parquet")["condition"])
    xwalk = set(pd.read_csv(REFERENCE / "condition_specialty_crosswalk.csv")["condition"])
    assert conditions == xwalk


def test_transcriptions_have_no_duplicate_text(report):
    df = pd.read_parquet(PROCESSED / "transcription_note.parquet")
    assert not df["text"].duplicated().any()
