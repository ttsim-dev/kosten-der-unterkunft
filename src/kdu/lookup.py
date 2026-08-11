"""Build the AGS → (Gemeinde, Kreis, Bundesland) lookup table.

The OpenDataSoft source carries, per municipality, its 12-digit AGS
(`gem_code`) plus the names of the Gemeinde, its Kreis, and its
Bundesland. This module flattens those into a tidy table keyed on the
AGS — the stable join key for attaching data to the boundary geometry,
since municipality names are not unique across Germany.
"""

from pathlib import Path
from typing import Any

import pandas as pd


def load_lookup(path: Path) -> pd.DataFrame:
    """Load the AGS lookup table written by {func}`build_gemeinde_lookup`."""
    return pd.read_feather(path)


def build_gemeinde_lookup(raw: dict[str, Any]) -> pd.DataFrame:
    """Flatten the raw GeoJSON properties into an AGS-keyed table.

    Returns a frame with columns `ags`, `gemeinde`, `gem_type`, `kreis`,
    and `bundesland`, sorted by AGS. The Gemeinde name is the short form
    (`gem_name_short`), falling back to the full official name.
    """
    properties = pd.DataFrame([feature["properties"] for feature in raw["features"]])
    frame = pd.DataFrame(index=properties.index)
    frame["ags"] = _unwrap(properties["gem_code"])
    frame["gemeinde"] = _unwrap(properties["gem_name_short"]).fillna(
        _unwrap(properties["gem_name"]),
    )
    frame["gem_type"] = properties["gem_type"]
    frame["kreis"] = _unwrap(properties["krs_name"])
    frame["bundesland"] = _unwrap(properties["lan_name"])
    _fail_if_ags_not_unique(frame)
    return frame.sort_values("ags").reset_index(drop=True)


def _unwrap(column: pd.Series) -> pd.Series:
    """Unwrap the source's single-element lists (e.g. `["14"]`) to scalars."""
    return column.map(
        lambda value: value[0] if isinstance(value, list) and value else value
    )


def _fail_if_ags_not_unique(frame: pd.DataFrame) -> None:
    duplicated = frame["ags"][frame["ags"].duplicated()].tolist()
    if duplicated:
        msg = f"AGS codes must be unique; found duplicates: {duplicated[:5]}"
        raise ValueError(msg)
