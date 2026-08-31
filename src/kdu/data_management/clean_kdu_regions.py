"""Turn the collected KdU Richtlinien into the long table of local caps.

`data/kdu_gemeinden.csv` records what 400 Kreise publish as the maximum
recognisable rent, one row per Gemeinde and a column per household size for
each rent concept. This module reshapes it to one row per Gemeinde and
household size, and settles the one substantive question the wide table leaves
open: which euro amount is the Bruttokaltmiete cap.

{func}`build_kdu_cap` carries the analytical weight: a cap is either published
as a Bruttokaltmiete total or summed from a published Nettokaltmiete and a
published kalte-Betriebskosten cap. Nothing is multiplied out from a
euro-per-square-metre figure, scaled, or imputed from a national average:
several documents state an explicit Ableitungsverbot, and the collectors
already left the cell empty where a derivation is forbidden.
"""

from enum import StrEnum
from pathlib import Path

import pandas as pd

from kdu.config import HOUSEHOLD_SIZES

# Digits in the Gemeinde AGS, leading zeros included.
AGS_LENGTH = 8

# Digits in the Kreis AGS.
KREIS_AGS_LENGTH = 5

# Two euro amounts count as equal when they differ by less than half a cent.
CENT_TOLERANCE = 0.005

# Columns of `kdu_caps.parquet`, in order.
KDU_CAP_COLUMNS: tuple[str, ...] = (
    "ags",
    "household_size",
    "kdu_cap",
    "max_area_sqm",
    "additional_person_amount",
    "calculation_method",
    "haertefall_regelung",
    "valid_from",
    "source_id",
)

# Columns of `kdu_sources.parquet`, in order.
KDU_SOURCE_COLUMNS: tuple[str, ...] = (
    "source_id",
    "source_document",
    "kdu_region",
    "institution",
    "valid_from",
)


class CalculationMethod(StrEnum):
    """How `kdu_cap` was constructed from what the document publishes."""

    PUBLISHED_GROSS_COLD_TOTAL = "published_gross_cold_total"
    """A Bruttokaltmiete total taken over unchanged."""
    SUM_OF_PUBLISHED_COMPONENTS = "sum_of_published_components"
    """A published Nettokaltmiete plus a published kalte-Betriebskosten cap."""
    NOT_CONSTRUCTED = "not_constructed"
    """The document publishes no admissible Bruttokaltmiete cap."""


def build_kdu_caps(wide: pd.DataFrame) -> pd.DataFrame:
    """Build the long cap table from the committed wide table.

    Args:
        wide: `kdu_gemeinden.csv` as read by {func}`read_kdu_gemeinden`.

    Returns:
        One row per Gemeinde and household size 1 to 5, with `KDU_CAP_COLUMNS`.
        A Gemeinde whose document states no cap at a given size keeps the row
        with a missing `kdu_cap`; no Gemeinde is ever dropped.

    """
    long_frame = _reshape_to_long(wide)
    cap = build_kdu_cap(long_frame)
    result = pd.concat([long_frame, cap], axis=1)
    result["source_id"] = source_identifier(result["source_document"])
    return (
        result.loc[:, list(KDU_CAP_COLUMNS)]
        .sort_values(["ags", "household_size"])
        .reset_index(drop=True)
    )


def build_kdu_sources(wide: pd.DataFrame) -> pd.DataFrame:
    """Build the document table the cap table cites.

    One row per cited Richtlinie. The committed table records the document's
    filename, the region label it applies to, and the date the rule took
    effect. The publishing institution is the Kreis, which the AGS identifies.

    Args:
        wide: `kdu_gemeinden.csv` as read by {func}`read_kdu_gemeinden`.

    Returns:
        One row per `source_id`, with `KDU_SOURCE_COLUMNS`.

    """
    cited = wide.dropna(subset=["source_document"])
    sources = pd.DataFrame(index=cited.index)
    sources["source_id"] = source_identifier(cited["source_document"])
    sources["source_document"] = cited["source_document"].astype("string")
    sources["kdu_region"] = cited["kdu_region"].astype("string")
    sources["institution"] = cited["ags_kreis"].astype("string")
    sources["valid_from"] = cited["valid_from"].astype("string")
    return (
        sources.drop_duplicates(subset="source_id")
        .loc[:, list(KDU_SOURCE_COLUMNS)]
        .sort_values("source_id")
        .reset_index(drop=True)
    )


