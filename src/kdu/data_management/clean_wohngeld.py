"""Build the statutory benchmark each local KdU cap is measured against.

Where a Kreis publishes no schlüssiges Konzept, BSG case law fixes the
Angemessenheitsgrenze at the Anlage 1 Höchstbetrag of § 12 Absatz 1 WoGG plus
a Sicherheitszuschlag of 10 %. That figure — `wohngeld_fallback_cap` — is the
project's single benchmark: it is what a Träger is legally required to apply
when it has nothing of its own, and therefore the standard a local rule
departs from. The bare Höchstbetrag is carried alongside it so the markup
stays visible.

Both are Bruttokaltmieten: § 9 WoGG excludes heating and hot water from the
wohngeldrechtliche Miete, so the benchmark and the local caps are on the same
rent concept.

The only Gemeinde-level input is the Mietenstufe of `wogg_mietstufe`. It is
never derived from Kreis membership or population: it is the classification
of the Anlage zur Wohngeldverordnung, except where a KdU document names a
Mietenstufe of its own, which is then the value kept.
"""

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import pandas as pd

from kdu.config import HOUSEHOLD_SIZES, MIETENSTUFEN, WOHNGELD_FALLBACK_MARKUP

# Digits in the Gemeinde AGS.
AGS_LENGTH = 8

# Columns of `wohngeld_fallback.parquet`, in order.
WOHNGELD_FALLBACK_COLUMNS: tuple[str, ...] = (
    "ags",
    "household_size",
    "mietenstufe",
    "wohngeld_hoechstbetrag",
    "wohngeld_fallback_cap",
)


@dataclass(frozen=True)
class WohngeldParameters:
    """The § 12 WoGG parameters the benchmark is built from."""

    hoechstbetrag: MappingProxyType[tuple[int, int], float]
    """`(mietenstufe, household_size)` → Höchstbetrag in euro per month."""
    legal_sources: MappingProxyType[str, tuple[str, str]]
    """Parameter name → (legal citation, date the Fassung came into force)."""

    def hoechstbetrag_for(self, mietenstufe: int, household_size: int) -> float:
        """Look up one Höchstbetrag by Mietenstufe and household size."""
        return self.hoechstbetrag[mietenstufe, household_size]

    @property
    def vintage_label(self) -> str:
        """A Rechtsstand label naming every citation and its Fassung date."""
        return "; ".join(
            f"{source} in force {in_force}"
            for source, in_force in sorted(set(self.legal_sources.values()))
        )


def build_wohngeld_fallback(
    mietenstufen: pd.DataFrame,
    parameters: WohngeldParameters,
) -> pd.DataFrame:
    """Expand every Gemeinde to the benchmark at each household size.

    Args:
        mietenstufen: One row per Gemeinde, with an eight-digit string `ags`
            and the statutory `mietenstufe` as a nullable integer.
        parameters: The parameters from {func}`load_wohngeld_parameters`.

    Returns:
        `len(mietenstufen) * len(HOUSEHOLD_SIZES)` rows with
        `WOHNGELD_FALLBACK_COLUMNS`. A Gemeinde without a statutory Mietenstufe
        keeps its rows with a missing benchmark; none is ever dropped.

    """
    _fail_if_key_columns_missing(mietenstufen)

    frame = mietenstufen[["ags", "mietenstufe"]].merge(
        pd.DataFrame({"household_size": pd.array(HOUSEHOLD_SIZES, dtype="Int64")}),
        how="cross",
    )
    result = pd.DataFrame(index=frame.index)
    result["ags"] = frame["ags"].astype("string")
    result["household_size"] = frame["household_size"].astype("Int64")
    result["mietenstufe"] = frame["mietenstufe"].astype("Int64")
    result["wohngeld_hoechstbetrag"] = _lookup_hoechstbetrag(
        result["mietenstufe"],
        result["household_size"],
        parameters,
    )
    result["wohngeld_fallback_cap"] = (
        result["wohngeld_hoechstbetrag"] * WOHNGELD_FALLBACK_MARKUP
    )
    return (
        result.loc[:, list(WOHNGELD_FALLBACK_COLUMNS)]
        .sort_values(["ags", "household_size"])
        .reset_index(drop=True)
    )


