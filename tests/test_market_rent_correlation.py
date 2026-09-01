"""Tests for the correlation of each cap with the local market rent."""

import numpy as np
import pandas as pd
import pytest

from kdu.market_rent_comparison.market_rent_correlation import (
    GRENZE_OHNE_SCHLUESSIGES_KONZEPT_SHORT,
    PRESENTATION_BASE_FONT_SIZE,
    CapKind,
    Comparison,
    _deviation_from_group_mean,
    _pearson_correlation,
    build_analysis_frame,
    correlation_table,
    market_rent_correlation_figure,
)


def _frame(
    rents: list[float],
    mietenstufen: list[int],
    household_sizes: tuple[int, ...] = (1,),
) -> tuple[pd.DataFrame, ...]:
    """Return caps, fallback and rents for Gemeinden with the given rent levels."""
    n = len(rents)
    ags = [f"0100{index:04d}" for index in range(n)]
    repeated_ags = [value for _ in household_sizes for value in ags]
    repeated_sizes = [size for size in household_sizes for _ in ags]
    repeated_rents = [rent for _ in household_sizes for rent in rents]
    repeated_stufen = [stufe for _ in household_sizes for stufe in mietenstufen]
    kdu_caps = pd.DataFrame(
        {
            "ags": repeated_ags,
            "household_size": repeated_sizes,
            # The cap is a fixed multiple of the market rent, so the two are
            # perfectly correlated in logarithms.
            "kdu_cap": [
                rent * 100.0 * size
                for rent, size in zip(repeated_rents, repeated_sizes, strict=True)
            ],
            "max_area_sqm": [50.0] * len(repeated_ags),
        },
    )
    wohngeld_fallback = pd.DataFrame(
        {
            "ags": repeated_ags,
            "household_size": repeated_sizes,
            "mietenstufe": repeated_stufen,
            "wohngeld_fallback_cap": [
                (300.0 + 50.0 * stufe) * size
                for stufe, size in zip(repeated_stufen, repeated_sizes, strict=True)
            ],
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


@pytest.mark.parametrize("position", [0, 1])
def test_pearson_correlation_is_nan_when_one_series_does_not_vary(
    position: int,
) -> None:
    """A constant series leaves the correlation undefined, whichever side it is on."""
    series = [np.array([2.0, 2.0, 2.0]), np.array([1.0, 5.0, 9.0])]
    assert np.isnan(_pearson_correlation(series[position], series[1 - position]))


def test_pearson_correlation_is_nan_when_one_series_varies_only_by_rounding() -> None:
    """Residuals of the size of floating-point rounding are not a measurable series."""
    dust = np.array([1.0, -1.0, 0.0]) * 1e-16
    assert np.isnan(_pearson_correlation(dust, np.array([1.0, 5.0, 9.0])))


def test_pearson_correlation_of_the_rounding_witness_is_not_exactly_constant() -> None:
    """The rounding witness really does have a non-zero standard deviation."""
    dust = np.array([1.0, -1.0, 0.0]) * 1e-16
    assert np.std(dust) > 0.0


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


def _fallback_within_mietenstufe(table: pd.DataFrame) -> pd.DataFrame:
    """Return the rows comparing the fallback to market rents within a Mietenstufe."""
    return table.loc[
        (table["cap"] == CapKind.FALLBACK)
        & (table["comparison"] == Comparison.WITHIN_MIETENSTUFE)
    ]


def _table_over_all_household_sizes() -> pd.DataFrame:
    """Return the correlation table for four Gemeinden at five household sizes."""
    kdu_caps, wohngeld_fallback, zensus_rents = _frame(
        [5.0, 6.0, 7.0, 9.0],
        [1, 1, 2, 2],
        household_sizes=(1, 2, 3, 4, 5),
    )
    return correlation_table(
        build_analysis_frame(kdu_caps, wohngeld_fallback, zensus_rents),
    )


def test_correlation_table_reports_no_correlation_within_mietenstufe_for_fallback() -> (
    None
):
    """The fallback cannot vary within a Mietenstufe, so no correlation is defined."""
    within = _fallback_within_mietenstufe(_table_over_all_household_sizes())

    assert np.isnan(within["correlation"].to_numpy(dtype=float)).all()


def test_correlation_table_flags_the_fallback_as_constant_at_every_household_size() -> (
    None
):
    """Every household size carries the flag, not only the single-person household."""
    within = _fallback_within_mietenstufe(_table_over_all_household_sizes())

    assert within["constant_within_comparison"].to_numpy().tolist() == [True] * 5


def test_correlation_table_reports_a_finite_correlation_for_the_local_cap_within() -> (
    None
):
    """The local cap varies within a Mietenstufe, so its correlation is a number."""
    table = _table_over_all_household_sizes()
    within = table.loc[
        (table["cap"] == CapKind.LOCAL)
        & (table["comparison"] == Comparison.WITHIN_MIETENSTUFE)
    ]

    assert np.isfinite(within["correlation"].to_numpy(dtype=float)).all()


def test_only_the_fallback_within_mietenstufe_is_marked_constant() -> None:
    """The local cap is free to vary within a Mietenstufe, so its value is measured."""
    table = _table_over_all_household_sizes()

    assert table.loc[table["constant_within_comparison"], "cap"].unique().tolist() == [
        CapKind.FALLBACK,
    ]


def test_market_rent_correlation_figure_labels_the_constant_bar_without_nan() -> None:
    """No trace text renders the string "nan" where the correlation is undefined."""
    figure = market_rent_correlation_figure(_table_over_all_household_sizes())

    texts = [text for trace in figure.data for text in trace.text]

    assert not any("nan" in text.lower() for text in texts)


def test_market_rent_correlation_figure_draws_no_bar_for_the_constant_comparison() -> (
    None
):
    """The fallback's within-Mietenstufe bar is absent rather than drawn at zero."""
    figure = market_rent_correlation_figure(_table_over_all_household_sizes())

    fallback = next(
        trace for trace in figure.data if trace.name == CapKind.FALLBACK.label
    )

    assert list(fallback.x) == [Comparison.OVERALL.label]


def test_market_rent_correlation_figure_annotates_the_constant_comparison() -> None:
    """An annotation states that the fallback cannot be measured in that space."""
    figure = market_rent_correlation_figure(_table_over_all_household_sizes())

    texts = [annotation.text for annotation in figure.layout.annotations]

    assert any("n/a" in text for text in texts)


def test_market_rent_correlation_figure_sets_the_annotation_clear_of_the_bar() -> None:
    """The note sits above the bar beside it rather than across its face."""
    table = _table_over_all_household_sizes()
    figure = market_rent_correlation_figure(table)

    local_within = table.loc[
        table["household_size"].eq(1)
        & table["comparison"].eq(Comparison.WITHIN_MIETENSTUFE)
        & ~table["constant_within_comparison"]
    ]
    drawn = float(local_within["correlation"].max())

    assert figure.layout.annotations[0].y > drawn


def test_cap_kind_fallback_is_labelled_grenze_ohne_schluessiges_konzept() -> None:
    """The statutory construction is named by its legal term, not as a benchmark."""
    assert CapKind.FALLBACK.label == GRENZE_OHNE_SCHLUESSIGES_KONZEPT_SHORT


def test_market_rent_correlation_figure_carries_no_in_figure_title() -> None:
    """The slide supplies the heading, so the figure draws none."""
    figure = market_rent_correlation_figure(_table_over_all_household_sizes())

    assert figure.layout.title.text is None


def test_market_rent_correlation_figure_sets_a_projector_legible_base_font() -> None:
    """The base font is large enough to read at 1600 by 900 pixels."""
    figure = market_rent_correlation_figure(_table_over_all_household_sizes())

    assert figure.layout.font.size >= PRESENTATION_BASE_FONT_SIZE


def test_market_rent_correlation_figure_names_no_trace_a_benchmark() -> None:
    """No legend entry calls the statutory construction a benchmark."""
    figure = market_rent_correlation_figure(_table_over_all_household_sizes())

    assert not any("benchmark" in trace.name.lower() for trace in figure.data)
