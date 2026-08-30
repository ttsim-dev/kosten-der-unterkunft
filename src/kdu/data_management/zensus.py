"""Parse the Zensus 2022 Gemeinde rents into the long table §15 works from.

**These are Bestandsmieten.** The Zensus recorded the Nettokaltmiete of every
occupied rented dwelling on 2022-05-15, so the figures describe tenancies as they
stood, most of them agreed years earlier. They are not Angebotsmieten and they do
not describe what a household searching today would have to pay.

Two further limits are part of the measure and are carried in the column names:

- The mean says nothing about how many simple dwellings a household could actually
  find. No quantity derived here may be read as, or named after, a share of
  dwellings within reach.
- Differences in dwelling quality and building age stay unobserved, so a comparison
  of two regions' means compares two differently composed stocks.

The source is the freely downloadable Regionaltabelle "Gebäude und Wohnungen",
whose `CSV-Wohnungen` sheet reports every Gemeinde with its mean Nettokaltmiete per
square metre and the dwelling counts by rent class and by floor-area class. A mean
Nettokaltmiete *within* a floor-area class is published only in the Zensusdatenbank,
whose API rejects unauthenticated requests; see `docs/external_data_status.md`.
"""

from collections.abc import Mapping
from types import MappingProxyType

import pandas as pd

ZENSUS_REFERENCE_DATE = "2022-05-15"
"""Stichtag of the Zensus 2022."""

RENT_CLASS_MEASURES: Mapping[str, str] = MappingProxyType(
    {
        "MIETE_EURM2_2__01": "dwellings_bestandsmiete_eur_per_sqm_under_4",
        "MIETE_EURM2_2__02": "dwellings_bestandsmiete_eur_per_sqm_4_to_6",
        "MIETE_EURM2_2__03": "dwellings_bestandsmiete_eur_per_sqm_6_to_8",
        "MIETE_EURM2_2__04": "dwellings_bestandsmiete_eur_per_sqm_8_to_10",
        "MIETE_EURM2_2__05": "dwellings_bestandsmiete_eur_per_sqm_10_to_12",
        "MIETE_EURM2_2__06": "dwellings_bestandsmiete_eur_per_sqm_12_to_14",
        "MIETE_EURM2_2__07": "dwellings_bestandsmiete_eur_per_sqm_14_to_16",
        "MIETE_EURM2_2__08": "dwellings_bestandsmiete_eur_per_sqm_16_to_18",
        "MIETE_EURM2_2__09": "dwellings_bestandsmiete_eur_per_sqm_18_to_20",
        "MIETE_EURM2_2__10": "dwellings_bestandsmiete_eur_per_sqm_20_and_more",
    }
)
"""Dwelling counts by Nettokaltmiete class, in euro per square metre."""

FLOOR_AREA_CLASS_MEASURES: Mapping[str, str] = MappingProxyType(
    {
        "WOHNFLAECHE_20S__01": "dwellings_floor_area_sqm_under_40",
        "WOHNFLAECHE_20S__02": "dwellings_floor_area_sqm_40_to_59",
        "WOHNFLAECHE_20S__03": "dwellings_floor_area_sqm_60_to_79",
        "WOHNFLAECHE_20S__04": "dwellings_floor_area_sqm_80_to_99",
        "WOHNFLAECHE_20S__05": "dwellings_floor_area_sqm_100_to_119",
        "WOHNFLAECHE_20S__06": "dwellings_floor_area_sqm_120_to_139",
        "WOHNFLAECHE_20S__07": "dwellings_floor_area_sqm_140_to_159",
        "WOHNFLAECHE_20S__08": "dwellings_floor_area_sqm_160_to_179",
        "WOHNFLAECHE_20S__09": "dwellings_floor_area_sqm_180_to_199",
        "WOHNFLAECHE_20S__10": "dwellings_floor_area_sqm_200_and_more",
    }
)
"""Dwelling counts by floor-area class, the classes §15.2's `s(h)` selects from."""

SCALAR_MEASURES: Mapping[str, str] = MappingProxyType(
    {
        "QMMIETE": "bestandsmiete_nettokalt_eur_per_sqm_mean",
        "FLAECHE": "mean_floor_area_sqm_per_dwelling",
        "GEBAEUDEART_SYS_1": "dwellings_total",
        "NUTZUNG__02": "dwellings_rented_for_residential_use",
    }
)

REGION_LEVELS: Mapping[str, str] = MappingProxyType(
    {
        "Bund": "bund",
        "Land": "land",
        "Regierungsbezirk": "regierungsbezirk",
        "Gemeindeverband": "gemeindeverband",
        "Gemeinde": "gemeinde",
    }
)
"""Region levels whose German label maps one to one. Kreise are matched by prefix."""

REGIONALSCHLUESSEL_WIDTHS: Mapping[str, int] = MappingProxyType(
    {
        "bund": 2,
        "land": 2,
        "regierungsbezirk": 3,
        "kreis": 5,
        "gemeindeverband": 9,
        "gemeinde": 12,
    }
)
"""Digits the Regionalschlüssel has at each level.

The workbook stores the key as a number, so Schleswig-Holstein's `01` arrives as
`1` and Flensburg's `010010000000` as `10010000000`. The level decides how many
leading zeros to restore.
"""

_KREIS_LABEL_PREFIX = "Stadtkreis"