def load_wohngeld_parameters(path: Path) -> WohngeldParameters:
    """Read the central parameter table.

    Args:
        path: The `wogg_parameters.csv` to read.

    Returns:
        The immutable parameter set. Rows for the Mehrbetrag per additional
        household member are read but not exposed: households of six and more
        are outside the household sizes this project reports.

    Raises:
        ValueError: If any combination of Mietenstufe and household size is
            missing, or if a row lacks its legal citation or Fassung date.

    """
    raw = pd.read_csv(path, dtype_backend="pyarrow")
    _fail_if_citations_incomplete(raw, path)

    base = raw.query("parameter == 'base_cap'")
    hoechstbetrag = {
        (int(mietenstufe), int(household_size)): float(value)
        for mietenstufe, household_size, value in zip(
            base["mietenstufe"],
            base["household_size"],
            base["value_eur"],
            strict=True,
        )
    }
    _fail_if_hoechstbetrag_incomplete(hoechstbetrag, path)

    return WohngeldParameters(
        hoechstbetrag=MappingProxyType(hoechstbetrag),
        legal_sources=MappingProxyType(
            {
                str(parameter): (str(source), str(in_force))
                for parameter, source, in_force in zip(
                    raw["parameter"],
                    raw["legal_source"],
                    raw["in_force_from"],
                    strict=True,
                )
            },
        ),
    )


def read_mietenstufen(path: Path) -> pd.DataFrame:
    """Read each Gemeinde's Mietenstufe from the committed table.

    Args:
        path: The `kdu_gemeinden.csv` to read.

    Returns:
        One row per Gemeinde with `ags` and the nullable integer `mietenstufe`.

    """
    raw = pd.read_csv(
        path,
        usecols=["ags_gemeinde", "wogg_mietstufe"],
        dtype=str,
        engine="pyarrow",
    )
    return pd.DataFrame(
        {
            "ags": raw["ags_gemeinde"].astype("string").str.zfill(AGS_LENGTH),
            "mietenstufe": pd.to_numeric(
                raw["wogg_mietstufe"],
                errors="coerce",
            ).astype("Int64"),
        },
    )


def _lookup_hoechstbetrag(
    mietenstufe: pd.Series,
    household_size: pd.Series,
    parameters: WohngeldParameters,
) -> pd.Series:
    keys = pd.MultiIndex.from_arrays([mietenstufe, household_size])
    table = pd.Series(dict(parameters.hoechstbetrag), dtype="Float64")
    return pd.Series(
        table.reindex(keys).to_numpy(dtype="object"),
        index=mietenstufe.index,
    ).astype("Float64")


def _fail_if_key_columns_missing(mietenstufen: pd.DataFrame) -> None:
    missing = {"ags", "mietenstufe"} - set(mietenstufen.columns)
    if missing:
        msg = f"the Mietenstufe table is missing the column(s) {sorted(missing)}"
        raise ValueError(msg)


def _fail_if_hoechstbetrag_incomplete(
    hoechstbetrag: dict[tuple[int, int], float],
    path: Path,
) -> None:
    expected = {
        (mietenstufe, household_size)
        for mietenstufe in MIETENSTUFEN
        for household_size in HOUSEHOLD_SIZES
    }
    missing = expected - set(hoechstbetrag)
    if missing:
        msg = f"{path} lacks Höchstbetrag rows for {sorted(missing)}"
        raise ValueError(msg)


def _fail_if_citations_incomplete(raw: pd.DataFrame, path: Path) -> None:
    uncited = raw[raw["legal_source"].isna() | raw["in_force_from"].isna()]
    if not uncited.empty:
        msg = (
            f"{path} has {len(uncited)} row(s) without a legal source or Fassung "
            f"date: {sorted(uncited['parameter'].unique())}"
        )
        raise ValueError(msg)
