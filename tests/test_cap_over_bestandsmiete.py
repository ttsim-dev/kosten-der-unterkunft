"""Tests for the local cap read against its own Gemeinde's Bestandsmiete."""

import numpy as np
import pandas as pd
import pytest

from kdu.market_rent_comparison.cap_over_bestandsmiete import (
    RATIO_COLUMN,
    REFERENCE_RATIO,
    X_AXIS_TITLE,
    Y_AXIS_TITLE,
    build_cap_over_bestandsmiete,
    cap_over_bestandsmiete_figure,
    summarise_cap_over_bestandsmiete,
)


def _gemeinde_shares(**thresholds: float) -> pd.DataFrame:
    """Return one household-size-one row per Gemeinde, keyed by its AGS."""
    return pd.DataFrame(
        {
            "ags": list(thresholds),
            "household_size": [1] * len(thresholds),
            "threshold_local_kdu_cap_eur_per_sqm": list(thresholds.values()),
        },
    )


def _zensus_rents(**means: float) -> pd.DataFrame:
    """Return the mean Nettokaltmiete per square metre of each Gemeinde."""
    return pd.DataFrame(
        {
            "ags": list(means),
            "nettokaltmiete_eur_per_sqm_mean": list(means.values()),
        },
    )


def test_build_cap_over_bestandsmiete_divides_the_cap_by_the_mean_rent() -> None:
    """A cap of 7.50 against a mean Bestandsmiete of 6.00 is a ratio of 1.25."""
    frame = build_cap_over_bestandsmiete(
        _gemeinde_shares(a=7.50),
        _zensus_rents(a=6.00),
    )
    np.testing.assert_allclose(frame[RATIO_COLUMN], [1.25], atol=1e-12)


def test_build_cap_over_bestandsmiete_excludes_a_gemeinde_with_a_zero_mean_rent() -> (
    None
):
    """A Gemeinde whose suppressed rent reads as zero is dropped, not divided by."""
    frame = build_cap_over_bestandsmiete(
        _gemeinde_shares(a=7.50, b=7.50),
        _zensus_rents(a=6.00, b=0.0),
    )
    assert frame["ags"].tolist() == ["a"]


def test_build_cap_over_bestandsmiete_never_returns_a_non_finite_ratio() -> None:
    """No ratio is infinite, whatever the Zensus reports as a mean rent."""
    frame = build_cap_over_bestandsmiete(
        _gemeinde_shares(a=7.50, b=7.50, c=7.50),
        _zensus_rents(a=6.00, b=0.0, c=float("nan")),
    )
    assert np.isfinite(frame[RATIO_COLUMN]).all()


def test_build_cap_over_bestandsmiete_excludes_a_gemeinde_without_a_cap() -> None:
    """A Gemeinde whose cap states no Wohnfläche has no ratio to report."""
    frame = build_cap_over_bestandsmiete(
        _gemeinde_shares(a=7.50, b=float("nan")),
        _zensus_rents(a=6.00, b=6.00),
    )
    assert frame["ags"].tolist() == ["a"]


def test_summarise_cap_over_bestandsmiete_counts_the_gemeinden_per_household_size() -> (
    None
):
    """Every Gemeinde with a ratio at a household size is counted once."""
    frame = build_cap_over_bestandsmiete(
        _gemeinde_shares(a=7.50, b=6.00),
        _zensus_rents(a=6.00, b=6.00),
    )
    summary = summarise_cap_over_bestandsmiete(frame)
    assert summary["n_gemeinden"].tolist() == [2]


def test_summarise_cap_over_bestandsmiete_reports_the_share_below_the_reference() -> (
    None
):
    """One Gemeinde in four whose cap falls short of its own mean rent is 0.25."""
    frame = build_cap_over_bestandsmiete(
        _gemeinde_shares(a=7.50, b=6.60, c=6.00, d=5.40),
        _zensus_rents(a=6.00, b=6.00, c=6.00, d=6.00),
    )
    summary = summarise_cap_over_bestandsmiete(frame)
    np.testing.assert_allclose(summary["share_below_one"], [0.25], atol=1e-12)


def test_summarise_cap_over_bestandsmiete_reports_the_median_ratio() -> None:
    """The median of the ratios 1.25 and 0.75 is 1.0."""
    frame = build_cap_over_bestandsmiete(
        _gemeinde_shares(a=7.50, b=4.50),
        _zensus_rents(a=6.00, b=6.00),
    )
    summary = summarise_cap_over_bestandsmiete(frame)
    np.testing.assert_allclose(summary["median"], [1.0], atol=1e-12)


def test_cap_over_bestandsmiete_figure_labels_the_horizontal_axis_in_german() -> None:
    """The horizontal axis names the Bestandsmiete and its Zensus vintage."""
    figure = cap_over_bestandsmiete_figure(
        build_cap_over_bestandsmiete(_gemeinde_shares(a=7.50), _zensus_rents(a=6.00)),
    )
    assert figure.layout.xaxis.title.text == X_AXIS_TITLE


def test_cap_over_bestandsmiete_figure_labels_the_vertical_axis_as_unweighted() -> None:
    """The vertical axis says that every Gemeinde counts once."""
    figure = cap_over_bestandsmiete_figure(
        build_cap_over_bestandsmiete(_gemeinde_shares(a=7.50), _zensus_rents(a=6.00)),
    )
    assert figure.layout.yaxis.title.text == Y_AXIS_TITLE


def test_cap_over_bestandsmiete_figure_draws_a_dashed_line_at_the_reference() -> None:
    """A dashed rule marks the ratio at which cap and mean rent coincide."""
    figure = cap_over_bestandsmiete_figure(
        build_cap_over_bestandsmiete(_gemeinde_shares(a=7.50), _zensus_rents(a=6.00)),
    )
    lines = [shape for shape in figure.layout.shapes if shape.type == "line"]
    assert [(line.x0, line.line.dash) for line in lines] == [
        (REFERENCE_RATIO, "dash"),
    ]


def test_cap_over_bestandsmiete_figure_sets_an_explicit_bin_width() -> None:
    """Bin edges are stated, so Plotly does not round them to its own width."""
    figure = cap_over_bestandsmiete_figure(
        build_cap_over_bestandsmiete(_gemeinde_shares(a=7.50), _zensus_rents(a=6.00)),
    )
    assert figure.data[0].xbins.size is not None


@pytest.mark.parametrize("ratio", [0.4, 3.2])
def test_cap_over_bestandsmiete_figure_bins_span_the_observed_ratios(
    ratio: float,
) -> None:
    """No Gemeinde falls outside the bins, so no bar is silently dropped."""
    figure = cap_over_bestandsmiete_figure(
        build_cap_over_bestandsmiete(
            _gemeinde_shares(a=6.00 * ratio),
            _zensus_rents(a=6.00),
        ),
    )
    bins = figure.data[0].xbins
    assert bins.start <= ratio <= bins.end
