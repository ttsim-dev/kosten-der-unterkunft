"""Tests for the variation in local KdU caps the Mietenstufe leaves unaccounted for."""

import numpy as np
import pandas as pd
import pytest

from kdu.kdu_vs_wohngeld.mietenstufe_dispersion import (
    degrees_of_freedom_adjusted_share,
    dispersion_within_mietenstufe,
    plot_mietenstufe_dispersion,
    variance_share_between_groups,
    variance_shares,
)

# The decomposition as it stands on the collected caps at household size one:
# the classification, the number of groups it distinguishes, the unadjusted
# between-group variance share, and the degrees-of-freedom adjusted share
# computed independently of this code.
N_GEMEINDEN_IN_DECOMPOSITION = 9397
REPORTED_DECOMPOSITION = (
    ("mietenstufe", 7, 0.4102229427397104, 0.4098),
    ("bundesland", 16, 0.4569447108792929, 0.4561),
    ("mietenstufe_and_bundesland", 69, 0.7385401070501563, 0.7366),
    ("kreis", 358, 0.9188074916766683, 0.9156),
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


@pytest.mark.parametrize(
    ("n_groups", "share", "expected_adjusted"),
    [(entry[1], entry[2], entry[3]) for entry in REPORTED_DECOMPOSITION],
    ids=[entry[0] for entry in REPORTED_DECOMPOSITION],
)
def test_adjusted_share_matches_the_independently_computed_value(
    n_groups: int,
    share: float,
    expected_adjusted: float,
) -> None:
    """The adjusted share rescales the unaccounted-for share by the lost degrees."""
    np.testing.assert_allclose(
        degrees_of_freedom_adjusted_share(
            share,
            n_observations=N_GEMEINDEN_IN_DECOMPOSITION,
            n_groups=n_groups,
        ),
        expected_adjusted,
        atol=5e-5,
    )


@pytest.mark.parametrize(
    ("n_groups", "share"),
    [(entry[1], entry[2]) for entry in REPORTED_DECOMPOSITION],
    ids=[entry[0] for entry in REPORTED_DECOMPOSITION],
)
def test_adjusted_share_never_exceeds_the_unadjusted_share(
    n_groups: int,
    share: float,
) -> None:
    """Charging a classification for the groups it spends can only lower its share."""
    assert (
        degrees_of_freedom_adjusted_share(
            share,
            n_observations=N_GEMEINDEN_IN_DECOMPOSITION,
            n_groups=n_groups,
        )
        <= share
    )


def test_variance_shares_reports_a_finite_adjusted_share_for_every_classification() -> (
    None
):
    """Every classification row carries an adjusted share rather than a missing one."""
    shares = variance_shares(_four_gemeinden())
    assert bool(np.isfinite(shares["variance_share_adjusted"]).all())


def test_dispersion_rows_carry_no_adjusted_share_in_the_combined_table() -> None:
    """The adjusted share is undefined for the per-Mietenstufe dispersion rows."""
    frame = _four_gemeinden()
    combined = pd.concat(
        [
            dispersion_within_mietenstufe(frame).assign(
                measure="dispersion_within_mietenstufe",
            ),
            variance_shares(frame).assign(measure="variance_share_between_groups"),
        ],
        ignore_index=True,
    )
    dispersion_rows = combined.query("measure == 'dispersion_within_mietenstufe'")
    assert dispersion_rows["variance_share_adjusted"].isna().all()


def test_four_gemeinden_fixture_has_variance_to_decompose() -> None:
    """The synthetic frame the adjusted-share tests read varies in the local cap."""
    assert _four_gemeinden()["kdu_cap"].nunique() == 4


def _four_gemeinden() -> pd.DataFrame:
    """Return four Gemeinden spread over two Mietenstufen and two Kreise."""
    return pd.DataFrame(
        {
            "ags": ["01", "02", "03", "04"],
            "household_size": [1, 1, 1, 1],
            "kdu_cap": [400.0, 420.0, 500.0, 520.0],
            "wohngeld_fallback_cap": [430.0, 430.0, 510.0, 510.0],
            "mietenstufe": [1, 1, 2, 2],
            "state_code": ["01", "01", "01", "01"],
            "district_ags": ["011", "011", "012", "012"],
        },
    )


def _one_mietenstufe(caps: list[float]) -> pd.DataFrame:
    """Return Gemeinden that all share Mietenstufe 1, Bundesland and Kreis."""
    return pd.DataFrame(
        {
            "ags": [f"{index:08d}" for index in range(len(caps))],
            "household_size": [1] * len(caps),
            "kdu_cap": caps,
            "wohngeld_fallback_cap": [500.0] * len(caps),
            "mietenstufe": [1] * len(caps),
            "state_code": ["01"] * len(caps),
            "district_ags": ["01001"] * len(caps),
        },
    )


def test_plot_mietenstufe_dispersion_names_the_classification_on_the_axis() -> None:
    """The horizontal axis names the statutory class each box stands for."""
    figure = plot_mietenstufe_dispersion(_four_gemeinden())
    assert figure.layout.xaxis.title.text == "Mietstufe"


def test_plot_mietenstufe_dispersion_names_the_estimand_and_unit_on_the_axis() -> None:
    """The vertical axis states what is drawn and in which unit."""
    figure = plot_mietenstufe_dispersion(_four_gemeinden())
    assert figure.layout.yaxis.title.text == "KdU cap, Euro per month"


def test_plot_mietenstufe_dispersion_marks_the_grenze_in_every_box() -> None:
    """Each class carries the one Grenze ohne schlüssiges Konzept it is measured by."""
    figure = plot_mietenstufe_dispersion(_four_gemeinden())
    markers = [trace for trace in figure.data if trace.type == "scatter"]
    assert [tuple(trace.y) for trace in markers] == [(430.0, 510.0)]


def test_plot_mietenstufe_dispersion_rejects_two_grenzen_in_one_mietenstufe() -> None:
    """The Grenze is one value per class, so two of them means the frame is wrong."""
    frame = _four_gemeinden().assign(
        wohngeld_fallback_cap=[430.0, 440.0, 510.0, 510.0],
    )
    with pytest.raises(ValueError, match="Mietenstufe 1"):
        plot_mietenstufe_dispersion(frame)
