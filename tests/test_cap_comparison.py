"""Tests for the departure of local KdU caps from the statutory fallback."""

import numpy as np
import pandas as pd
import pytest

from kdu.config import WeightingScheme
from kdu.kdu_vs_wohngeld.cap_comparison import (
    AnalysisPopulation,
    attach_weights,
    bedarfsgemeinschaft_weights,
    build_cap_comparison,
    cap_ratio_spread_across_household_sizes,
    stack_populations,
)


@pytest.fixture
def caps() -> pd.DataFrame:
    """Two Gemeinden observed at household sizes one and two."""
    return pd.DataFrame(
        {
            "ags": ["01001000", "01001000", "01002000", "01002000"],
            "household_size": [1, 2, 1, 2],
            "kdu_cap": [500.0, 600.0, 400.0, 480.0],
        },
    )


@pytest.fixture
def fallback() -> pd.DataFrame:
    """A fallback for every row of `caps` except one, which has no Mietenstufe."""
    return pd.DataFrame(
        {
            "ags": ["01001000", "01001000", "01002000", "01002000"],
            "household_size": [1, 2, 1, 2],
            "wohngeld_fallback_cap": [400.0, 500.0, 500.0, None],
            "wohngeld_rule_suspected": [False, False, True, True],
        },
    )


@pytest.fixture
def gemeinden() -> pd.DataFrame:
    """Both Gemeinden, in the same Kreis and Bundesland."""
    return pd.DataFrame(
        {
            "ags": ["01001000", "01002000"],
            "district_ags": ["01001", "01001"],
            "state_code": ["01", "01"],
        },
    )


def test_build_cap_comparison_reports_the_ratio_of_cap_to_fallback(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
) -> None:
    """A 500 € cap against a 400 € fallback is a ratio of 1.25."""
    frame = build_cap_comparison(caps, fallback, gemeinden)
    row = frame.query("ags == '01001000' and household_size == 1").iloc[0]
    assert row["cap_ratio"] == pytest.approx(1.25)


def test_build_cap_comparison_reports_the_euro_difference(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
) -> None:
    """A 500 € cap against a 400 € fallback is 100 € above it."""
    frame = build_cap_comparison(caps, fallback, gemeinden)
    row = frame.query("ags == '01001000' and household_size == 1").iloc[0]
    assert row["cap_difference_eur"] == pytest.approx(100.0)


def test_build_cap_comparison_reports_the_log_ratio(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
) -> None:
    """The log ratio of 1.25 is 0.22314355."""
    frame = build_cap_comparison(caps, fallback, gemeinden)
    row = frame.query("ags == '01001000' and household_size == 1").iloc[0]
    assert float(row["log_cap_ratio"]) == pytest.approx(np.log(1.25))


def test_build_cap_comparison_leaves_the_ratio_missing_without_a_fallback(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
) -> None:
    """A Gemeinde without a Mietenstufe has no benchmark and so no ratio."""
    frame = build_cap_comparison(caps, fallback, gemeinden)
    row = frame.query("ags == '01002000' and household_size == 2").iloc[0]
    assert pd.isna(row["cap_ratio"])


def test_cap_ratio_spread_is_the_largest_minus_the_smallest_ratio() -> None:
    """Ratios of 1.00, 1.05, 0.98 and 1.02 span 0.07 ratio points."""
    frame = pd.DataFrame(
        {
            "ags": ["01001000"] * 4,
            "household_size": [1, 2, 3, 4],
            "cap_ratio": [1.00, 1.05, 0.98, 1.02],
            "wohngeld_rule_suspected": [False] * 4,
        },
    )
    spread = cap_ratio_spread_across_household_sizes(frame)
    assert spread.loc[0, "cap_ratio_spread"] == pytest.approx(0.07)


def test_cap_ratio_spread_omits_a_gemeinde_missing_a_household_size() -> None:
    """A spread over a subset of sizes is not comparable, so the Gemeinde drops out."""
    frame = pd.DataFrame(
        {
            "ags": ["01001000"] * 3,
            "household_size": [1, 2, 3],
            "cap_ratio": [1.00, 1.05, 0.98],
            "wohngeld_rule_suspected": [False] * 3,
        },
    )
    assert cap_ratio_spread_across_household_sizes(frame).empty


def test_bedarfsgemeinschaft_weights_add_up_the_jobcenter_serving_one_kreis() -> None:
    """Berlin's two Jobcenter contribute one Kreis-level stock of 18,604."""
    statistik = pd.DataFrame(
        {
            "jobcenter_id": ["t92202", "t92204"],
            "district_ags": ["11000", "11000"],
            "household_size": [1, 1],
            "bedarfsgemeinschaften": [11537.0, 7067.0],
        },
    )
    weights = bedarfsgemeinschaft_weights(statistik)
    assert weights.loc[0, "bedarfsgemeinschaften"] == pytest.approx(18604.0)


def test_attach_weights_gives_zero_weight_to_an_unreported_kreis(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
) -> None:
    """A Kreis the Bundesagentur does not report leaves that scheme, not the other."""
    frame = build_cap_comparison(caps, fallback, gemeinden)
    empty = pd.DataFrame(
        {
            "district_ags": pd.Series([], dtype="object"),
            "household_size": pd.Series([], dtype="int64"),
            "bedarfsgemeinschaften": pd.Series([], dtype="float64"),
        },
    )
    weighted = attach_weights(frame, empty)
    assert weighted[WeightingScheme.BEDARFSGEMEINSCHAFT.value].eq(0.0).all()


def test_stack_populations_repeats_only_the_unsuspected_rows(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
) -> None:
    """Two of four rows are suspected, so the second population holds two rows."""
    frame = build_cap_comparison(caps, fallback, gemeinden)
    stacked = stack_populations(frame)
    retained = stacked.loc[
        stacked["population"] == AnalysisPopulation.EXCLUDING_SUSPECTED_FALLBACK.value
    ]
    assert len(retained) == 2
