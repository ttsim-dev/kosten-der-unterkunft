"""The Zensus 2022 rents of each Gemeinde's rented housing stock.

The Zensus recorded the Nettokaltmiete of every occupied rented dwelling on
2022-05-15, per Gemeinde, as a mean per square metre and as dwelling counts by
rent class. It is the only rent measure available at the resolution the local
caps are set at, which is what makes it the rent measurement this project
compares them against.

Three properties of the measure are part of it and constrain what may be said:

- **These are Bestandsmieten.** They describe tenancies as they stood, most of
  them agreed years earlier. They are not Angebotsmieten, so a household
  searching today faces a tighter distribution than these figures show.
- **The mean says nothing about how many dwellings a household could find.** No
  quantity derived here may be named after, or read as, a share of dwellings
  within reach.
- **Dwelling quality and building age stay unobserved**, so comparing two
  Gemeinden's means compares two differently composed stocks.

The Regionaltabelle stacks Bund, Länder, Kreise and Gemeinden in one block and
repeats a kreisfreie Stadt at both the Kreis and the Gemeinde level. Only the
Gemeinde rows carry a twelve-digit Regionalschlüssel, and only they are kept.
"""

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

import pandas as pd

# Stichtag of the Zensus 2022.
ZENSUS_REFERENCE_DATE = "2022-05-15"

# Digits in the Gemeinde AGS.
AGS_LENGTH = 8

# Dwelling counts by Nettokaltmiete class, in euro per square metre.
RENT_CLASS_MEASURES: Mapping[str, str] = MappingProxyType(
    {
        "MIETE_EURM2_2__01": "dwellings_nettokaltmiete_eur_per_sqm_under_4",
        "MIETE_EURM2_2__02": "dwellings_nettokaltmiete_eur_per_sqm_4_to_6",
        "MIETE_EURM2_2__03": "dwellings_nettokaltmiete_eur_per_sqm_6_to_8",
        "MIETE_EURM2_2__04": "dwellings_nettokaltmiete_eur_per_sqm_8_to_10",
        "MIETE_EURM2_2__05": "dwellings_nettokaltmiete_eur_per_sqm_10_to_12",
        "MIETE_EURM2_2__06": "dwellings_nettokaltmiete_eur_per_sqm_12_to_14",
        "MIETE_EURM2_2__07": "dwellings_nettokaltmiete_eur_per_sqm_14_to_16",
        "MIETE_EURM2_2__08": "dwellings_nettokaltmiete_eur_per_sqm_16_to_18",
        "MIETE_EURM2_2__09": "dwellings_nettokaltmiete_eur_per_sqm_18_to_20",
        "MIETE_EURM2_2__10": "dwellings_nettokaltmiete_eur_per_sqm_20_and_more",
    },
)

SCALAR_MEASURES: Mapping[str, str] = MappingProxyType(
    {
        "QMMIETE": "nettokaltmiete_eur_per_sqm_mean",
        "FLAECHE": "mean_floor_area_sqm_per_dwelling",
        "NUTZUNG__02": "dwellings_rented_for_residential_use",
    },
)

# Region levels whose German label maps one to one. Kreise are matched by prefix.
REGION_LEVELS: Mapping[str, str] = MappingProxyType(
    {
        "Bund": "bund",
        "Land": "land",
        "Regierungsbezirk": "regierungsbezirk",
        "Gemeindeverband": "gemeindeverband",
        "Gemeinde": "gemeinde",
    },
)

# Digits the Regionalschlüssel has at each level.  The workbook stores the key as a
# number, so Schleswig-Holstein's `01` arrives as `1` and Flensburg's `010010000000` as
# `10010000000`. The level decides how many leading zeros to restore.
REGIONALSCHLUESSEL_WIDTHS: Mapping[str, int] = MappingProxyType(
    {
        "bund": 2,
        "land": 2,
        "regierungsbezirk": 3,
        "kreis": 5,
        "gemeindeverband": 9,
        "gemeinde": 12,
    },
)

_KREIS_LABEL_PREFIX = "Stadtkreis"

_FORBIDDEN_MEASURE_SUBSTRINGS: tuple[str, ...] = (
    "availab",
    "verfuegbar",
    "verfügbar",
    "supply",
    "angebotsmiete",
)


