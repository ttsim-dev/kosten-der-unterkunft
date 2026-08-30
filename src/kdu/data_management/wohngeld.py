"""Build the Wohngeld benchmark per Gemeinde and household size (P0.2).

Two benchmarks are produced for every Gemeinde and household size, both expressed on the
Bruttokaltmiete — § 9 WoGG excludes heating and hot water from the wohngeldrechtliche
Miete:

- `wogg_base_cap` — the bare Höchstbetrag of Anlage 1 (zu § 12 Absatz 1) WoGG. This is
  the **primary** benchmark under decision D6: every headline number, map, and Table 2
  entry is computed against it, because the bare Anlage 1 table is what a tax-transfer
  model substitutes for a local KdU cap.
- `wogg_bkc_cap` — base Höchstbetrag plus the Klimakomponente of § 12 Absatz 7 WoGG. The
  mandatory **robustness** variant.

`wogg_heating_relief` (§ 12 Absatz 6 WoGG) is carried alongside as its own column and is
never added to either benchmark; it belongs to a full Wohngeld simulation only.

Every number comes from `data/wogg_parameters.csv`, which carries the legal citation and
the Fassung date of each parameter. No per-Gemeinde value is written into this module:
the only Gemeinde-level input is the statutory Mietenstufe `wogv_mietstufe`. It is never
derived from Kreis membership or population — a Wohngeldstelle applies the Anlage zur
Wohngeldverordnung, regardless of what a KdU document claims, so `wogg_mietstufe` (which
defers to KdU documents) is deliberately ignored.
"""

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import pandas as pd

from kdu.config import DATA, WOGG_SAFETY_MARKUP

# Central parameter table; `docs/config_requests_p02.md` holds the catalog request.
WOGG_PARAMETERS_PATH = DATA / "wogg_parameters.csv"

# The committed wide raw table, never written to.
KDU_GEMEINDEN_PATH = DATA / "kdu_gemeinden.csv"

# Household sizes the benchmark is built for; 6 and above go to the annex (D3).
HOUSEHOLD_SIZES: tuple[int, ...] = (1, 2, 3, 4, 5)

# Mietenstufen I to VII of Anlage 1 WoGG, stored as integers.
RENT_LEVELS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7)


@dataclass(frozen=True)
class WoggParameters:
    """The § 12 WoGG parameters needed to build the benchmark.

    Attributes are keyed by the statutory Mietenstufe (1 to 7) and the number of
    zu berücksichtigende Haushaltsmitglieder.
    """

    base_cap: MappingProxyType[tuple[int, int], float]
    """`(rent_level, household_size)` → Höchstbetrag in €/month."""
    climate_component: MappingProxyType[int, float]
    """`household_size` → Klimakomponente in €/month."""
    heating_relief: MappingProxyType[int, float]
    """`household_size` → Entlastung bei den Heizkosten in €/month."""
    legal_sources: MappingProxyType[str, tuple[str, str]]
    """Parameter name → (legal citation, date the Fassung came into force)."""

    def base_cap_for(self, rent_level: int, household_size: int) -> float:
        """Look up the base Höchstbetrag for one Mietenstufe and household size."""
        return self.base_cap[rent_level, household_size]

    @property
    def vintage_label(self) -> str:
        """A one-line Rechtsstand label naming every citation and its Fassung date."""
        return "; ".join(
            f"{source} in force {in_force}"
            for source, in_force in sorted(set(self.legal_sources.values()))
        )


def load_wogg_parameters(path: Path = WOGG_PARAMETERS_PATH) -> WoggParameters:
    """Read the central parameter table.

    Args:
        path: The `wogg_parameters.csv` to read.

    Returns:
        The immutable parameter set. Rows for the Mehrbetrag per additional household
        member are read but not exposed here — households ≥ 6 are annex material.

    Raises:
        ValueError: If any combination of Mietenstufe and household size is missing,
            or if a row lacks its legal citation or Fassung date.

    """
    raw = pd.read_csv(path, dtype_backend="pyarrow")
    _fail_if_citations_incomplete(raw, path)

    base = raw.query("parameter == 'base_cap'")
    climate = raw.query("parameter == 'climate_component'")
    heating = raw.query("parameter == 'heating_relief'")

    base_cap = {
        (int(rent_level), int(household_size)): float(value)
        for rent_level, household_size, value in zip(
            base["mietenstufe"],
            base["household_size"],
            base["value_eur"],
            strict=True,
        )
    }
    _fail_if_base_cap_incomplete(base_cap, path)

    return WoggParameters(
        base_cap=MappingProxyType(base_cap),
        climate_component=MappingProxyType(_by_household_size(climate)),
        heating_relief=MappingProxyType(_by_household_size(heating)),
        legal_sources=MappingProxyType(
            {
                str(parameter): (str(source), str(in_force))
                for parameter, source, in_force in zip(
                    raw["parameter"],
                    raw["legal_source"],
                    raw["in_force_from"],
                    strict=True,
                )
            }
        ),
    )