_FORBIDDEN_MEASURE_SUBSTRINGS: tuple[str, ...] = (
    "availab",
    "verfuegbar",
    "verfügbar",
    "supply",
    "angebotsmiete",
)


def build_zensus_rents(raw: pd.DataFrame) -> pd.DataFrame:
    """Turn the Regionaltabelle's `CSV-Wohnungen` block into the long rent table.

    Args:
        raw: The sheet as read, with its original German column codes.

    Returns:
        A long frame with `ags`, `region_name`, `region_level`, `reference_date`,
        `measure` and `value`, one row per region and measure.

    """
    measures = {**SCALAR_MEASURES, **RENT_CLASS_MEASURES, **FLOOR_AREA_CLASS_MEASURES}
    frame = pd.DataFrame(index=raw.index)
    frame["region_level"] = _classify_region_level(raw["Regionalebene"])
    frame["ags"] = normalise_regionalschluessel(raw["_RS"], frame["region_level"])
    frame["region_name"] = raw["Name"].astype("string").str.strip()
    frame["reference_date"] = ZENSUS_REFERENCE_DATE
    for source_column, measure in measures.items():
        frame[measure] = _to_numeric(raw[source_column])
    long_frame = frame.melt(
        id_vars=["ags", "region_name", "region_level", "reference_date"],
        value_vars=list(measures.values()),
        var_name="measure",
        value_name="value",
    )
    fail_if_measure_names_claim_availability(long_frame["measure"])
    return long_frame.sort_values(["ags", "measure"]).reset_index(drop=True)


def normalise_regionalschluessel(codes: pd.Series, levels: pd.Series) -> pd.Series:
    """Restore the leading zeros the workbook's numeric storage drops.

    Args:
        codes: Regionalschlüssel as read from the workbook.
        levels: Region level of each row, as `_classify_region_level` returns it.

    Returns:
        The zero-padded Regionalschlüssel, unchanged where the level is unknown.

    """
    text = codes.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    widths = levels.map(REGIONALSCHLUESSEL_WIDTHS)
    padded = pd.Series(
        [
            code if pd.isna(width) or pd.isna(code) else code.zfill(int(width))
            for code, width in zip(text, widths, strict=True)
        ],
        index=codes.index,
        dtype="string",
    )
    return padded


def select_gemeinden(long_frame: pd.DataFrame) -> pd.DataFrame:
    """Keep the Gemeinde rows, the level §15 compares the local caps against.

    The Regionaltabelle stacks Bund, Länder, Kreise and Gemeinden in one block and
    repeats a kreisfreie Stadt at both the Kreis and the Gemeinde level. Only the
    Gemeinde rows carry a twelve-digit Regionalschlüssel that joins to
    `data/gemeinde_lookup.arrow`.

    Args:
        long_frame: Output of `build_zensus_rents`.

    Returns:
        The Gemeinde rows only.

    """
    return long_frame.query("region_level == 'gemeinde'").reset_index(drop=True)


def add_ags_eight_digit(long_frame: pd.DataFrame) -> pd.DataFrame:
    """Add the eight-digit AGS the map table is keyed by.

    The Zensus writes a twelve-digit Regionalschlüssel whose last four digits are
    the Verbandsschlüssel; the map's AGS drops them.

    Args:
        long_frame: Gemeinde-level frame carrying a twelve-digit `ags`.

    Returns:
        The frame with an `ags_gemeinde` column of eight digits.

    """
    return long_frame.assign(
        ags_gemeinde=long_frame["ags"].str[:5] + long_frame["ags"].str[-3:]
    )


def fail_if_measure_names_claim_availability(measures: pd.Series) -> None:
    """Raise when a measure name promises more than a Bestandsmiete can say.

    §15's limitations are explicit that the mean says nothing about whether simple
    dwellings can be found, and D13 forbids "housing availability" derived from a
    mean rent. A name carrying that claim would smuggle the conclusion into the
    data.

    Args:
        measures: Measure names to check.

    Raises:
        ValueError: If any name claims availability or an Angebotsmiete.

    """
    lowered = measures.astype(str).str.lower()
    for token in _FORBIDDEN_MEASURE_SUBSTRINGS:
        offending = sorted(set(measures[lowered.str.contains(token, regex=False)]))
        if offending:
            msg = (
                f"Zensus measure names must not claim availability, but {offending} "
                f"contain {token!r}. The Zensus reports Bestandsmieten; a mean over "
                f"existing tenancies carries no statement about what a searching "
                f"household can find."
            )
            raise ValueError(msg)


def _classify_region_level(labels: pd.Series) -> pd.Series:
    stripped = labels.astype("string").str.strip()
    mapped = stripped.map(REGION_LEVELS)
    is_kreis = stripped.str.startswith(_KREIS_LABEL_PREFIX, na=False)
    return mapped.mask(is_kreis, "kreis").fillna("other")


def _to_numeric(column: pd.Series) -> pd.Series:
    """Convert a Zensus cell to a float, honouring the source's own value marks.

    `–` marks "nothing to report" and becomes zero; `.` and `x` mark a value that
    is not published and become missing.
    """
    text = column.astype("string").str.strip()
    zeroed = text.replace({"–": "0", "-": "0", "—": "0"})
    blanked = zeroed.replace({".": pd.NA, "x": pd.NA, "X": pd.NA, "": pd.NA})
    return pd.to_numeric(blanked.str.replace(",", ".", regex=False), errors="coerce")