def build_zensus_rents(raw: pd.DataFrame) -> pd.DataFrame:
    """Turn the Regionaltabelle into one row per Gemeinde.

    Args:
        raw: The `CSV-Wohnungen` block as read, with its German column codes.

    Returns:
        One row per Gemeinde, keyed on the eight-digit `ags`, with the mean
        Nettokaltmiete per square metre, the dwelling count in each rent class,
        the mean floor area, and the number of dwellings rented for residential
        use.

    """
    measures = {**SCALAR_MEASURES, **RENT_CLASS_MEASURES}
    frame = pd.DataFrame(index=raw.index)
    frame["region_level"] = _classify_region_level(raw["Regionalebene"])
    frame["regionalschluessel"] = _restore_leading_zeros(
        raw["_RS"],
        frame["region_level"],
    )
    for source_column, measure in measures.items():
        frame[measure] = _to_numeric(raw[source_column])

    fail_if_measure_names_claim_availability(pd.Series(list(measures.values())))

    gemeinden = frame.query("region_level == 'gemeinde'").copy()
    gemeinden["ags"] = to_gemeinde_ags(gemeinden["regionalschluessel"])
    gemeinden["reference_date"] = ZENSUS_REFERENCE_DATE
    columns = ["ags", "reference_date", *measures.values()]
    result = gemeinden.loc[:, columns].sort_values("ags").reset_index(drop=True)
    _fail_if_ags_not_unique(result["ags"])
    return result


def to_gemeinde_ags(regionalschluessel: pd.Series) -> pd.Series:
    """Reduce the twelve-digit Regionalschlüssel to the eight-digit AGS.

    The Zensus writes a twelve-digit key whose last four digits are the
    Verbandsschlüssel; the AGS drops them.

    Args:
        regionalschluessel: The twelve-digit codes.

    Returns:
        The eight-digit AGS.

    """
    codes = regionalschluessel.astype("string")
    return codes.str[:5] + codes.str[-3:]


def fail_if_measure_names_claim_availability(measures: pd.Series) -> None:
    """Raise when a measure name promises more than a Bestandsmiete can say.

    The mean says nothing about whether simple dwellings can be found, so a
    name carrying that claim would state the conclusion in the data rather than
    derive it.

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
                f"Zensus measure names must not claim availability, but "
                f"{offending} contain {token!r}. The Zensus reports "
                f"Bestandsmieten; a mean over existing tenancies carries no "
                f"statement about what a searching household can find."
            )
            raise ValueError(msg)


def _restore_leading_zeros(codes: pd.Series, levels: pd.Series) -> pd.Series:
    """Restore the leading zeros the workbook's numeric storage drops."""
    text = codes.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    widths = levels.map(REGIONALSCHLUESSEL_WIDTHS)
    return pd.Series(
        [
            code if pd.isna(width) or pd.isna(code) else code.zfill(int(width))
            for code, width in zip(text, widths, strict=True)
        ],
        index=codes.index,
        dtype="string",
    )


def _classify_region_level(labels: pd.Series) -> pd.Series:
    stripped = labels.astype("string").str.strip()
    mapped = stripped.map(REGION_LEVELS)
    is_kreis = stripped.str.startswith(_KREIS_LABEL_PREFIX, na=False)
    return mapped.mask(is_kreis, "kreis").fillna("other")


def _to_numeric(column: pd.Series) -> pd.Series:
    """Convert a Zensus cell to a float, honouring the source's value marks.

    `–` marks "nothing to report" and becomes zero; `.` and `x` mark a value
    that is not published and become missing.
    """
    text = column.astype("string").str.strip()
    zeroed = text.replace({"–": "0", "-": "0", "—": "0"})
    blanked = zeroed.replace({".": pd.NA, "x": pd.NA, "X": pd.NA, "": pd.NA})
    return pd.to_numeric(blanked.str.replace(",", ".", regex=False), errors="coerce")


def read_zensus_extract(path: Path) -> pd.DataFrame:
    """Read the committed Zensus extract with every column as text."""
    return pd.read_csv(path, dtype=str, engine="pyarrow")


def _fail_if_ags_not_unique(ags: pd.Series) -> None:
    duplicated = ags[ags.duplicated()].tolist()
    if duplicated:
        msg = f"AGS codes must be unique; found duplicates: {duplicated[:5]}"
        raise ValueError(msg)