def build_wogg_benchmark(
    gemeinden: pd.DataFrame,
    parameters: WoggParameters,
    kdu_caps: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Expand Gemeinden to a long benchmark table keyed `ags` and `household_size`.

    Args:
        gemeinden: One row per Gemeinde, with an eight-digit string `ags` and the
            statutory Mietenstufe `wogv_mietstufe` as a nullable integer. Any further
            column is ignored, so Kreis and population cannot influence the lookup.
        parameters: The parameters from `load_wogg_parameters`.
        kdu_caps: Optional long KdU cap table with `ags`, `household_size`, and
            `kdu_bkc_cap`, as produced by `reshape_kdu_caps_to_long`. When given, the
            proxy-error columns are attached.

    Returns:
        `len(gemeinden) * len(HOUSEHOLD_SIZES)` rows with `wogg_rent_level`,
        `wogg_rent_level_missing`, `wogg_base_cap` (primary), `wogg_climate_component`,
        `wogg_bkc_cap` (robustness), `wogg_heating_relief`, and
        `wogg_parameter_vintage`. Gemeinden without a statutory Mietenstufe are kept
        with null caps and `wogg_rent_level_missing` set, never dropped.

    """
    _fail_if_key_columns_missing(gemeinden)

    frame = gemeinden[["ags", "wogv_mietstufe"]].merge(
        pd.DataFrame({"household_size": pd.array(HOUSEHOLD_SIZES, dtype="Int64")}),
        how="cross",
    )

    result = pd.DataFrame(index=frame.index)
    result["ags"] = frame["ags"].astype("string")
    result["household_size"] = frame["household_size"].astype("Int64")
    result["wogg_rent_level"] = frame["wogv_mietstufe"].astype("Int64")
    result["wogg_rent_level_missing"] = result["wogg_rent_level"].isna()
    result["wogg_base_cap"] = _lookup_base_cap(
        result["wogg_rent_level"], result["household_size"], parameters
    )
    result["wogg_climate_component"] = _lookup_by_household_size(
        result["household_size"], parameters.climate_component
    )
    result["wogg_heating_relief"] = _lookup_by_household_size(
        result["household_size"], parameters.heating_relief
    )
    result["wogg_bkc_cap"] = result["wogg_base_cap"] + result["wogg_climate_component"]
    # The primary benchmark `W`: the Anlage 1 table times the BSG
    # Sicherheitszuschlag, which is the fallback a Kreis without a schlüssiges
    # Konzept must apply and therefore the value a model should substitute (D15).
    result["wogg_primary_cap"] = result["wogg_base_cap"] * WOGG_SAFETY_MARKUP
    result["wogg_parameter_vintage"] = pd.array(
        [parameters.vintage_label] * len(result), dtype="string"
    )

    if kdu_caps is None:
        return result.sort_values(["ags", "household_size"]).reset_index(drop=True)
    return add_kdu_comparison(result, kdu_caps)


def add_kdu_comparison(benchmark: pd.DataFrame, kdu_caps: pd.DataFrame) -> pd.DataFrame:
    """Attach the KdU cap and the proxy error in percent of the Wohngeld ceiling.

    `kdu_vs_wogg_pct_primary` is the headline measure of D6 and is computed against
    `wogg_base_cap` alone; `kdu_vs_wogg_pct_klima` repeats it against `wogg_bkc_cap` for
    the robustness row. Positive means the Jobcenter recognises more than the Wohngeld
    ceiling.

    Args:
        benchmark: The long benchmark from `build_wogg_benchmark`.
        kdu_caps: Long table with `ags`, `household_size`, `kdu_bkc_cap`.

    Returns:
        The benchmark with `kdu_bkc_cap` and both proxy-error columns appended.

    """
    merged = benchmark.merge(
        kdu_caps[["ags", "household_size", "kdu_bkc_cap"]],
        on=["ags", "household_size"],
        how="left",
    )
    merged["kdu_vs_wogg_pct_primary"] = _relative_deviation_pct(
        merged["kdu_bkc_cap"], merged["wogg_base_cap"]
    )
    merged["kdu_vs_wogg_pct_klima"] = _relative_deviation_pct(
        merged["kdu_bkc_cap"], merged["wogg_bkc_cap"]
    )
    return merged.sort_values(["ags", "household_size"]).reset_index(drop=True)


def reshape_kdu_caps_to_long(gemeinden: pd.DataFrame) -> pd.DataFrame:
    """Melt the wide `max_bruttokaltmiete_eur_*p` columns into `kdu_bkc_cap`.

    Args:
        gemeinden: The wide raw table, with an `ags` column.

    Returns:
        Long table keyed `ags` and `household_size`, with `kdu_bkc_cap` in €/month.
        Household sizes whose column is absent from the input yield an all-null
        block, so the shape is the same regardless of which columns the input carries.

    """
    blocks = [
        pd.DataFrame(
            {
                "ags": gemeinden["ags"].astype("string"),
                "household_size": pd.array(
                    [household_size] * len(gemeinden), dtype="Int64"
                ),
                "kdu_bkc_cap": _cap_column(gemeinden, household_size),
            }
        )
        for household_size in HOUSEHOLD_SIZES
    ]
    return (
        pd.concat(blocks, ignore_index=True)
        .sort_values(["ags", "household_size"])
        .reset_index(drop=True)
    )


def read_kdu_gemeinden(path: Path = KDU_GEMEINDEN_PATH) -> pd.DataFrame:
    """Read the committed wide KdU table with the AGS as an eight-digit string.

    Args:
        path: The `kdu_gemeinden.csv` to read.

    Returns:
        The raw frame with an added `ags` column; `ags_gemeinde` is left untouched.

    """
    raw = pd.read_csv(path, dtype={"ags_gemeinde": "string", "ags_kreis": "string"})
    raw["ags"] = raw["ags_gemeinde"].str.zfill(8)
    raw["wogv_mietstufe"] = raw["wogv_mietstufe"].astype("Int64")
    return raw


def _cap_column(gemeinden: pd.DataFrame, household_size: int) -> pd.Series:
    column = f"max_bruttokaltmiete_eur_{household_size}p"
    if column not in gemeinden.columns:
        return pd.Series(pd.array([None] * len(gemeinden), dtype="Float64"))
    return gemeinden[column].astype("Float64").reset_index(drop=True)


def _relative_deviation_pct(value: pd.Series, benchmark: pd.Series) -> pd.Series:
    return (100 * (value.astype("Float64") / benchmark.astype("Float64") - 1)).astype(
        "Float64"
    )


def _by_household_size(frame: pd.DataFrame) -> dict[int, float]:
    return {
        int(household_size): float(value)
        for household_size, value in zip(
            frame["household_size"], frame["value_eur"], strict=True
        )
    }


def _lookup_base_cap(
    rent_level: pd.Series, household_size: pd.Series, parameters: WoggParameters
) -> pd.Series:
    keys = pd.MultiIndex.from_arrays([rent_level, household_size])
    table = pd.Series(dict(parameters.base_cap), dtype="Float64")
    return pd.Series(
        table.reindex(keys).to_numpy(dtype="object"), index=rent_level.index
    ).astype("Float64")


def _lookup_by_household_size(
    household_size: pd.Series, table: MappingProxyType[int, float]
) -> pd.Series:
    return household_size.map(dict(table)).astype("Float64")


def _fail_if_key_columns_missing(gemeinden: pd.DataFrame) -> None:
    missing = {"ags", "wogv_mietstufe"} - set(gemeinden.columns)
    if missing:
        msg = f"gemeinden is missing the required column(s) {sorted(missing)}"
        raise ValueError(msg)


def _fail_if_base_cap_incomplete(
    base_cap: dict[tuple[int, int], float], path: Path
) -> None:
    expected = {
        (rent_level, household_size)
        for rent_level in RENT_LEVELS
        for household_size in HOUSEHOLD_SIZES
    }
    missing = expected - set(base_cap)
    if missing:
        msg = f"{path} lacks base_cap rows for {sorted(missing)}"
        raise ValueError(msg)


def _fail_if_citations_incomplete(raw: pd.DataFrame, path: Path) -> None:
    uncited = raw[raw["legal_source"].isna() | raw["in_force_from"].isna()]
    if not uncited.empty:
        msg = (
            f"{path} has {len(uncited)} row(s) without a legal source or Fassung date: "
            f"{sorted(uncited['parameter'].unique())}"
        )
        raise ValueError(msg)
