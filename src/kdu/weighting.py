"""Weighted descriptive statistics shared by every analysis package.

Each result is reported under one of the two schemes of
{class}`kdu.config.WeightingScheme`, so the same four statistics are needed
wherever a distribution is summarised. They live here once.

Every function ignores rows with a missing value or a missing weight, and
returns `nan` rather than raising when no row survives — an empty subgroup is
a fact about the data, not an error.
"""

import numpy as np
import pandas as pd

# Fewer observations than this leave the weighted variance undefined.
MIN_OBSERVATIONS_FOR_VARIANCE = 2


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    """Return the weighted mean of `values`.

    Args:
        values: The quantity to summarise.
        weights: Non-negative weights aligned with `values`.

    Returns:
        The weighted mean, or `nan` if no observation carries positive weight.

    """
    clean = _drop_incomplete(values, weights)
    if clean.empty or clean["weight"].sum() == 0:
        return float("nan")
    return float(np.average(clean["value"], weights=clean["weight"]))


def weighted_quantile(
    values: pd.Series,
    weights: pd.Series,
    quantile: float,
) -> float:
    """Return the `quantile` of `values` under `weights`.

    Each observation is placed at the midpoint of the weight it occupies, so
    observation `i` sits at `(cumulative weight - half its own weight) / total`,
    and the result interpolates linearly between those positions.

    Under equal weights this agrees with {meth}`pandas.Series.quantile` at the
    median but not in the tails: pandas places the `i`-th of `n` observations at
    `i / (n - 1)`, which puts the extremes at 0 and 1, while the midpoint rule
    puts them at `0.5 / n` and `1 - 0.5 / n`. The midpoint rule is used because
    it does not treat the smallest and largest observation as the population
    minimum and maximum.

    Args:
        values: The quantity to summarise.
        weights: Non-negative weights aligned with `values`.
        quantile: A probability in `[0, 1]`.

    Returns:
        The weighted quantile, or `nan` if no observation carries positive
        weight.

    """
    _fail_if_quantile_out_of_range(quantile)
    clean = _drop_incomplete(values, weights)
    clean = clean.loc[clean["weight"] > 0].sort_values("value", kind="stable")
    if clean.empty:
        return float("nan")
    weight = clean["weight"].to_numpy(dtype=float)
    position = (np.cumsum(weight) - 0.5 * weight) / weight.sum()
    return float(np.interp(quantile, position, clean["value"].to_numpy(dtype=float)))


def weighted_standard_deviation(values: pd.Series, weights: pd.Series) -> float:
    """Return the weighted standard deviation of `values`.

    Args:
        values: The quantity to summarise.
        weights: Non-negative weights aligned with `values`.

    Returns:
        The square root of the weighted variance around the weighted mean, or
        `nan` if fewer than two observations carry positive weight.

    """
    clean = _drop_incomplete(values, weights)
    if len(clean) < MIN_OBSERVATIONS_FOR_VARIANCE or clean["weight"].sum() == 0:
        return float("nan")
    mean = np.average(clean["value"], weights=clean["weight"])
    variance = np.average((clean["value"] - mean) ** 2, weights=clean["weight"])
    return float(np.sqrt(variance))


def weighted_share(indicator: pd.Series, weights: pd.Series) -> float:
    """Return the weighted share of `indicator` that is true, as a proportion.

    Args:
        indicator: A boolean series.
        weights: Non-negative weights aligned with `indicator`.

    Returns:
        A proportion in `[0, 1]`, or `nan` if no observation carries positive
        weight.

    """
    clean = _drop_incomplete(indicator.astype("Float64"), weights)
    if clean.empty or clean["weight"].sum() == 0:
        return float("nan")
    return float(np.average(clean["value"], weights=clean["weight"]))


def _drop_incomplete(values: pd.Series, weights: pd.Series) -> pd.DataFrame:
    """Pair values with weights and drop rows where either is missing."""
    paired = pd.DataFrame(
        {
            "value": pd.to_numeric(values, errors="coerce").to_numpy(dtype="float64"),
            "weight": pd.to_numeric(weights, errors="coerce").to_numpy(dtype="float64"),
        },
    )
    return paired.dropna()


def _fail_if_quantile_out_of_range(quantile: float) -> None:
    if not 0.0 <= quantile <= 1.0:
        msg = f"quantile must lie in [0, 1], got {quantile}"
        raise ValueError(msg)