def build_kdu_cap(long_frame: pd.DataFrame) -> pd.DataFrame:
    """Return `kdu_cap` and `calculation_method` for each row.

    A published Bruttokaltmiete total is taken over unchanged. Where none
    exists but the document publishes both a Nettokaltmiete and a kalte
    Betriebskosten cap, the cap is their sum. Deriving a total from a
    euro-per-square-metre figure is deliberately not attempted.

    Args:
        long_frame: Long frame carrying `gross_cold_cap_total`,
            `net_cold_cap_total` and `cold_opex_cap_total`.

    Returns:
        Columns `kdu_cap` and `calculation_method`.

    """
    gross = long_frame["gross_cold_cap_total"]
    components = long_frame["net_cold_cap_total"] + long_frame["cold_opex_cap_total"]

    cap = gross.where(gross.notna(), components)
    method = pd.Series(
        CalculationMethod.NOT_CONSTRUCTED.value,
        index=long_frame.index,
        dtype="string",
    )
    method[components.notna()] = CalculationMethod.SUM_OF_PUBLISHED_COMPONENTS.value
    method[gross.notna()] = CalculationMethod.PUBLISHED_GROSS_COLD_TOTAL.value
    # A published total that is exactly its two published components is the
    # component sum, whichever column of the wide table happens to carry it.
    is_component_sum = (
        cap.notna() & components.notna() & (cap - components).abs().le(CENT_TOLERANCE)
    )
    method[is_component_sum] = CalculationMethod.SUM_OF_PUBLISHED_COMPONENTS.value
    method[cap.isna()] = CalculationMethod.NOT_CONSTRUCTED.value
    return pd.DataFrame({"kdu_cap": cap, "calculation_method": method})


def source_identifier(source_document: pd.Series) -> pd.Series:
    """Derive a stable identifier from a cited document's filename.

    Args:
        source_document: The `source_document` column, one filename per row.

    Returns:
        A lowercase slug per row, missing where no document is cited.

    """
    slug = (
        source_document.astype("string")
        .str.lower()
        .str.replace(r"[^a-z0-9]+", "_", regex=True)
        .str.strip("_")
    )
    return slug.replace("", pd.NA)


def read_kdu_gemeinden(path: Path) -> pd.DataFrame:
    """Read the committed wide table with both AGS columns as strings.

    The AGS is a string throughout: read as a number, every
    Schleswig-Holstein AGS loses its leading zero and joins against nothing.

    Args:
        path: The `kdu_gemeinden.csv` to read.

    Returns:
        The raw frame with `ags_gemeinde` and `ags_kreis` zero-padded.

    """
    frame = pd.read_csv(path, engine="pyarrow")
    frame["ags_gemeinde"] = frame["ags_gemeinde"].astype("string").str.zfill(AGS_LENGTH)
    frame["ags_kreis"] = frame["ags_kreis"].astype("string").str.zfill(KREIS_AGS_LENGTH)
    _fail_if_kreis_prefix_mismatch(frame)
    return frame


def _reshape_to_long(wide: pd.DataFrame) -> pd.DataFrame:
    """Stack the per-household-size columns into one row per size."""
    per_size = [
        pd.DataFrame(
            {
                "ags": wide["ags_gemeinde"],
                "household_size": household_size,
                "max_area_sqm": _as_float(
                    wide[f"max_wohnflaeche_sqm_{household_size}p"],
                ),
                "net_cold_cap_total": _as_float(
                    wide[f"max_nettokaltmiete_eur_{household_size}p"],
                ),
                "cold_opex_cap_total": _as_float(
                    wide[f"max_kalte_bk_eur_{household_size}p"],
                ),
                "gross_cold_cap_total": _as_float(
                    wide[f"max_bruttokaltmiete_eur_{household_size}p"],
                ),
            },
        )
        for household_size in HOUSEHOLD_SIZES
    ]
    long_frame = pd.concat(per_size, ignore_index=True)

    per_gemeinde = pd.DataFrame(
        {
            "ags": wide["ags_gemeinde"],
            "additional_person_amount": _as_float(
                wide["max_bruttokaltmiete_eur_addl"],
            ),
            "haertefall_regelung": wide["haertefall_regelung"].astype("string"),
            "valid_from": wide["valid_from"].astype("string"),
            "source_document": wide["source_document"].astype("string"),
        },
    )
    return long_frame.merge(
        per_gemeinde,
        on="ags",
        how="left",
        validate="many_to_one",
    )


def _as_float(column: pd.Series) -> pd.Series:
    """Read a euro or square-metre column as a nullable float.

    Household sizes whose column happens to hold whole numbers only would
    otherwise be inferred as integers and refuse to stack with the rest.
    """
    return pd.to_numeric(column, errors="coerce").astype("Float64")


def _fail_if_kreis_prefix_mismatch(frame: pd.DataFrame) -> None:
    """Raise if a Gemeinde's AGS does not begin with its Kreis AGS."""
    mismatched = frame.loc[
        frame["ags_gemeinde"].str[:KREIS_AGS_LENGTH] != frame["ags_kreis"],
        "ags_gemeinde",
    ].tolist()
    if mismatched:
        msg = (
            "ags_kreis must be the first five digits of ags_gemeinde; it is not "
            f"for {len(mismatched)} rows: {mismatched[:10]}"
        )
        raise ValueError(msg)
