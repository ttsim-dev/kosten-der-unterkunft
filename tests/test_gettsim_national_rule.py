"""GETTSIM's own recognised housing cost, checked against a literal reference.

The reference below transcribes the four GETTSIM policy functions that decide
the recognised housing cost — `kosten_der_unterkunft_m`,
`anerkannte_warmmiete_je_qm_m`, `berechtigte_wohnfläche` and the per-person
splits — as scalar arithmetic. It shares no code with the production path,
which calls GETTSIM itself, so agreement between the two is an oracle
differential rather than the same computation run twice.
"""

import numpy as np
import pandas as pd
import pytest

from kdu.eligibility.gettsim_national_rule import (
    GETTSIM_BERECHTIGTE_WOHNFLAECHE_BASE_SQM,
    GETTSIM_BERECHTIGTE_WOHNFLAECHE_PER_FURTHER_PERSON_SQM,
    GETTSIM_MIETOBERGRENZE_EUR_PER_SQM,
    ILLUSTRATIVE_DWELLING_BRUTTOKALTMIETE_EUR_PER_MONTH,
    ILLUSTRATIVE_DWELLING_HEIZKOSTEN_EUR_PER_MONTH,
    ILLUSTRATIVE_DWELLING_WOHNFLAECHE_SQM,
    HousingAssumption,
    SeparateCapsComparison,
    build_housing_assumptions,
    compare_recognised_housing_costs,
    compare_separate_caps_to_monthly_ceiling,
    gettsim_recognised_warm_eur_per_month,
    median_local_cap_eur_per_month,
    modal_admissible_area_sqm,
)


def _reference_recognised_warm_eur_per_month(
    bruttokaltmiete_hh: float,
    heizkosten_hh: float,
    wohnflaeche_hh: float,
    anzahl_personen: int,
) -> float:
    """Transcribe GETTSIM's housing rule as scalar arithmetic.

    Every quantity GETTSIM works on is per person, and the recognised amount is
    a person-level column, so the household total multiplies the per-person
    amount back up by household size.
    """
    bruttokaltmiete = bruttokaltmiete_hh / anzahl_personen
    heizkosten = heizkosten_hh / anzahl_personen
    wohnflaeche = wohnflaeche_hh / anzahl_personen
    maximum = (
        GETTSIM_BERECHTIGTE_WOHNFLAECHE_BASE_SQM
        + max(
            anzahl_personen - 1,
            0,
        )
        * GETTSIM_BERECHTIGTE_WOHNFLAECHE_PER_FURTHER_PERSON_SQM
    )
    berechtigte_wohnflaeche = min(wohnflaeche, maximum / anzahl_personen)
    warmmiete_je_qm = min(
        (bruttokaltmiete + heizkosten) / wohnflaeche,
        GETTSIM_MIETOBERGRENZE_EUR_PER_SQM,
    )
    return berechtigte_wohnflaeche * warmmiete_je_qm * anzahl_personen


@pytest.fixture
def caps() -> pd.DataFrame:
    """Five Gemeinden at household size one, with three admissible areas."""
    return pd.DataFrame(
        {
            "ags": [f"0100{index}000" for index in range(1, 6)],
            "household_size": [1, 1, 1, 1, 1],
            "kdu_cap": [300.0, 400.0, 430.0, 500.0, 600.0],
            "max_area_sqm": [50.0, 50.0, 50.0, 45.0, 48.0],
        },
    )


@pytest.fixture
def fallback() -> pd.DataFrame:
    """The Grenze ohne schlüssiges Konzept for the same five Gemeinden."""
    return pd.DataFrame(
        {
            "ags": [f"0100{index}000" for index in range(1, 6)],
            "household_size": [1, 1, 1, 1, 1],
            "wohngeld_fallback_cap": [350.0, 380.0, 400.0, 450.0, 550.0],
        },
    )


def test_gettsim_recognised_warm_matches_the_literal_reference() -> None:
    """A single adult renting 50 m² at 430.50 EUR plus 69.49 EUR heating."""
    recognised = gettsim_recognised_warm_eur_per_month(
        household_sizes=np.array([1]),
        bruttokaltmiete=np.array([430.50]),
        heizkosten=np.array([69.49]),
        wohnflaeche=np.array([50.0]),
    )
    expected = _reference_recognised_warm_eur_per_month(430.50, 69.49, 50.0, 1)
    np.testing.assert_allclose(recognised, [expected], atol=1e-6)


def test_gettsim_recognised_warm_matches_the_reference_for_a_couple_with_children() -> (
    None
):
    """A four-person household at the modal admissible area of 90 m²."""
    recognised = gettsim_recognised_warm_eur_per_month(
        household_sizes=np.array([4]),
        bruttokaltmiete=np.array([710.0]),
        heizkosten=np.array([136.77]),
        wohnflaeche=np.array([90.0]),
    )
    expected = _reference_recognised_warm_eur_per_month(710.0, 136.77, 90.0, 4)
    np.testing.assert_allclose(recognised, [expected], atol=1e-6)


