"""Tests for the correlation of each cap with the local market rent."""

import numpy as np
import pandas as pd

from kdu.market_rent_comparison.market_rent_correlation import (
    CapKind,
    Comparison,
    _deviation_from_group_mean,
    _pearson_correlation,
    build_analysis_frame,
    correlation_table,
)


def _frame(rents: list[float], mietenstufen: list[int]) -> tuple[pd.DataFrame, ...]:
    """Return caps, fallback and rents for Gemeinden with the given rent levels."""
    n = len(rents)
    ags = [f"0100{index:04d}" for index in range(n)]
    kdu_caps = pd.DataFrame(
        {
            "ags": ags,
            "household_size": [1] * n,
            # The cap is a fixed multiple of the market rent, so the two are
            # perfectly correlated in logarithms.
            "kdu_cap": [rent * 100.0 for rent in rents],
            "max_area_sqm": [50.0] * n,
        },
    )
    wohngeld_fallback = pd.DataFrame(
        {
            "ags": ags,
            "household_size": [1] * n,
            "mietenstufe": mietenstufen,
            "wohngeld_fallback_cap": [300.0 + 50.0 * stufe for stufe in mietenstufen],
        },
    )
    zensus_rents = pd.DataFrame(
        {"ags": ags, "nettokaltmiete_eur_per_sqm_mean": rents},
    )
    return kdu_caps, wohngeld_fallback, zensus_rents


def test_deviation_from_group_mean_subtracts_the_mean_of_each_group() -> None:
    """Values are centred within their own group, not across all groups."""
    deviations = _deviation_from_group_mean(
        np.array([1.0, 3.0, 10.0, 20.0]),
        np.array([1, 1, 2, 2]),
    )
    np.testing.assert_allclose(deviations, [-1.0, 1.0, -5.0, 5.0], atol=1e-12)


def test_pearson_correlation_is_one_for_an_exact_increasing_relation() -> None:
    """A series and a positive multiple of it correlate perfectly."""
    values = np.array([1.0, 2.0, 3.0, 4.0])
    assert _pearson_correlation(values, 3.0 * values) == 1.0


def test_pearson_correlation_is_zero_when_one_series_does_not_vary() -> None:
    """A constant series carries no information, so the correlation is zero."""
    assert (
        _pearson_correlation(np.array([2.0, 2.0, 2.0]), np.array([1.0, 5.0, 9.0]))
        == 0.0
    )


def test_build_analysis_frame_drops_gemeinden_without_a_measured_rent() -> None:
    """A Gemeinde with no positive Zensus rent cannot enter the correlation."""
    kdu_caps, wohngeld_fallback, zensus_rents = _frame([6.0, 8.0], [2, 4])
    zensus_rents.loc[1, "nettokaltmiete_eur_per_sqm_mean"] = 0.0

    frame = build_analysis_frame(kdu_caps, wohngeld_fallback, zensus_rents)

    assert frame["ags"].tolist() == ["01000000"]


def test_correlation_table_reports_a_perfect_correlation_for_a_proportional_cap() -> (
    None
):
    """A local cap set as a fixed multiple of the market rent correlates perfectly."""
    kdu_caps, wohngeld_fallback, zensus_rents = _frame(
        [5.0, 6.0, 7.0, 9.0],
        [1, 1, 2, 2],
    )

    table = correlation_table(
        build_analysis_frame(kdu_caps, wohngeld_fallback, zensus_rents),
    )
    overall = table.loc[
        (table["cap"] == CapKind.LOCAL) & (table["comparison"] == Comparison.OVERALL)
    ]

    np.testing.assert_allclose(overall["correlation"].to_numpy(), [1.0], atol=1e-12)


def test_correlation_table_reports_zero_within_mietenstufe_for_the_fallback() -> None:
    """The fallback is a step function of the Mietenstufe, so it cannot vary there."""
    kdu_caps, wohngeld_fallback, zensus_rents = _frame(
        [5.0, 6.0, 7.0, 9.0],
        [1, 1, 2, 2],
    )

    table = correlation_table(
        build_analysis_frame(kdu_caps, wohngeld_fallback, zensus_rents),
    )
    within = table.loc[
        (table["cap"] == CapKind.FALLBACK)
        & (table["comparison"] == Comparison.WITHIN_MIETENSTUFE)
    ]

    assert within["correlation"].to_numpy().tolist() == [0.0]
    assert within["mechanically_zero"].to_numpy().tolist() == [True]


def test_only_the_fallback_within_mietenstufe_is_marked_mechanical() -> None:
    """The local cap is free to vary within a Mietenstufe, so its zero would be real."""
    kdu_caps, wohngeld_fallback, zensus_rents = _frame(
        [5.0, 6.0, 7.0, 9.0], [1, 1, 2, 2]
    )

    table = correlation_table(
        build_analysis_frame(kdu_caps, wohngeld_fallback, zensus_rents),
    )

    assert table.loc[table["mechanically_zero"], "cap"].unique().tolist() == [
        CapKind.FALLBACK,
    ]
