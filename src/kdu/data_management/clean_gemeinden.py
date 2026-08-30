"""The Gemeinde table: name, Kreis, Bundesland, and population.

Every other table in this project is keyed on the eight-digit AGS and carries
no geography of its own, so this is the one place a Gemeinde acquires its name,
its Kreis, its Bundesland and its population. Region names are never join keys:
they repeat across Germany.

Three key formats meet here:

- `gemeinde_lookup.arrow` keys on the twelve-digit Regionalschlüssel, whose
  eight-digit AGS is its first five and last three characters. The four
  Verbandsgemeinde digits in between are not part of the AGS.
- `kdu_gemeinden.csv` keys on the eight-digit AGS.
- `gemeinde_population.arrow` already keys on the eight-digit AGS.
"""

from pathlib import Path

import pandas as pd

from kdu.joins import merge_without_duplicating

# Digits in the Gemeinde AGS.
AGS_LENGTH = 8

# Digits in the Kreis AGS.
KREIS_AGS_LENGTH = 5

# Columns of `gemeinden.parquet`, in order.
GEMEINDE_COLUMNS: tuple[str, ...] = (
    "ags",
    "municipality_name",
    "district_ags",
    "district_name",
    "state_code",
    "state_name",
    "population",
)

# Insel Lütje Hörn, a gemeindefreies Gebiet on the North Sea.
#
# The boundary export names it, but its polygon vanishes when the boundaries
# are snapped to the roughly one-kilometre grid, so it is absent from
# `gemeinden.geo.json` and from `kdu_gemeinden.csv`. It is dropped by name
# here rather than by a silent inner join, so that any other lookup-only AGS
# raises instead of disappearing.
LOOKUP_ONLY_AGS: tuple[str, ...] = ("03457501",)


def build_gemeinden(
    lookup: pd.DataFrame,
    population: pd.DataFrame,
) -> pd.DataFrame:
    """Join names, Kreis, Bundesland and population into one Gemeinde table.

    Args:
        lookup: The twelve-digit-keyed lookup with the Gemeinde, Kreis and
            Bundesland names.
        population: The committed population table, keyed on the eight-digit
            AGS.

    Returns:
        One row per Gemeinde with `GEMEINDE_COLUMNS`, sorted by AGS.

    """
    geography = _normalise_lookup(lookup)
    inhabitants = pd.DataFrame(
        {
            "ags": population["ags"].astype("string"),
            "population": population["population"],
        },
    )
    frame = merge_without_duplicating(geography, inhabitants, on=["ags"])
    return (
        frame.loc[:, list(GEMEINDE_COLUMNS)].sort_values("ags").reset_index(drop=True)
    )


def to_gemeinde_ags(regionalschluessel: pd.Series) -> pd.Series:
    """Reduce a twelve-digit Regionalschlüssel to the eight-digit Gemeinde AGS.

    Args:
        regionalschluessel: The twelve-digit codes.

    Returns:
        The eight-digit AGS: the first five digits and the last three.

    """
    codes = regionalschluessel.astype("string")
    return codes.str[:KREIS_AGS_LENGTH] + codes.str[-3:]


def load_lookup(path: Path) -> pd.DataFrame:
    """Read the committed AGS lookup table."""
    return pd.read_feather(path)


def load_population(path: Path) -> pd.DataFrame:
    """Read the committed Gemeinde population table."""
    return pd.read_feather(path)


def _normalise_lookup(lookup: pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame(index=lookup.index)
    frame["ags"] = to_gemeinde_ags(lookup["ags"])
    frame["municipality_name"] = lookup["gemeinde"].astype("string")
    frame["district_ags"] = frame["ags"].str[:KREIS_AGS_LENGTH]
    frame["district_name"] = lookup["kreis"].astype("string")
    frame["state_code"] = frame["ags"].str[:2]
    frame["state_name"] = lookup["bundesland"].astype("string")
    trimmed = frame.loc[~frame["ags"].isin(LOOKUP_ONLY_AGS)].reset_index(drop=True)
    _fail_if_ags_not_unique(trimmed["ags"])
    return trimmed


def _fail_if_ags_not_unique(ags: pd.Series) -> None:
    duplicated = ags[ags.duplicated()].tolist()
    if duplicated:
        msg = f"AGS codes must be unique; found duplicates: {duplicated[:5]}"
        raise ValueError(msg)