def test_gettsim_area_cap_binds_at_the_actual_area_when_it_is_the_smaller() -> None:
    """A single adult in 30 m² is credited 30 m², not the statutory 45 m²."""
    recognised = gettsim_recognised_warm_eur_per_month(
        household_sizes=np.array([1]),
        bruttokaltmiete=np.array([390.0]),
        heizkosten=np.array([60.0]),
        wohnflaeche=np.array([30.0]),
    )
    np.testing.assert_allclose(
        recognised,
        [30.0 * GETTSIM_MIETOBERGRENZE_EUR_PER_SQM],
        atol=1e-6,
    )


def test_gettsim_area_cap_binds_at_the_statutory_area_when_it_is_the_smaller() -> None:
    """A single adult in 60 m² is credited the statutory 45 m²."""
    recognised = gettsim_recognised_warm_eur_per_month(
        household_sizes=np.array([1]),
        bruttokaltmiete=np.array([540.0]),
        heizkosten=np.array([60.0]),
        wohnflaeche=np.array([60.0]),
    )
    np.testing.assert_allclose(
        recognised,
        [GETTSIM_BERECHTIGTE_WOHNFLAECHE_BASE_SQM * GETTSIM_MIETOBERGRENZE_EUR_PER_SQM],
        atol=1e-6,
    )


def test_gettsim_recognises_the_full_rent_below_the_per_square_metre_ceiling() -> None:
    """At 45 m² and 7.78 EUR per m² warm, the whole warm rent is recognised."""
    recognised = gettsim_recognised_warm_eur_per_month(
        household_sizes=np.array([1]),
        bruttokaltmiete=np.array([300.0]),
        heizkosten=np.array([50.0]),
        wohnflaeche=np.array([GETTSIM_BERECHTIGTE_WOHNFLAECHE_BASE_SQM]),
    )
    np.testing.assert_allclose(recognised, [350.0], atol=1e-6)


def test_modal_admissible_area_is_the_most_frequent_published_area(
    caps: pd.DataFrame,
) -> None:
    """Three of five Richtlinien publish 50 m² for a single, so 50 m² it is."""
    assert modal_admissible_area_sqm(caps, 1) == 50.0


def test_median_local_cap_is_the_median_over_gemeinden(caps: pd.DataFrame) -> None:
    """Five caps of 300, 400, 430, 500 and 600 have a median of 430."""
    assert median_local_cap_eur_per_month(caps, 1) == 430.0


def test_build_housing_assumptions_uses_the_median_cap_as_the_actual_rent(
    caps: pd.DataFrame,
) -> None:
    """The assumed actual Bruttokaltmiete is the median local cap."""
    assumptions = build_housing_assumptions(caps, {1: 69.49}, (1,))
    assert assumptions[1] == HousingAssumption(
        household_size=1,
        actual_bruttokaltmiete_m=430.0,
        wohnflaeche_sqm=50.0,
        heizkosten_m=69.49,
    )


def test_comparison_reports_one_row_per_household_size(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
) -> None:
    """Each household size compared yields exactly one row."""
    comparison = compare_recognised_housing_costs(
        caps=caps,
        fallback=fallback,
        heizkosten_per_household_size={1: 69.49},
        household_sizes=(1,),
    )
    assert len(comparison) == 1


def test_comparison_local_cap_median_is_the_capped_actual_warm_rent(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
) -> None:
    """The median Gemeinde recognises the whole assumed warm rent, 430 + 69.49."""
    comparison = compare_recognised_housing_costs(
        caps=caps,
        fallback=fallback,
        heizkosten_per_household_size={1: 69.49},
        household_sizes=(1,),
    )
    assert comparison["local_cap_recognised_warm_m_median"].iloc[0] == 499.49


def test_comparison_records_the_gettsim_version(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
) -> None:
    """The result measures GETTSIM, so the release it was taken from travels with it."""
    comparison = compare_recognised_housing_costs(
        caps=caps,
        fallback=fallback,
        heizkosten_per_household_size={1: 69.49},
        household_sizes=(1,),
    )
    assert comparison["gettsim_version"].iloc[0] != ""


@pytest.fixture
def separate_caps_comparison() -> SeparateCapsComparison:
    """The slide's dwelling: 30 m², 390 EUR cold plus 60 EUR heating, cap 430.50."""
    return compare_separate_caps_to_monthly_ceiling(
        wohnflaeche_sqm=ILLUSTRATIVE_DWELLING_WOHNFLAECHE_SQM,
        bruttokaltmiete_m=ILLUSTRATIVE_DWELLING_BRUTTOKALTMIETE_EUR_PER_MONTH,
        heizkosten_m=ILLUSTRATIVE_DWELLING_HEIZKOSTEN_EUR_PER_MONTH,
        local_bruttokaltmiete_cap_m=430.50,
    )


