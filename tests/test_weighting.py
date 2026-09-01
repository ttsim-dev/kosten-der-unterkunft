"""The weighted statistics every analysis package reports its results under."""

import numpy as np
import pandas as pd
import pytest

from kdu.weighting import (
    ExtremeAllocation,
    allocate_group_total_to_extreme_value,
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


def test_allocate_group_total_to_the_lowest_value() -> None:
    """A group total of 10 lands entirely on the row holding the smallest value."""
    weights = allocate_group_total_to_extreme_value(
        values=pd.Series([3.0, 1.0, 2.0]),
        groups=pd.Series(["a", "a", "a"]),
        group_totals=pd.Series([10.0, 10.0, 10.0]),
        extreme=ExtremeAllocation.LOWEST,
    )
    assert weights.tolist() == pytest.approx([0.0, 10.0, 0.0])


def test_allocate_group_total_to_the_highest_value() -> None:
    """A group total of 10 lands entirely on the row holding the largest value."""
    weights = allocate_group_total_to_extreme_value(
        values=pd.Series([3.0, 1.0, 2.0]),
        groups=pd.Series(["a", "a", "a"]),
        group_totals=pd.Series([10.0, 10.0, 10.0]),
        extreme=ExtremeAllocation.HIGHEST,
    )
    assert weights.tolist() == pytest.approx([10.0, 0.0, 0.0])


def test_allocate_group_total_splits_a_tie_equally() -> None:
    """Two rows tied at the smallest value take five each out of a total of 10."""
    weights = allocate_group_total_to_extreme_value(
        values=pd.Series([1.0, 1.0, 4.0]),
        groups=pd.Series(["a", "a", "a"]),
        group_totals=pd.Series([10.0, 10.0, 10.0]),
        extreme=ExtremeAllocation.LOWEST,
    )
    assert weights.tolist() == pytest.approx([5.0, 5.0, 0.0])


def test_allocate_group_total_treats_each_group_separately() -> None:
    """Each group's own total goes to that group's own extreme row."""
    weights = allocate_group_total_to_extreme_value(
        values=pd.Series([3.0, 1.0, 8.0, 6.0]),
        groups=pd.Series(["a", "a", "b", "b"]),
        group_totals=pd.Series([10.0, 10.0, 20.0, 20.0]),
        extreme=ExtremeAllocation.LOWEST,
    )
    assert weights.tolist() == pytest.approx([0.0, 10.0, 0.0, 20.0])


def test_allocate_group_total_conserves_every_group_total() -> None:
    """Allocation moves a total within its group and never creates or destroys any."""
    weights = allocate_group_total_to_extreme_value(
        values=pd.Series([3.0, 1.0, 8.0, 6.0]),
        groups=pd.Series(["a", "a", "b", "b"]),
        group_totals=pd.Series([10.0, 10.0, 20.0, 20.0]),
        extreme=ExtremeAllocation.HIGHEST,
    )
    assert weights.sum() == pytest.approx(30.0)


def test_allocate_group_total_skips_a_row_without_a_value() -> None:
    """A row whose value is missing is no candidate, so the total passes it by."""
    weights = allocate_group_total_to_extreme_value(
        values=pd.Series([np.nan, 4.0]),
        groups=pd.Series(["a", "a"]),
        group_totals=pd.Series([10.0, 10.0]),
        extreme=ExtremeAllocation.LOWEST,
    )
    assert weights.tolist() == pytest.approx([0.0, 10.0])


def test_allocate_group_total_leaves_a_valueless_group_at_zero() -> None:
    """A group in which no row carries a value allocates nothing at all."""
    weights = allocate_group_total_to_extreme_value(
        values=pd.Series([np.nan, np.nan]),
        groups=pd.Series(["a", "a"]),
        group_totals=pd.Series([10.0, 10.0]),
        extreme=ExtremeAllocation.LOWEST,
    )
    assert weights.tolist() == pytest.approx([0.0, 0.0])


def test_allocate_group_total_leaves_an_unreported_group_at_zero() -> None:
    """A group whose total is unreported allocates nothing rather than guessing."""
    weights = allocate_group_total_to_extreme_value(
        values=pd.Series([1.0, 4.0]),
        groups=pd.Series(["a", "a"]),
        group_totals=pd.Series([np.nan, np.nan]),
        extreme=ExtremeAllocation.LOWEST,
    )
    assert weights.tolist() == pytest.approx([0.0, 0.0])


def test_allocate_group_total_rejects_two_totals_for_one_group() -> None:
    """Two tied rows carrying different group totals cannot both be that group's."""
    with pytest.raises(ValueError, match="changed the total"):
        allocate_group_total_to_extreme_value(
            values=pd.Series([1.0, 1.0]),
            groups=pd.Series(["a", "a"]),
            group_totals=pd.Series([10.0, 20.0]),
            extreme=ExtremeAllocation.LOWEST,
        )
