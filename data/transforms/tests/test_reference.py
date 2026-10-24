"""Reference data checks: sites, specialties and the condition-to-specialty crosswalk."""
import pandas as pd

from data.transforms.common import REFERENCE
from data.transforms.transcriptions import SPECIALTY_MAP

SITES = pd.read_csv(REFERENCE / "sites.csv")
SPECIALTIES = set(pd.read_csv(REFERENCE / "specialties.csv")["name"])
XWALK = pd.read_csv(REFERENCE / "condition_specialty_crosswalk.csv", dtype=str, keep_default_na=False)


def test_network_matches_the_pack():
    # p3: 6 hospitals and 22 clinics, split evenly across Pune and Hyderabad.
    counts = SITES.groupby(["city", "kind"]).size().to_dict()
    assert counts == {("Hyderabad", "clinic"): 11, ("Hyderabad", "hospital"): 3,
                      ("Pune", "clinic"): 11, ("Pune", "hospital"): 3}
    clinics = SITES[SITES["kind"] == "clinic"]
    assert clinics["parent_hospital_id"].isin(SITES.loc[SITES["kind"] == "hospital", "site_id"]).all()


def test_every_mapped_specialty_exists():
    assert {v for v in SPECIALTY_MAP.values() if v} <= SPECIALTIES
    used = set(XWALK["specialty"]) | {s for s in XWALK["alternative_specialty"] if s}
    assert used <= SPECIALTIES


def test_crosswalk_rows_are_complete():
    assert XWALK["condition"].is_unique
    assert XWALK["emergency_condition"].isin(["true", "false"]).all()


def test_every_crosswalk_row_carries_a_reviewer_mark():
    # Pack p19: the crosswalk is generated, then hand-checked; every row carries a reviewer mark.
    missing = XWALK.loc[(XWALK["reviewed_by"] == "") | (XWALK["reviewed_on"] == ""), "condition"].tolist()
    assert not missing, f"{len(missing)} crosswalk rows not reviewed yet: {missing[:5]}..."
