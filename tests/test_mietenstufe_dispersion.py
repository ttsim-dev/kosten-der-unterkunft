"""Tests for the variation in local KdU caps the Mietenstufe leaves unaccounted for."""

import numpy as np
import pandas as pd
import pytest

from kdu.kdu_vs_wohngeld.mietenstufe_dispersion import (
    dispersion_within_mietenstufe,
    variance_share_between_groups,
    variance_shares,
)


def test_variance_share_is_one_when_every_group_holds_one_observation() -> None:
    """A classification that separates every observation leaves nothing within."""
    values = np.array([1.0, 2.0, 3.0])
    grouping = [np.array(["a", "b", "c"])]
    assert variance_share_between_groups(values, grouping) == pytest.approx(1.0)


def test_variance_share_is_zero_when_every_observation_shares_one_group() -> None:
    """A classification with a single group accounts for none of the variation."""
    values = np.array([1.0, 2.0, 3.0, 4.0])
    grouping = [np.array(["a", "a", "a", "a"])]
    assert variance_share_between_groups(values, grouping) == pytest.approx(0.0)


def test_variance_share_matches_the_hand_computed_decomposition() -> None:
    """Values 1, 3, 5, 7 split as (1,3) and (5,7) leave 4 of 20 within groups."""
    values = np.array([1.0, 3.0, 5.0, 7.0])
    grouping = [np.array(["a", "a", "b", "b"])]
    assert variance_share_between_groups(values, grouping) == pytest.approx(0.8)


def test_variance_share_uses_the_interaction_of_several_columns() -> None:
    """Crossing two binary columns separates four observations completely."""
    values = np.array([1.0, 3.0, 5.0, 7.0])
    grouping = [np.array(["a", "a", "b", "b"]), np.array(["x", "y", "x", "y"])]
    assert variance_share_between_groups(values, grouping) == pytest.approx(1.0)


def test_variance_share_is_missing_when_the_values_do_not_vary() -> None:
    """With no variation to account for, the share is undefined rather than zero."""
    values = np.array([2.0, 2.0, 2.0])
    grouping = [np.array(["a", "b", "c"])]
    assert np.isnan(variance_share_between_groups(values, grouping))


def test_dispersion_reports_the_interdecile_range_within_a_mietenstufe() -> None:
    """Caps of 100 to 1000 in steps of 100 span 800 € between the deciles."""
    frame = _one_mietenstufe(caps=[float(step) for step in range(100, 1100, 100)])
    dispersion = dispersion_within_mietenstufe(frame)
    assert dispersion.loc[0, "interdecile_range_kdu_cap"] == pytest.approx(800.0)


def test_dispersion_reports_the_median_within_a_mietenstufe() -> None:
    """The median of ten evenly spaced caps sits between the fifth and the sixth."""
    frame = _one_mietenstufe(caps=[float(step) for step in range(100, 1100, 100)])
    dispersion = dispersion_within_mietenstufe(frame)
    assert dispersion.loc[0, "median_kdu_cap"] == pytest.approx(550.0)


def test_variance_shares_count_the_groups_each_classification_distinguishes() -> None:
    """Two Mietenstufen over four Gemeinden are two groups."""
    frame = pd.DataFrame(
        {
            "ags": ["01", "02", "03", "04"],
            "household_size": [1, 1, 1, 1],
            "kdu_cap": [400.0, 420.0, 500.0, 520.0],
            "mietenstufe": [1, 1, 2, 2],
            "state_code": ["01", "01", "01", "01"],
            "district_ags": ["011", "011", "012", "012"],
        },
    )
    shares = variance_shares(frame)
    n_groups = shares.set_index("classification").loc["mietenstufe", "n_groups"]
    assert n_groups == 2


def _one_mietenstufe(caps: list[float]) -> pd.DataFrame:
    """Return Gemeinden that all share Mietenstufe 1, Bundesland and Kreis."""
    return pd.DataFrame(
        {
            "ags": [f"{index:08d}" for index in range(len(caps))],
            "household_size": [1] * len(caps),
            "kdu_cap": caps,
            "mietenstufe": [1] * len(caps),
            "state_code": ["01"] * len(caps),
            "district_ags": ["01001"] * len(caps),
        },
    )
