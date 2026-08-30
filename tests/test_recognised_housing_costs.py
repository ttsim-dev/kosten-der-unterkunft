"""The § 22 SGB II recognised-housing-cost rule."""

import numpy as np
import pytest

from kdu.eligibility.recognised_housing_costs import (
    fail_if_not_weakly_decreasing,
    kopfteil_eur_per_month,
    recognised_bruttokaltmiete_eur_per_month,
    round_currency,
    unterkunftskosten_eur_per_month,
)


def test_recognised_bruttokaltmiete_is_the_cap_when_the_rent_exceeds_it() -> None:
    """A rent above the cap is recognised only up to the cap."""
    recognised = recognised_bruttokaltmiete_eur_per_month(
        np.array([600.0]),
        np.array([486.0]),
    )
    np.testing.assert_allclose(recognised, [486.0])


def test_recognised_bruttokaltmiete_is_the_rent_when_it_stays_below_the_cap() -> None:
    """A rent below the cap is recognised in full."""
    recognised = recognised_bruttokaltmiete_eur_per_month(
        np.array([400.0]),
        np.array([486.0]),
    )
    np.testing.assert_allclose(recognised, [400.0])


def test_unterkunftskosten_add_heating_to_the_capped_rent() -> None:
    """Heating is recognised in full on top of the capped Bruttokaltmiete."""
    total = unterkunftskosten_eur_per_month(
        np.array([600.0]),
        np.array([486.0]),
        np.array([67.76]),
    )
    np.testing.assert_allclose(total, [553.76])


def test_kopfteil_splits_the_household_amount_equally() -> None:
    """A four-person household carries a quarter of the housing amount each."""
    per_person = kopfteil_eur_per_month(np.array([800.0]), np.array([4]))
    np.testing.assert_allclose(per_person, [200.0])


def test_kopfteil_rejects_an_empty_household() -> None:
    """A household of zero persons has no per-person share to compute."""
    with pytest.raises(ValueError, match="at least 1"):
        kopfteil_eur_per_month(np.array([800.0]), np.array([0]))


def test_recognised_bruttokaltmiete_rejects_a_negative_rent() -> None:
    """A negative Bruttokaltmiete is a data error rather than a zero rent."""
    with pytest.raises(ValueError, match="non-negative"):
        recognised_bruttokaltmiete_eur_per_month(np.array([-1.0]), np.array([486.0]))


def test_weakly_decreasing_check_accepts_a_falling_anspruch() -> None:
    """An Anspruch that never rises with income satisfies the check."""
    fail_if_not_weakly_decreasing(np.array([500.0, 500.0, 300.0, 0.0]), "anspruch")


def test_weakly_decreasing_check_rejects_a_rising_anspruch() -> None:
    """An Anspruch that rises with income invalidates the bisection."""
    with pytest.raises(ValueError, match="not weakly decreasing"):
        fail_if_not_weakly_decreasing(np.array([300.0, 400.0]), "anspruch")


def test_round_currency_rounds_to_whole_cents() -> None:
    """Money is reported to the cent."""
    np.testing.assert_allclose(round_currency(np.array([486.12345])), [486.12])