def test_separate_caps_comparison_inputs_are_finite_and_positive(
    separate_caps_comparison: SeparateCapsComparison,
) -> None:
    """Area, both rent components and the cap all survive construction."""
    assert all(
        np.isfinite(value) and value > 0.0
        for value in (
            separate_caps_comparison.wohnflaeche_sqm,
            separate_caps_comparison.bruttokaltmiete_m,
            separate_caps_comparison.heizkosten_m,
            separate_caps_comparison.local_bruttokaltmiete_cap_m,
        )
    )


def test_separate_caps_comparison_warmmiete_is_the_sum_of_its_components(
    separate_caps_comparison: SeparateCapsComparison,
) -> None:
    """The warm rent is the Bruttokaltmiete plus the Heizkosten, 390 + 60."""
    assert np.isclose(
        separate_caps_comparison.warmmiete_m,
        separate_caps_comparison.bruttokaltmiete_m
        + separate_caps_comparison.heizkosten_m,
        atol=1e-9,
    )


def test_separate_caps_comparison_rejects_a_non_finite_heizkosten() -> None:
    """A Heizkosten that did not survive construction fails loudly."""
    with pytest.raises(ValueError, match="finite and positive"):
        compare_separate_caps_to_monthly_ceiling(
            wohnflaeche_sqm=30.0,
            bruttokaltmiete_m=390.0,
            heizkosten_m=float("nan"),
            local_bruttokaltmiete_cap_m=430.50,
        )


def test_separate_caps_comparison_gettsim_recognises_the_area_times_the_ceiling(
    separate_caps_comparison: SeparateCapsComparison,
) -> None:
    """GETTSIM recognises 30 m² × 10 EUR/m² warm = 300 EUR warm per month."""
    assert np.isclose(
        separate_caps_comparison.gettsim_recognised_warm_m,
        300.0,
        atol=1e-6,
    )


def test_separate_caps_comparison_gettsim_matches_the_literal_reference(
    separate_caps_comparison: SeparateCapsComparison,
) -> None:
    """GETTSIM's figure agrees with the transcribed scalar rule."""
    assert np.isclose(
        separate_caps_comparison.gettsim_recognised_warm_m,
        _reference_recognised_warm_eur_per_month(390.0, 60.0, 30.0, 1),
        atol=1e-6,
    )


def test_separate_caps_comparison_area_cap_does_not_bind(
    separate_caps_comparison: SeparateCapsComparison,
) -> None:
    """30 m² is below the 45 m² admissible for a single, so the area cap is slack."""
    assert separate_caps_comparison.gettsim_area_cap_binds is False


def test_separate_caps_comparison_price_ceiling_binds(
    separate_caps_comparison: SeparateCapsComparison,
) -> None:
    """450 EUR warm over 30 m² is 15 EUR/m², above the 10 EUR/m² ceiling."""
    assert separate_caps_comparison.gettsim_price_ceiling_binds is True


def test_separate_caps_comparison_reports_the_actual_warm_price_per_square_metre(
    separate_caps_comparison: SeparateCapsComparison,
) -> None:
    """450 EUR warm over 30 m² is 15.00 EUR per square metre and month."""
    assert np.isclose(
        separate_caps_comparison.warmmiete_je_qm_m,
        15.0,
        atol=1e-6,
    )


def test_separate_caps_comparison_local_cap_recognises_the_whole_bruttokaltmiete(
    separate_caps_comparison: SeparateCapsComparison,
) -> None:
    """390 EUR cold is below the 430.50 EUR ceiling, so all of it is recognised."""
    assert np.isclose(
        separate_caps_comparison.local_recognised_bruttokaltmiete_m,
        390.0,
        atol=1e-6,
    )


def test_separate_caps_comparison_local_heizkosten_are_assessed_separately(
    separate_caps_comparison: SeparateCapsComparison,
) -> None:
    """Heating sits outside the Bruttokaltmiete ceiling and is recognised in full."""
    assert np.isclose(
        separate_caps_comparison.local_recognised_heizkosten_m,
        60.0,
        atol=1e-6,
    )


def test_separate_caps_comparison_caps_the_bruttokaltmiete_at_the_ceiling() -> None:
    """A Bruttokaltmiete above the ceiling is recognised only up to the ceiling."""
    comparison = compare_separate_caps_to_monthly_ceiling(
        wohnflaeche_sqm=30.0,
        bruttokaltmiete_m=500.0,
        heizkosten_m=60.0,
        local_bruttokaltmiete_cap_m=430.50,
    )
    assert np.isclose(comparison.local_recognised_bruttokaltmiete_m, 430.50, atol=1e-6)


def test_separate_caps_comparison_records_the_gettsim_version(
    separate_caps_comparison: SeparateCapsComparison,
) -> None:
    """The figure is GETTSIM's own, so the release it came from travels with it."""
    assert separate_caps_comparison.gettsim_version != ""
