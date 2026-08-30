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
    headline: str = ""
    """Figure title naming what the colour actually shows. Falls back to `label`."""
    context: str = ""
    """Second title line: legal basis, unit, and how to read the scale."""
    counterpart_column: str = ""
    """Column proving a blank Gemeinde is regulated under the other rent concept."""
    counterpart_text: str = ""
    """How to describe those Gemeinden in the coverage breakdown."""
    colourbar_title: str = ""
    """Colour bar caption. Falls back to `unit`, then to `Mietstufe`."""
    reflects_kdu_cap: bool = False
    """Whether the value is a KdU rent cap a Härtefallzuschlag would raise.

    Selects the hatch overlay. False for the Mietstufe, the Wohngeld-Höchstbeträge
    and the Wohnflächen, none of which a rent top-up changes.
    """


_SGB_BASIS = "Kosten der Unterkunft nach § 22 SGB II / § 35 SGB XII"

_CONTEXT_MIETSTUFE = "Stufe 1-7 · Grundlage der Wohngeld-Höchstbeträge nach § 12 WoGG"

_CONTEXT_BRUTTO = f"{_SGB_BASIS} · €/Monat, mit kalten Nebenkosten, ohne Heizkosten"

_CONTEXT_BRUTTO_SQM = (
    f"{_SGB_BASIS} · € je m² und Monat, mit kalten Nebenkosten, ohne Heizkosten"
)

_CONTEXT_NETTO = f"{_SGB_BASIS} · €/Monat, ohne Nebenkosten und ohne Heizkosten"

_CONTEXT_FLAECHE = f"{_SGB_BASIS} · m²"

_CONTEXT_WOGG = (
    "§ 12 Abs. 1 WoGG, Anlage 1 (Fassung 1. Januar 2025) · €/Monat, Bruttokaltmiete"
)

_CONTEXT_VERGLEICH = (
    "In % des Wohngeld-Höchstbetrags nach § 12 WoGG · 0 % = Obergrenze entspricht dem "
    "Höchstbetrag, positiv = es wird mehr anerkannt"
)

