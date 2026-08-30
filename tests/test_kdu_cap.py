import numpy as np
import pytest

from kdu.simulation.kdu_cap import (
    GETTSIM_UNTERKUNFTSKOSTEN_COLUMN,
    fail_if_not_weakly_decreasing,
    kopfteil_m,
    recognised_bruttokaltmiete_m,
    unterkunftskosten_m,
)

RENT_GRID = np.arange(0.0, 1200.0, 25.0)


def test_gettsim_column_name_is_the_buergergeld_kdu_node() -> None:
    assert GETTSIM_UNTERKUNFTSKOSTEN_COLUMN == "bürgergeld__kosten_der_unterkunft_m"


def test_identical_caps_yield_identical_recognised_amounts() -> None:
    """§12.8 test 1: with K == W the two scenarios cannot differ anywhere."""
    cap = np.full_like(RENT_GRID, 480.0)
    np.testing.assert_allclose(
        recognised_bruttokaltmiete_m(RENT_GRID, cap),
        recognised_bruttokaltmiete_m(RENT_GRID, cap.copy()),
    )


def test_identical_caps_yield_identical_unterkunftskosten() -> None:
    """§12.8 test 1, carried through to the amount GETTSIM is handed."""
    cap = np.full_like(RENT_GRID, 480.0)
    heizkosten = np.full_like(RENT_GRID, 92.0)
    np.testing.assert_allclose(
        unterkunftskosten_m(RENT_GRID, cap, heizkosten),
        unterkunftskosten_m(RENT_GRID, cap.copy(), heizkosten),
    )


def test_rent_below_both_caps_is_recognised_in_full_under_both_caps() -> None:
    """§12.8 test 2: for m < min(K, W) the cap never binds, so K and W agree."""
    kdu_cap = np.array([520.0, 610.0, 480.0])
    wogg_cap = np.array([456.0, 551.0, 408.0])
    actual_rent = np.array([300.0, 400.0, 350.0])
    np.testing.assert_allclose(
        recognised_bruttokaltmiete_m(actual_rent, kdu_cap),
        recognised_bruttokaltmiete_m(actual_rent, wogg_cap),
    )


def test_rent_above_both_caps_makes_the_difference_exactly_k_minus_w() -> None:
    """§12.8 test 3: for m > max(K, W) the recognised difference is K - W."""
    kdu_cap = np.array([520.0, 610.0, 480.0])
    wogg_cap = np.array([456.0, 551.0, 408.0])
    actual_rent = np.array([900.0, 900.0, 900.0])
    difference = recognised_bruttokaltmiete_m(
        actual_rent, kdu_cap
    ) - recognised_bruttokaltmiete_m(actual_rent, wogg_cap)
    np.testing.assert_allclose(difference, kdu_cap - wogg_cap)


def test_heating_cancels_from_the_scenario_difference() -> None:
    """§12.3: heating is held constant, so it drops out of the K - W contrast."""
    kdu_cap = np.array([520.0])
    wogg_cap = np.array([456.0])
    actual_rent = np.array([900.0])
    heizkosten = np.array([92.0])
    difference = unterkunftskosten_m(
        actual_rent, kdu_cap, heizkosten
    ) - unterkunftskosten_m(actual_rent, wogg_cap, heizkosten)
    np.testing.assert_allclose(difference, kdu_cap - wogg_cap)


def test_unterkunftskosten_add_heating_on_top_of_the_capped_rent() -> None:
    np.testing.assert_allclose(
        unterkunftskosten_m(np.array([900.0]), np.array([480.0]), np.array([92.0])),
        np.array([572.0]),
    )


def test_recognised_amount_is_weakly_increasing_in_the_cap() -> None:
    """D10's bisection needs the recognised amount to be monotone in the cap."""
    caps = np.arange(100.0, 900.0, 10.0)
    recognised = recognised_bruttokaltmiete_m(np.full_like(caps, 700.0), caps)
    assert np.all(np.diff(recognised) >= 0.0)


@pytest.mark.parametrize("bad_rent", [-1.0, np.nan, np.inf])
def test_recognised_bruttokaltmiete_rejects_invalid_rent(bad_rent: float) -> None:
    with pytest.raises(ValueError, match="actual_bruttokaltmiete_m"):
        recognised_bruttokaltmiete_m(np.array([bad_rent]), np.array([480.0]))


@pytest.mark.parametrize("bad_cap", [-1.0, np.nan])
def test_recognised_bruttokaltmiete_rejects_invalid_cap(bad_cap: float) -> None:
    with pytest.raises(ValueError, match="cap_m"):
        recognised_bruttokaltmiete_m(np.array([300.0]), np.array([bad_cap]))


def test_weakly_decreasing_sequence_passes_the_monotonicity_assertion() -> None:
    fail_if_not_weakly_decreasing(
        np.array([1013.0, 900.0, 900.0, 400.0, 0.0]), name="anspruch_m"
    )


def test_increasing_sequence_fails_the_monotonicity_assertion() -> None:
    with pytest.raises(ValueError, match="anspruch_m"):
        fail_if_not_weakly_decreasing(
            np.array([1013.0, 900.0, 950.0, 0.0]), name="anspruch_m"
        )


def test_monotonicity_assertion_tolerates_rounding_noise() -> None:
    fail_if_not_weakly_decreasing(
        np.array([100.0, 100.0 + 1e-10, 50.0]), name="anspruch_m", tolerance=1e-8
    )


def test_kopfteil_splits_the_household_amount_equally() -> None:
    np.testing.assert_allclose(
        kopfteil_m(np.array([690.0, 690.0]), np.array([2, 2])),
        np.array([345.0, 345.0]),
    )


def test_kopfteil_leaves_a_single_person_household_unchanged() -> None:
    np.testing.assert_allclose(
        kopfteil_m(np.array([572.0]), np.array([1])), np.array([572.0])
    )


def test_kopfteil_rejects_an_empty_household() -> None:
    with pytest.raises(ValueError, match="anzahl_personen_hh"):
        kopfteil_m(np.array([690.0]), np.array([0]))
