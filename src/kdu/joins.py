"""Guards for the joins that assemble the analysis tables.

Every table in this project is keyed on the eight-digit AGS, most of them on
the AGS together with a household size. A key that repeats on the right-hand
side of a join multiplies rows silently: the result still looks like a valid
frame, every column is present, and every weighted statistic computed from it
is wrong. These guards raise instead.
"""

from collections.abc import Sequence
from typing import Literal

import pandas as pd

# How many offending keys an error message lists before truncating.
MAX_KEYS_IN_MESSAGE = 10

JoinType = Literal["left", "inner"]
"""The join types the cleaning code uses; nothing here needs an outer join."""


def merge_without_duplicating(
    left: pd.DataFrame,
    right: pd.DataFrame,
    on: Sequence[str],
    how: JoinType = "left",
) -> pd.DataFrame:
    """Merge `right` onto `left` and raise if the row count changes.

    Args:
        left: The frame whose rows the result must preserve.
        right: The frame to attach; its `on` columns must be unique.
        on: Join key columns, present in both frames.
        how: Join type, `"left"` or `"inner"`.

    Returns:
        The merged frame, with exactly `len(left)` rows when `how="left"`.

    Raises:
        ValueError: If `right` repeats a key, or the join changes the row count.

    """
    _fail_if_keys_not_unique(right, on)
    merged = left.merge(right, on=list(on), how=how)
    if how == "left":
        _fail_if_join_duplicated_rows(len(left), len(merged), on)
    return merged


def _fail_if_keys_not_unique(frame: pd.DataFrame, on: Sequence[str]) -> None:
    """Raise if the join key repeats in the frame being attached."""
    missing = sorted(set(on) - set(frame.columns))
    if missing:
        msg = f"join key column(s) {missing} are absent from the right-hand frame"
        raise ValueError(msg)
    duplicated = frame.loc[frame.duplicated(subset=list(on)), list(on)]
    if not duplicated.empty:
        examples = duplicated.head(MAX_KEYS_IN_MESSAGE).to_dict("records")
        msg = (
            f"the right-hand frame repeats {len(duplicated)} of its {list(on)} "
            f"keys, so the join would multiply rows; examples: {examples}"
        )
        raise ValueError(msg)


def _fail_if_join_duplicated_rows(
    expected: int,
    observed: int,
    on: Sequence[str],
) -> None:
    """Raise if a left join returned a different number of rows than it was given."""
    if observed != expected:
        msg = (
            f"joining on {list(on)} changed the row count from {expected} to "
            f"{observed}; the key is not unique on the right-hand side"
        )
        raise ValueError(msg)


def fail_if_key_not_unique(frame: pd.DataFrame, on: Sequence[str]) -> None:
    """Raise if `frame` does not hold at most one row per `on` combination.

    Args:
        frame: The table to check.
        on: The columns that are meant to identify a row.

    Raises:
        ValueError: If any key combination appears more than once.

    """
    _fail_if_keys_not_unique(frame, on)