MEASURES: tuple[MeasureSpec, ...] = (
    MeasureSpec(
        key="wogg_mietstufe",
        column="wogg_mietstufe",
        label="Mietstufe · Stufe 1-7",
        unit="",
        hover_format="d",
        is_ordinal=True,
        headline="Mietstufe der Gemeinde",
        context=_CONTEXT_MIETSTUFE,
        colourbar_title="Mietstufe",
    ),
    MeasureSpec(
        key="max_bruttokaltmiete_eur_1p",
        column="max_bruttokaltmiete_eur_1p",
        reflects_kdu_cap=True,
        label="Obergrenze · Bruttokaltmiete (mit kalten Nebenkosten), 1 Person",
        unit="€",
        hover_format=",.0f",
        is_ordinal=False,
        headline="Höchstens anerkannte Bruttokaltmiete, 1-Personen-Haushalt",
        context=_CONTEXT_BRUTTO,
        counterpart_column="max_nettokaltmiete_eur_1p",
        counterpart_text="als Nettokaltmiete geregelt",
        colourbar_title="€/Monat",
    ),
    MeasureSpec(
        key="max_bruttokaltmiete_eur_2p",
        column="max_bruttokaltmiete_eur_2p",
        reflects_kdu_cap=True,
        label="Obergrenze · Bruttokaltmiete (mit kalten Nebenkosten), 2 Personen",
        unit="€",
        hover_format=",.0f",
        is_ordinal=False,
        headline="Höchstens anerkannte Bruttokaltmiete, 2-Personen-Haushalt",
        context=_CONTEXT_BRUTTO,
        counterpart_column="max_nettokaltmiete_eur_1p",
        counterpart_text="als Nettokaltmiete geregelt",
        colourbar_title="€/Monat",
    ),
    MeasureSpec(
        key="max_bruttokaltmiete_eur_4p",
        column="max_bruttokaltmiete_eur_4p",
        reflects_kdu_cap=True,
        label="Obergrenze · Bruttokaltmiete (mit kalten Nebenkosten), 4 Personen",
        unit="€",
        hover_format=",.0f",
        is_ordinal=False,
        headline="Höchstens anerkannte Bruttokaltmiete, 4-Personen-Haushalt",
        context=_CONTEXT_BRUTTO,
        counterpart_column="max_nettokaltmiete_eur_1p",
        counterpart_text="als Nettokaltmiete geregelt",
        colourbar_title="€/Monat",
    ),
    MeasureSpec(
        key="max_bruttokaltmiete_eur_sqm",
        column="max_bruttokaltmiete_eur_sqm",
        reflects_kdu_cap=True,
        label="Obergrenze · Bruttokaltmiete je m²",
        unit="€/m²",
        hover_format=",.2f",
        is_ordinal=False,
        headline="Höchstens anerkannte Bruttokaltmiete je m²",
        context=_CONTEXT_BRUTTO_SQM,
        colourbar_title="€/m² und Monat",
    ),
    MeasureSpec(
        key="max_nettokaltmiete_eur_1p",
        column="max_nettokaltmiete_eur_1p",
        reflects_kdu_cap=True,
        label="Obergrenze · Nettokaltmiete (ohne Nebenkosten), 1 Person",
        unit="€",
        hover_format=",.0f",
        is_ordinal=False,
        headline="Höchstens anerkannte Nettokaltmiete, 1-Personen-Haushalt",
        context=_CONTEXT_NETTO,
        counterpart_column="max_bruttokaltmiete_eur_1p",
        counterpart_text="als Bruttokaltmiete geregelt",
        colourbar_title="€/Monat",
    ),
    MeasureSpec(
        key="max_nettokaltmiete_eur_4p",
        column="max_nettokaltmiete_eur_4p",
        reflects_kdu_cap=True,
        label="Obergrenze · Nettokaltmiete (ohne Nebenkosten), 4 Personen",
        unit="€",
        hover_format=",.0f",
        is_ordinal=False,
        headline="Höchstens anerkannte Nettokaltmiete, 4-Personen-Haushalt",
        context=_CONTEXT_NETTO,
        counterpart_column="max_bruttokaltmiete_eur_1p",
        counterpart_text="als Bruttokaltmiete geregelt",
        colourbar_title="€/Monat",
    ),
    MeasureSpec(
        key="max_wohnflaeche_sqm_1p",
        column="max_wohnflaeche_sqm_1p",
        label="Wohnfläche · angemessen, 1 Person",
        unit="m²",
        hover_format=",.0f",
        is_ordinal=False,
        headline="Angemessene Wohnfläche, 1-Personen-Haushalt",
        context=_CONTEXT_FLAECHE,
        colourbar_title="m²",
    ),
    MeasureSpec(
        key="max_wohnflaeche_sqm_4p",
        column="max_wohnflaeche_sqm_4p",
        label="Wohnfläche · angemessen, 4 Personen",
        unit="m²",
        hover_format=",.0f",
        is_ordinal=False,
        headline="Angemessene Wohnfläche, 4-Personen-Haushalt",
        context=_CONTEXT_FLAECHE,
        colourbar_title="m²",
    ),
    MeasureSpec(
        key="wogg_hoechstbetrag_eur_1p",
        column="wogg_hoechstbetrag_eur_1p",
        label="Wohngeld · Höchstbetrag § 12 WoGG, 1 Person",
        unit="€",
        hover_format=",.0f",
        is_ordinal=False,
        headline="Wohngeld-Höchstbetrag für Miete, 1-Personen-Haushalt",
        context=_CONTEXT_WOGG,
        colourbar_title="€/Monat",
    ),
    MeasureSpec(
        key="wogg_hoechstbetrag_eur_2p",
        column="wogg_hoechstbetrag_eur_2p",
        label="Wohngeld · Höchstbetrag § 12 WoGG, 2 Personen",
        unit="€",
        hover_format=",.0f",
        is_ordinal=False,
        headline="Wohngeld-Höchstbetrag für Miete, 2-Personen-Haushalt",
        context=_CONTEXT_WOGG,
        colourbar_title="€/Monat",
    ),
    MeasureSpec(
        key="wogg_hoechstbetrag_eur_4p",
        column="wogg_hoechstbetrag_eur_4p",
        label="Wohngeld · Höchstbetrag § 12 WoGG, 4 Personen",
        unit="€",
        hover_format=",.0f",
        is_ordinal=False,
        headline="Wohngeld-Höchstbetrag für Miete, 4-Personen-Haushalt",
        context=_CONTEXT_WOGG,
        colourbar_title="€/Monat",
    ),
    MeasureSpec(
        key="kdu_vs_wogg_pct_1p",
        column="kdu_vs_wogg_pct_1p",
        reflects_kdu_cap=True,
        label="Vergleich · Abweichung vom Wohngeld-Höchstbetrag in %, 1 Person",
        unit="%",
        hover_format="+,.1f",
        is_ordinal=False,
        is_diverging=True,
        headline=(
            "Abweichung der Mietobergrenze vom Wohngeld-Höchstbetrag, 1-Personen-"
            "Haushalt"
        ),
        context=_CONTEXT_VERGLEICH,
        counterpart_column="max_nettokaltmiete_eur_1p",
        counterpart_text="als Nettokaltmiete geregelt",
        colourbar_title="% vom Wohngeld-Höchstbetrag",
    ),
    MeasureSpec(
        key="kdu_vs_wogg_pct_2p",
        column="kdu_vs_wogg_pct_2p",
        reflects_kdu_cap=True,
        label="Vergleich · Abweichung vom Wohngeld-Höchstbetrag in %, 2 Personen",
        unit="%",
        hover_format="+,.1f",
        is_ordinal=False,
        is_diverging=True,
        headline=(
            "Abweichung der Mietobergrenze vom Wohngeld-Höchstbetrag, 2-Personen-"
            "Haushalt"
        ),
        context=_CONTEXT_VERGLEICH,
        counterpart_column="max_nettokaltmiete_eur_1p",
        counterpart_text="als Nettokaltmiete geregelt",
        colourbar_title="% vom Wohngeld-Höchstbetrag",
    ),
    MeasureSpec(
        key="kdu_vs_wogg_pct_4p",
        column="kdu_vs_wogg_pct_4p",
        reflects_kdu_cap=True,
        label="Vergleich · Abweichung vom Wohngeld-Höchstbetrag in %, 4 Personen",
        unit="%",
        hover_format="+,.1f",
        is_ordinal=False,
        is_diverging=True,
        headline=(
            "Abweichung der Mietobergrenze vom Wohngeld-Höchstbetrag, 4-Personen-"
            "Haushalt"
        ),
        context=_CONTEXT_VERGLEICH,
        counterpart_column="max_nettokaltmiete_eur_1p",
        counterpart_text="als Nettokaltmiete geregelt",
        colourbar_title="% vom Wohngeld-Höchstbetrag",
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
