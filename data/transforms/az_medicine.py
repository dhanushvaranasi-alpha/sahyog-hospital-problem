"""A-Z Medicine Dataset of India -> formulary keyed by composition.

Known mess (pack p19): price strings with symbols, brand duplicates per composition.
Found in this copy: price is already numeric (4 rows <= 0); 5 exact duplicate rows;
a regex parses every pack-size label, so the LLM fallback in the pack is not needed.
"""
from __future__ import annotations

import re

import pandas as pd

from .common import Tally

PACK_RE = re.compile(r"of\s*(\d+(?:\.\d+)?)\s*([A-Za-z][A-Za-z ]*)", re.I)


def composition_key(c1: object, c2: object) -> str:
    parts = [re.sub(r"\s+", " ", str(c)).strip().lower() for c in (c1, c2) if isinstance(c, str) and c.strip()]
    return " + ".join(sorted(parts))


def parse_pack(label: object) -> tuple[float | None, str | None]:
    if not isinstance(label, str):
        return None, None
    m = PACK_RE.search(label)
    if not m:
        return None, None
    return float(m.group(1)), m.group(2).strip().lower()


def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, Tally]:
    t = Tally("az_medicine", rows_in=len(raw))
    df = raw.copy()
    df = t.drop(df, df.drop(columns=["id"]).duplicated(), "exact duplicate row")
    df = t.drop(df, df["price(₹)"] <= 0, "price not positive")

    parsed = df["pack_size_label"].map(parse_pack)
    out = pd.DataFrame(
        {
            "medicine_id": df["id"].astype("int64"),
            "brand_name": df["name"].str.strip(),
            "manufacturer": df["manufacturer_name"].str.strip(),
            "composition": [composition_key(a, b) for a, b in zip(df["short_composition1"], df["short_composition2"])],
            "pack_label": df["pack_size_label"],
            "pack_qty": [p[0] for p in parsed],
            "pack_unit": [p[1] for p in parsed],
            "price_inr": df["price(₹)"].astype(float),
            "discontinued": df["Is_discontinued"].astype(bool),
        }
    ).reset_index(drop=True)
    t.rows_out = len(out)
    t.notes.append(f"pack size parsed by regex for {out['pack_qty'].notna().mean():.2%} of rows")
    t.notes.append(f"{out['composition'].nunique()} distinct compositions")
    return out, t
