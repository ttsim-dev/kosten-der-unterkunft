"""Define the measures available in the Gemeinde choropleth."""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class MeasureSpec:
    """Describe one selectable map measure."""

    key: str
    """Short stable identifier."""
    column: str
    """Column name in the completed KdU CSV."""
    label: str
    """German text used in the dropdown and figure title."""
    unit: str
    """Display unit: `€`, `%`, `m²`, `€/m²`, or empty for Mietstufe."""
    hover_format: str
    """Plotly d3 format applied to the displayed value."""
    is_ordinal: bool
    """Whether the measure is the ordinal Mietstufe scale."""
    is_diverging: bool = False
    """Mark a measure whose natural midpoint is zero."""


MEASURES: tuple[MeasureSpec, ...] = (
    MeasureSpec(
        key="wogg_mietstufe",
        column="wogg_mietstufe",
        label="Mietstufe (KdU-Dokument, sonst § 12 WoGG)",
        unit="",
        hover_format="d",
        is_ordinal=True,
    ),
    MeasureSpec(
        key="max_bruttokaltmiete_eur_1p",
        column="max_bruttokaltmiete_eur_1p",
        label="Bruttokaltmiete, 1 Person",
        unit="€",
        hover_format=",.0f",
        is_ordinal=False,
    ),
    MeasureSpec(
        key="max_bruttokaltmiete_eur_2p",
        column="max_bruttokaltmiete_eur_2p",
        label="Bruttokaltmiete, 2 Personen",
        unit="€",
        hover_format=",.0f",
        is_ordinal=False,
    ),
    MeasureSpec(
        key="max_bruttokaltmiete_eur_4p",
        column="max_bruttokaltmiete_eur_4p",
        label="Bruttokaltmiete, 4 Personen",
        unit="€",
        hover_format=",.0f",
        is_ordinal=False,
    ),
    MeasureSpec(
        key="max_bruttokaltmiete_eur_sqm",
        column="max_bruttokaltmiete_eur_sqm",
        label="Bruttokaltmiete je m²",
        unit="€/m²",
        hover_format=",.2f",
        is_ordinal=False,
    ),
    MeasureSpec(
        key="max_nettokaltmiete_eur_1p",
        column="max_nettokaltmiete_eur_1p",
        label="Nettokaltmiete, 1 Person",
        unit="€",
        hover_format=",.0f",
        is_ordinal=False,
    ),
    MeasureSpec(
        key="max_nettokaltmiete_eur_4p",
        column="max_nettokaltmiete_eur_4p",
        label="Nettokaltmiete, 4 Personen",
        unit="€",
        hover_format=",.0f",
        is_ordinal=False,
    ),
    MeasureSpec(
        key="max_wohnflaeche_sqm_1p",
        column="max_wohnflaeche_sqm_1p",
        label="Angemessene Wohnfläche, 1 Person",
        unit="m²",
        hover_format=",.0f",
        is_ordinal=False,
    ),
    MeasureSpec(
        key="max_wohnflaeche_sqm_4p",
        column="max_wohnflaeche_sqm_4p",
        label="Angemessene Wohnfläche, 4 Personen",
        unit="m²",
        hover_format=",.0f",
        is_ordinal=False,
    ),
    MeasureSpec(
        key="wogg_hoechstbetrag_eur_1p",
        column="wogg_hoechstbetrag_eur_1p",
        label="Wohngeld-Höchstbetrag, 1 Person",
        unit="€",
        hover_format=",.0f",
        is_ordinal=False,
    ),
    MeasureSpec(
        key="wogg_hoechstbetrag_eur_2p",
        column="wogg_hoechstbetrag_eur_2p",
        label="Wohngeld-Höchstbetrag, 2 Personen",
        unit="€",
        hover_format=",.0f",
        is_ordinal=False,
    ),
    MeasureSpec(
        key="wogg_hoechstbetrag_eur_4p",
        column="wogg_hoechstbetrag_eur_4p",
        label="Wohngeld-Höchstbetrag, 4 Personen",
        unit="€",
        hover_format=",.0f",
        is_ordinal=False,
    ),
    MeasureSpec(
        key="kdu_vs_wogg_pct_1p",
        column="kdu_vs_wogg_pct_1p",
        label="KdU ggü. Wohngeld-Höchstbetrag, 1 Person",
        unit="%",
        hover_format="+,.1f",
        is_ordinal=False,
        is_diverging=True,
    ),
    MeasureSpec(
        key="kdu_vs_wogg_pct_2p",
        column="kdu_vs_wogg_pct_2p",
        label="KdU ggü. Wohngeld-Höchstbetrag, 2 Personen",
        unit="%",
        hover_format="+,.1f",
        is_ordinal=False,
        is_diverging=True,
    ),
    MeasureSpec(
        key="kdu_vs_wogg_pct_4p",
        column="kdu_vs_wogg_pct_4p",
        label="KdU ggü. Wohngeld-Höchstbetrag, 4 Personen",
        unit="%",
        hover_format="+,.1f",
        is_ordinal=False,
        is_diverging=True,
    ),
)


def compute_colour_range(
    values: pd.Series,
    spec: MeasureSpec,
) -> tuple[float, float]:
    """Compute the display range for a measure.

    Args:
        values: Measure values, including any missing observations.
        spec: Display specification for the measure.

    Returns:
        The fixed ordinal range, a symmetric diverging range, or the 2nd and 98th
        percentiles.

    Raises:
        ValueError: If `values` contains no non-missing observations.
    """
    observed = values.dropna()
    if observed.empty:
        msg = f"Measure '{spec.key}' has no non-missing values."
        raise ValueError(msg)
    if spec.is_ordinal:
        return (1, 7)
    lower, upper = observed.quantile([0.02, 0.98])
    if spec.is_diverging:
        limit = max(abs(float(lower)), abs(float(upper)))
        return (-limit, limit)
    return (float(lower), float(upper))
