"""How a published Richtlinie becomes a Bruttokaltmiete cap."""

import pandas as pd
import pytest

from kdu.data_management.clean_kdu_regions import (
    CalculationMethod,
    build_kdu_cap,
    detect_wohngeld_rule,
    source_identifier,
)


def _long_frame(
    gross: list[float | None],
    net: list[float | None],
    cold_opex: list[float | None],
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "gross_cold_cap_total": pd.array(gross, dtype="Float64"),
            "net_cold_cap_total": pd.array(net, dtype="Float64"),
            "cold_opex_cap_total": pd.array(cold_opex, dtype="Float64"),
        },
    )


def test_published_gross_cold_total_is_taken_unchanged() -> None:
    """A document that prints a Bruttokaltmiete of 486 € yields exactly 486 €."""
    result = build_kdu_cap(_long_frame([486.0], [None], [None]))
    assert result["kdu_cap"].iloc[0] == pytest.approx(486.0)
    assert (
        result["calculation_method"].iloc[0]
        == CalculationMethod.PUBLISHED_GROSS_COLD_TOTAL.value
    )


def test_cap_is_the_sum_of_the_two_published_components() -> None:
    """A Nettokaltmiete of 380 € and a cold-cost cap of 75 € give 455 €."""
    result = build_kdu_cap(_long_frame([None], [380.0], [75.0]))
    assert result["kdu_cap"].iloc[0] == pytest.approx(455.0)
    assert (
        result["calculation_method"].iloc[0]
        == CalculationMethod.SUM_OF_PUBLISHED_COMPONENTS.value
    )


def test_a_gross_total_equal_to_its_components_counts_as_the_component_sum() -> None:
    """380 + 75 printed alongside a total of 455 is the component sum."""
    result = build_kdu_cap(_long_frame([455.0], [380.0], [75.0]))
    assert (
        result["calculation_method"].iloc[0]
        == CalculationMethod.SUM_OF_PUBLISHED_COMPONENTS.value
    )


def test_a_nettokaltmiete_without_a_cold_cost_cap_yields_no_cap() -> None:
    """A euro-per-square-metre derivation is never attempted, so the cap is missing."""
    result = build_kdu_cap(_long_frame([None], [380.0], [None]))
    assert pd.isna(result["kdu_cap"].iloc[0])
    assert (
        result["calculation_method"].iloc[0] == CalculationMethod.NOT_CONSTRUCTED.value
    )


def test_a_kreis_at_the_markup_at_every_size_is_suspected_of_the_fallback() -> None:
    """Caps of exactly 1.10 times the Höchstbetrag at both sizes raise the suspicion."""
    caps = pd.DataFrame(
        {
            "ags": ["01001000", "01001000"],
            "household_size": [1, 2],
            "kdu_cap": [550.0, 660.0],
        },
    )
    hoechstbetrag = pd.DataFrame({"wohngeld_hoechstbetrag": [500.0, 600.0]})
    notes = pd.Series(["", ""])
    result = detect_wohngeld_rule(caps, hoechstbetrag, notes)
    assert bool(result["wohngeld_rule_suspected"].iloc[0]) is True


def test_a_kreis_away_from_the_markup_is_not_suspected() -> None:
    """Caps unrelated to the Höchstbetrag leave the suspicion unraised."""
    caps = pd.DataFrame(
        {
            "ags": ["01002000", "01002000"],
            "household_size": [1, 2],
            "kdu_cap": [486.0, 540.0],
        },
    )
    hoechstbetrag = pd.DataFrame({"wohngeld_hoechstbetrag": [500.0, 600.0]})
    notes = pd.Series(["", ""])
    result = detect_wohngeld_rule(caps, hoechstbetrag, notes)
    assert bool(result["wohngeld_rule_suspected"].iloc[0]) is False


def test_notes_naming_the_sicherheitszuschlag_raise_the_suspicion() -> None:
    """The collectors' wording is a reading of its own, independent of the ratio."""
    caps = pd.DataFrame(
        {
            "ags": ["01003000"],
            "household_size": [1],
            "kdu_cap": [486.0],
        },
    )
    hoechstbetrag = pd.DataFrame({"wohngeld_hoechstbetrag": [500.0]})
    notes = pd.Series(["Wohngeldtabelle zzgl. 10 % Sicherheitszuschlag"])
    result = detect_wohngeld_rule(caps, hoechstbetrag, notes)
    assert bool(result["wohngeld_rule_suspected"].iloc[0]) is True


def test_source_identifier_is_a_lowercase_slug_of_the_filename() -> None:
    """`KdU Flensburg Stadt-01.07.2025.pdf` becomes a stable joinable key."""
    result = source_identifier(pd.Series(["KdU Flensburg Stadt-01.07.2025.pdf"]))
    assert result.iloc[0] == "kdu_flensburg_stadt_01_07_2025_pdf"
