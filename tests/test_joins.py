"""The guards that stop a repeated key from silently multiplying rows."""

import pandas as pd
import pytest

from kdu.joins import fail_if_key_not_unique, merge_without_duplicating


def test_merge_preserves_every_row_of_the_left_frame() -> None:
    """A one-to-one join returns exactly the rows it was given."""
    left = pd.DataFrame({"ags": ["01001000", "01002000"], "kdu_cap": [486.0, 455.0]})
    right = pd.DataFrame({"ags": ["01001000", "01002000"], "population": [90_000, 800]})
    result = merge_without_duplicating(left, right, on=["ags"])
    assert len(result) == 2
    assert result.loc[result["ags"] == "01001000", "population"].iloc[0] == 90_000


def test_merge_raises_when_the_right_frame_repeats_a_key() -> None:
    """A repeated key would double the rows and corrupt every weighted statistic."""
    left = pd.DataFrame({"ags": ["01001000"], "kdu_cap": [486.0]})
    right = pd.DataFrame({"ags": ["01001000", "01001000"], "population": [1, 2]})
    with pytest.raises(ValueError, match="repeats"):
        merge_without_duplicating(left, right, on=["ags"])


def test_merge_raises_when_the_join_key_is_absent() -> None:
    """A misspelled key is a caller error, not an empty join."""
    left = pd.DataFrame({"ags": ["01001000"]})
    right = pd.DataFrame({"gemeinde": ["Flensburg"]})
    with pytest.raises(ValueError, match="absent"):
        merge_without_duplicating(left, right, on=["ags"])


def test_a_composite_key_is_checked_on_both_columns() -> None:
    """The tables are keyed on AGS and household size together, not on either alone."""
    frame = pd.DataFrame(
        {
            "ags": ["01001000", "01001000"],
            "household_size": [1, 2],
            "kdu_cap": [486.0, 540.0],
        },
    )
    fail_if_key_not_unique(frame, ["ags", "household_size"])
    with pytest.raises(ValueError, match="repeats"):
        fail_if_key_not_unique(frame, ["ags"])
