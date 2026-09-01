"""Weighted descriptive statistics shared by every analysis package.

Each result is reported under one of the schemes of
{class}`kdu.config.WeightingScheme`, so the same four statistics are needed
wherever a distribution is summarised. They live here once, together with
{func}`allocate_group_total_to_extreme_value`, which builds the weights a
scheme carries when a published total is known only for a group and not for the
rows inside it.

Every statistic ignores rows with a missing value or a missing weight, and
returns `nan` rather than raising when no row survives — an empty subgroup is
a fact about the data, not an error.
"""

from enum import StrEnum

import numpy as np
import pandas as pd

# Fewer observations than this leave the weighted variance undefined.
MIN_OBSERVATIONS_FOR_VARIANCE = 2

# How far a group's allocated weights may drift from its published total before
# the allocation is treated as having created or destroyed mass. Splitting a
# total over tied rows and adding it back up is a handful of floating-point
# operations, so anything beyond rounding is a defect rather than arithmetic.
ALLOCATION_RELATIVE_TOLERANCE = 1e-9
ALLOCATION_ABSOLUTE_TOLERANCE = 1e-6


class ExtremeAllocation(StrEnum):
    """Which end of a group's values an allocation places the group total on."""

    LOWEST = "lowest"
    """The rows holding the smallest value in the group."""
    HIGHEST = "highest"
    """The rows holding the largest value in the group."""


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


def allocate_group_total_to_extreme_value(
    values: pd.Series,
    groups: pd.Series,
    group_totals: pd.Series,
    extreme: ExtremeAllocation,
) -> pd.Series:
    """Place each group's whole total on the rows holding its extreme value.

    A total published for a group says nothing about which row inside the group
    it belongs to. Putting all of it on the group's smallest value and then all
    of it on the group's largest brackets every placement of that total: the
    weighted mean of `values` under any placement is a weighted average of the
    per-group weighted averages, and each of those lies between the group's
    smallest and its largest value.

    Ties are split equally among the tied rows. That is the only rule invariant
    to the order the rows arrive in and to how they are labelled, so no silent
    sort decides the result. Because the tie is a tie in the very quantity being
    extremised, every split of the total among the tied rows gives that quantity
    the same weighted mean; the choice matters only for other quantities read
    under the same weights.

    A row is a candidate only if both its value and its group total are present.
    A group with no candidate allocates nothing, so its total is withheld rather
    than moved to another group.

    The comparison against the group extreme is exact rather than tolerated,
    because the extreme is drawn from the same column by `min` or `max`; two
    rows tie only when they carry the identical value.

    Args:
        values: The quantity whose extreme rows receive the total.
        groups: The group each row belongs to, aligned with `values`.
        group_totals: The total published for each row's group, repeated on
            every row of the group and aligned with `values`.
        extreme: Which end of each group's values to allocate to.

    Returns:
        A weight per row, aligned with `values`, summing within each group to
        that group's total wherever the group has a candidate and to zero
        elsewhere.

    Raises:
        ValueError: If a group's allocated weights do not sum to its total.

    """
    frame = pd.DataFrame(
        {
            "value": _as_float(values),
            "group": groups.to_numpy(),
            "total": _as_float(group_totals),
        },
        index=values.index,
    )
    candidate = frame["value"].notna() & frame["total"].notna()
    candidate_value = frame["value"].where(candidate)
    aggregation = "min" if extreme is ExtremeAllocation.LOWEST else "max"
    target = candidate_value.groupby(frame["group"], dropna=False).transform(
        aggregation
    )
    is_extreme = candidate & candidate_value.eq(target)
    tied = is_extreme.groupby(frame["group"], dropna=False).transform("sum")
    weights = pd.Series(
        np.where(is_extreme, frame["total"] / tied.where(tied > 0), 0.0),
        index=values.index,
    )
    _fail_if_allocation_departs_from_total(weights, frame, is_extreme)
    return weights


def _fail_if_allocation_departs_from_total(
    weights: pd.Series,
    frame: pd.DataFrame,
    is_extreme: pd.Series,
) -> None:
    """Raise unless every group with a candidate received exactly its total."""
    grouped = weights.groupby(frame["group"], dropna=False)
    allocated = grouped.sum()
    expected = (
        frame["total"]
        .where(is_extreme)
        .groupby(frame["group"], dropna=False)
        .max()
        .fillna(0.0)
    )
    departure = (allocated - expected).abs()
    conserved = np.isclose(
        allocated.to_numpy(dtype="float64"),
        expected.to_numpy(dtype="float64"),
        rtol=ALLOCATION_RELATIVE_TOLERANCE,
        atol=ALLOCATION_ABSOLUTE_TOLERANCE,
    )
    offending = departure.loc[~conserved]
    if not offending.empty:
        msg = (
            f"allocation changed the total of {len(offending)} group(s); "
            f"largest departure {offending.max()} on group {offending.idxmax()!r}"
        )
        raise ValueError(msg)


def _as_float(values: pd.Series) -> np.ndarray:
    """Return `values` as a plain float array, with every missing entry `nan`."""
    return (
        pd.to_numeric(values, errors="coerce")
        .astype("Float64")
        .to_numpy(
            dtype="float64",
            na_value=np.nan,
        )
    )


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
