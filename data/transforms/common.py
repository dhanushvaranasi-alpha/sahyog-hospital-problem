"""Shared helpers for the data-estate transforms.

Every transform is a pure function ``clean(df) -> (clean_df, Tally)`` so it can be
unit-tested on small frames; ``run.py`` wires them to the raw files.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "raw"
PROCESSED = REPO / "data" / "processed"
REFERENCE = REPO / "data" / "reference"


@dataclass
class Tally:
    """Rows in, rows out, and why each dropped row was dropped (pack p19)."""

    source: str
    rows_in: int = 0
    rows_out: int = 0
    dropped: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def drop(self, df: pd.DataFrame, mask: pd.Series, reason: str) -> pd.DataFrame:
        n = int(mask.sum())
        if n:
            self.dropped[reason] = self.dropped.get(reason, 0) + n
        return df.loc[~mask]

    def balanced(self) -> bool:
        return self.rows_in - sum(self.dropped.values()) == self.rows_out

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "dropped": self.dropped,
            "notes": self.notes,
        }


def write(df: pd.DataFrame, name: str, tally: Tally | None = None) -> Path:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    out = PROCESSED / f"{name}.parquet"
    df.to_parquet(out, index=False)
    if tally is not None:
        (PROCESSED / f"tally_{tally.source}.json").write_text(json.dumps(tally.as_dict(), indent=2))
    return out
