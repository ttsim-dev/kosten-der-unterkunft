"""Gemeinde population and area from the Destatis Gemeindeverzeichnis.

`gemeinde_lookup.arrow` carries no population and no area, so the committed
`data/gemeinde_population.arrow` supplies both, built from the GV-ISys
Jahresausgabe. This module holds the pure logic behind it — parsing the
published workbook rows, reconciling the published Gebietsstand with the
boundary file, and deriving the Gemeindegrößenklassen — while
`scripts/fetch_gemeinde_population.py` does the downloading and writing.

The reconciliation exists because no single published Gebietsstand reproduces
the 10,980 AGS of `gemeinden.geo.json` exactly: the boundary export mixes
vintages. `build_gemeinde_population` therefore takes a base edition, a
backfill edition, and an explicit list of `MergerReversal` records, and
raises unless the result covers the boundary AGS exactly.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

# Satzart marking a Gemeinde row in the GV-ISys Onlineprodukt sheet.
GV_GEMEINDE_RECORD_TYPE = "60"

# Schema of `data/gemeinde_population.arrow`.
POPULATION_COLUMNS: tuple[str, ...] = (
    "ags",
    "gemeinde_name",
    "population",
    "area_sqkm",
    "population_per_sqkm",
    "population_reference_date",
)


@dataclass(frozen=True)
class MergerReversal:
    """Restore an AGS that the base edition no longer knows.

    The boundary file still draws the pre-merger municipality, so its
    population and area are taken from the backfill edition. Where the
    successor is known, its figures are reduced by the restored ones, so no
    inhabitant is counted twice.
    """

    absorbed_ags: tuple[str, ...]
    """AGS present in the boundary file but absent from the base edition."""
    successor_ags: str | None
    """AGS that absorbed them, or `None` if no successor could be identified."""
    note: str
    """Why the reversal is applied, for the report and the data dictionary."""


def build_gemeinde_population(
    base: pd.DataFrame,
    backfill: pd.DataFrame,
    boundary_ags: pd.Series,
    reversals: tuple[MergerReversal, ...],
    base_reference_date: date,
    backfill_reference_date: date,
) -> pd.DataFrame:
    """Reconcile two GV editions into one table covering the boundary AGS exactly.

    Args:
        base: Parsed Gemeinde rows of the chosen Jahresausgabe.
        backfill: Parsed Gemeinde rows of the preceding Jahresausgabe.
        boundary_ags: The eight-digit AGS of every geometry, as strings.
        reversals: Explicit corrections for AGS the base edition dropped.
        base_reference_date: Gebietsstand and reporting date of `base`.
        backfill_reference_date: Same, for `backfill`.

    Returns:
        A frame with `POPULATION_COLUMNS`, one row per boundary AGS.

    Raises:
        ValueError: If the result does not cover `boundary_ags` exactly.

    """
    target = set(boundary_ags)
    frame = base.set_index("ags")
    frame["population_reference_date"] = base_reference_date
    restored = backfill.set_index("ags")
    restored["population_reference_date"] = backfill_reference_date

    for reversal in reversals:
        rows = restored.loc[list(reversal.absorbed_ags)]
        if reversal.successor_ags is not None:
            frame = _subtract(frame, reversal.successor_ags, rows)
        frame = pd.concat([frame, rows[frame.columns]])

    frame = frame.loc[frame.index.isin(target)].sort_index()
    _fail_if_coverage_incomplete(frame.index, target)
    return _finalise(frame)


def parse_gv_rows(rows: list[tuple[Any, ...]]) -> pd.DataFrame:
    """Extract Gemeinde population and area from GV-ISys Onlineprodukt rows.

    The sheet is a hierarchy of record types; only Satzart `60` is a Gemeinde.
    Its eight-digit AGS is Land, Regierungsbezirk, Kreis, and Gemeinde — the
    four-digit Verbandsgemeinde column sits between the last two and is not
    part of the AGS.

    Args:
        rows: Raw cell tuples of the Onlineprodukt sheet, header rows included.

    Returns:
        A frame with `ags`, `gemeinde_name`, `population`, and `area_sqkm`.

    """
    records = [
        {
            "ags": f"{row[2]}{row[3]}{row[4]}{row[6]}",
            "gemeinde_name": str(row[7]),
            "area_sqkm": float(row[8]),
            "population": int(row[9]),
        }
        for row in rows
        if row[0] == GV_GEMEINDE_RECORD_TYPE and row[2] and row[9] is not None
    ]
    frame = pd.DataFrame.from_records(records, columns=list(POPULATION_COLUMNS[:4]))
    _fail_if_ags_not_unique(frame["ags"])
    return frame


def load_gemeinde_population(path: Path) -> pd.DataFrame:
    """Load the committed population table written by the fetch script."""
    return pd.read_feather(path)


def _finalise(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.reset_index()
    result["population_per_sqkm"] = result["population"] / result["area_sqkm"]
    result["population_reference_date"] = result["population_reference_date"].map(
        lambda value: value.isoformat(),
    )
    return result.loc[:, list(POPULATION_COLUMNS)].reset_index(drop=True)


def _subtract(
    frame: pd.DataFrame,
    successor_ags: str,
    absorbed: pd.DataFrame,
) -> pd.DataFrame:
    """Remove the absorbed municipalities' figures from their successor."""
    if successor_ags not in frame.index:
        msg = f"successor AGS {successor_ags} is absent from the base edition"
        raise ValueError(msg)
    adjusted = frame.copy()
    for column in ("population", "area_sqkm"):
        remainder = adjusted.loc[successor_ags, column] - absorbed[column].sum()
        if remainder < 0:
            msg = (
                f"reversing the merger into {successor_ags} leaves a negative "
                f"{column} ({remainder}); the absorbed AGS list is wrong"
            )
            raise ValueError(msg)
        adjusted.loc[successor_ags, column] = remainder
    adjusted["population"] = adjusted["population"].round().astype(int)
    return adjusted


def _size_class_labels(breaks: tuple[int, ...]) -> list[str]:
    edges = (0, *breaks[:-1])
    labels = [
        f"{lower:,}-{upper - 1:,}" for lower, upper in zip(edges, breaks, strict=True)
    ]
    labels[0] = f"under {breaks[0]:,}"
    labels.append(f"{breaks[-1]:,} and over")
    return labels


def _fail_if_ags_not_unique(ags: pd.Series) -> None:
    duplicated = ags[ags.duplicated()].tolist()
    if duplicated:
        msg = f"AGS codes must be unique; found duplicates: {duplicated[:5]}"
        raise ValueError(msg)


def _fail_if_coverage_incomplete(ags: pd.Index, target: set[str]) -> None:
    missing = sorted(target - set(ags))
    extra = sorted(set(ags) - target)
    if missing or extra:
        msg = (
            f"population table must cover the {len(target)} boundary AGS exactly; "
            f"{len(missing)} missing {missing[:10]}, {len(extra)} extra {extra[:10]}"
        )
        raise ValueError(msg)
