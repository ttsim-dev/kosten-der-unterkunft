"""The seven measures the Gemeinde choropleth offers.

Each measure names one column of the long map frame keyed `fid` by
`household_size`. Six of the seven vary with household size and are read at
whichever size the map's household-size control currently selects; the
Mietenstufe is a property of the Gemeinde alone.

Every label, unit and caption is German: the map's readers are German policy
practitioners and the quantities are legal terms of art.
"""

from dataclasses import dataclass

import pandas as pd

# Quantile bounds of the displayed colour range, so that the most extreme 2 % of
# Gemeinden at either end cannot compress the scale for the remaining 96 %.
LOWER_DISPLAY_QUANTILE = 0.02
UPPER_DISPLAY_QUANTILE = 0.98


@dataclass(frozen=True)
class MeasureSpec:
    """One selectable measure of the choropleth."""

    key: str
    """Stable identifier, also the filename fragment of the standalone export."""
    column: str
    """Column of the map frame holding the value."""
    label: str
    """German text shown in the measure control."""
    unit: str
    """Display unit: `€/Monat`, `€/m²`, `m²`, `%`, or empty for the Mietenstufe."""
    hover_format: str
    """Plotly d3 number format applied to the displayed value."""
    headline: str
    """First title line, naming what the colour shows."""
    context: str
    """Second title line: legal basis and unit."""
    varies_by_household_size: bool = True
    """Whether the value is read at the selected household size."""
    is_ordinal: bool = False
    """Whether the measure is the ordinal Mietenstufe scale 1 to 7."""
    diverging_midpoint: float | None = None
    """Value the diverging colour scale centres on, or `None` for a sequential scale."""
    reflects_kdu_cap: bool = False
    """Whether a Härtefallzuschlag would raise this value.

    Selects the hatch overlay and the Sicherheitszuschlag footnote. False for the
    Mietenstufe, the Wohngeld-Höchstbeträge and the Wohnflächen, none of which a
    rent surcharge changes.
    """


_SGB_BASIS = "Kosten der Unterkunft nach § 22 SGB II und § 35 SGB XII"

_WOHNGELD_BASIS = (
    "§ 12 Absatz 1 Wohngeldgesetz, Anlage 1, zuzüglich zehn Prozent "
    "Sicherheitszuschlag (Bundessozialgericht B 4 AS 87/12 R)"
)

MEASURES: tuple[MeasureSpec, ...] = (
    MeasureSpec(
        key="mietenstufe",
        column="mietenstufe",
        label="Mietenstufe",
        unit="",
        hover_format="d",
        headline="Mietenstufe der Gemeinde",
        context=(
            "Stufe 1 bis 7 · Grundlage der Wohngeld-Höchstbeträge nach "
            "§ 12 Wohngeldgesetz"
        ),
        varies_by_household_size=False,
        is_ordinal=True,
    ),
    MeasureSpec(
        key="kdu_cap",
        column="kdu_cap",
        label="Örtliche Mietobergrenze",
        unit="€/Monat",
        hover_format=",.0f",
        headline="Höchstens anerkannte Bruttokaltmiete",
        context=(
            f"{_SGB_BASIS} · Euro je Monat, mit kalten Betriebskosten, ohne Heizkosten"
        ),
        reflects_kdu_cap=True,
    ),
    MeasureSpec(
        key="kdu_cap_per_sqm",
        column="kdu_cap_per_sqm",
        label="Örtliche Mietobergrenze je Quadratmeter",
        unit="€/m²",
        hover_format=",.2f",
        headline="Höchstens anerkannte Bruttokaltmiete je Quadratmeter",
        context=(
            f"{_SGB_BASIS} · Euro je Quadratmeter und Monat, bezogen auf die "
            "angemessene Wohnfläche"
        ),
        reflects_kdu_cap=True,
    ),
    MeasureSpec(
        key="wohngeld_fallback_cap",
        column="wohngeld_fallback_cap",
        label="Wohngeld-Obergrenze (Höchstbetrag zuzüglich zehn Prozent)",
        unit="€/Monat",
        hover_format=",.0f",
        headline="Wohngeld-Höchstbetrag zuzüglich Sicherheitszuschlag",
        context=f"{_WOHNGELD_BASIS} · Euro je Monat",
    ),
    MeasureSpec(
        key="cap_ratio",
        column="cap_ratio",
        label="Örtliche Mietobergrenze im Verhältnis zur Wohngeld-Obergrenze",
        unit="",
        hover_format=",.2f",
        headline=("Örtliche Mietobergrenze im Verhältnis zur Wohngeld-Obergrenze"),
        context=(
            "1,00 = die örtliche Obergrenze entspricht dem Wohngeld-Höchstbetrag "
            "zuzüglich zehn Prozent · größer als 1,00 = örtlich wird mehr anerkannt"
        ),
        diverging_midpoint=1.0,
        reflects_kdu_cap=True,
    ),
    MeasureSpec(
        key="max_wohnflaeche",
        column="max_wohnflaeche",
        label="Angemessene Wohnfläche",
        unit="m²",
        hover_format=",.0f",
        headline="Angemessene Wohnfläche",
        context=f"{_SGB_BASIS} · Quadratmeter",
    ),
    MeasureSpec(
        key="share_of_stock_above_cap",
        column="share_of_stock_above_cap",
        label="Anteil der Mietwohnungen oberhalb der Obergrenze",
        unit="%",
        hover_format=",.1f",
        headline="Anteil der örtlichen Mietwohnungen oberhalb der Mietobergrenze",
        context=(
            "Zensus 2022, Bestandsmieten nettokalt je Quadratmeter, umgerechnet "
            "auf Bruttokaltmiete · Prozent der vermieteten Wohnungen"
        ),
        reflects_kdu_cap=True,
    ),
)


def get_measure(key: str) -> MeasureSpec:
    """Return the measure registered under `key`.

    Args:
        key: Stable identifier of a measure in `MEASURES`.

    Returns:
        The matching specification.

    Raises:
        ValueError: If no measure carries that key.
    """
    for spec in MEASURES:
        if spec.key == key:
            return spec
    registered = ", ".join(spec.key for spec in MEASURES)
    msg = f"Unknown measure {key!r}; registered measures are {registered}"
    raise ValueError(msg)


def compute_colour_range(
    values: pd.Series,
    spec: MeasureSpec,
) -> tuple[float, float]:
    """Compute the displayed colour range of a measure.

    The Mietenstufe spans its statutory scale. A diverging measure is given a
    range symmetric around its midpoint, so that equal departures in either
    direction read as equally strong. Every other measure spans its 2nd to 98th
    percentile.

    Args:
        values: Measure values, missing observations included.
        spec: Display specification of the measure.

    Returns:
        The lower and upper bound of the colour range.

    Raises:
        ValueError: If `values` holds no observation.
    """
    observed = values.dropna()
    if observed.empty:
        msg = f"Measure {spec.key!r} has no observed values."
        raise ValueError(msg)
    if spec.is_ordinal:
        return (1.0, 7.0)
    lower, upper = observed.quantile([LOWER_DISPLAY_QUANTILE, UPPER_DISPLAY_QUANTILE])
    if spec.diverging_midpoint is not None:
        midpoint = spec.diverging_midpoint
        limit = max(abs(float(lower) - midpoint), abs(float(upper) - midpoint))
        return (midpoint - limit, midpoint + limit)
    return (float(lower), float(upper))
