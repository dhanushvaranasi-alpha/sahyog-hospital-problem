"""Slot calendar: plain arithmetic from clinic hours (pack p20: no LLM touches a calendar).

16 thirty-minute slots a day (09:00-17:00 IST), Monday to Saturday, for a 14-day window
(trimmed from the pack's 60 days for a laptop build; see docs/data-sizing.md).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

IST = ZoneInfo("Asia/Kolkata")
START = date(2026, 10, 26)      # a Monday
DAYS = 14
SLOTS_PER_DAY = 16
FIRST = time(9, 0)
LENGTH = timedelta(minutes=30)


def working_days() -> list[date]:
    return [START + timedelta(days=i) for i in range(DAYS) if (START + timedelta(days=i)).weekday() < 6]


def build(doctors: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for day in working_days():
        base = datetime.combine(day, FIRST, tzinfo=IST)
        for d in doctors.itertuples():
            for k in range(SLOTS_PER_DAY):
                rows.append((d.doctor_id, d.clinic_id, base + k * LENGTH))
    return pd.DataFrame(rows, columns=["doctor_id", "clinic_id", "starts_at"]).assign(capacity=1, synthetic=True)
