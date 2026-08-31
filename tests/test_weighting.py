"""The weighted statistics every analysis package reports its results under."""

import numpy as np
import pandas as pd
import pytest

from kdu.weighting import (
    weighted_mean,
    weighted_quantile,
    weighted_share,
    weighted_standard_deviation,
)


def test_weighted_mean_matches_hand_computation() -> None:
    """`(1*1 + 2*3 + 3*6) / (1 + 3 + 6)` is 2.5."""
    values = pd.Series([1.0, 2.0, 3.0])
    weights = pd.Series([1.0, 3.0, 6.0])
    assert weighted_mean(values, weights) == pytest.approx(2.5)


def test_weighted_mean_ignores_rows_with_a_missing_value() -> None:
    """A missing value drops its row rather than making the whole mean missing."""
    values = pd.Series([10.0, np.nan, 20.0])
    weights = pd.Series([1.0, 99.0, 1.0])
    assert weighted_mean(values, weights) == pytest.approx(15.0)


def test_weighted_median_with_equal_weights_is_the_middle_observation() -> None:
    """Five equally weighted values put the median on the third of them."""
    values = pd.Series([4.0, 1.0, 3.0, 2.0, 5.0])
    weights = pd.Series(1.0, index=values.index)
    assert weighted_quantile(values, weights, 0.5) == pytest.approx(3.0)


def test_weighted_quantile_places_each_observation_at_its_weight_midpoint() -> None:
    """Five equal weights sit at 0.1, 0.3, 0.5, 0.7, 0.9, so 0.25 falls at 1.75.

    This is deliberately not `pandas.Series.quantile`, which would return 2.0:
    that estimator places the smallest and largest observation at 0 and 1 and so
    reads them as the population minimum and maximum.
    """
    values = pd.Series([4.0, 1.0, 3.0, 2.0, 5.0])
    weights = pd.Series(1.0, index=values.index)
    assert weighted_quantile(values, weights, 0.25) == pytest.approx(1.75)


def test_weighted_quantile_shifts_towards_the_heavier_observation() -> None:
    """With all weight on one value, every quantile is that value."""
    values = pd.Series([1.0, 100.0])
    weights = pd.Series([0.0, 5.0])
    assert weighted_quantile(values, weights, 0.5) == pytest.approx(100.0)


def test_weighted_standard_deviation_matches_hand_computation() -> None:
    """Two values 10 apart with equal weight have a standard deviation of 5."""
    values = pd.Series([0.0, 10.0])
    weights = pd.Series([1.0, 1.0])
    assert weighted_standard_deviation(values, weights) == pytest.approx(5.0)


def test_weighted_share_returns_a_proportion() -> None:
    """Weights 1 and 3 on false and true give a share of 0.75."""
    indicator = pd.Series([False, True])
    weights = pd.Series([1.0, 3.0])
    assert weighted_share(indicator, weights) == pytest.approx(0.75)


def test_weighted_mean_of_an_empty_subgroup_is_nan() -> None:
    """An empty subgroup is a fact about the data, not an error."""
    assert np.isnan(weighted_mean(pd.Series(dtype=float), pd.Series(dtype=float)))


def test_weighted_quantile_rejects_a_probability_outside_the_unit_interval() -> None:
    """A quantile above one is a caller error, not a value to extrapolate."""
    with pytest.raises(ValueError, match="must lie in"):
        weighted_quantile(pd.Series([1.0]), pd.Series([1.0]), 1.5)
