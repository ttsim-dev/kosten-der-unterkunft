"""Tests for how far local KdU caps depart from the Grenze ohne schlüssiges Konzept."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from kdu.config import WeightingScheme, catalog_path
from kdu.kdu_vs_wohngeld.cap_comparison import (
    allocate_bedarfsgemeinschaften_to_gemeinden,
    attach_weights,
    bedarfsgemeinschaft_weights,
    build_cap_comparison,
    cap_ratio_pairs_across_household_sizes,
    cap_ratio_spread_across_household_sizes,
    count_gemeinden_at_benchmark,
    plot_cap_difference_distribution,
    plot_cap_ratio_by_household_size,
    share_with_sign_flip,
    summarise_cap_difference_eur,
)
from kdu.weighting import weighted_mean


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
            "population": [75, 25],
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
    """No Mietenstufe means no Grenze ohne schlüssiges Konzept and so no ratio."""
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
    allocated = allocate_bedarfsgemeinschaften_to_gemeinden(empty, gemeinden)
    weighted = attach_weights(frame, allocated)
    scheme = WeightingScheme.BEDARFSGEMEINSCHAFT_ALLOCATED_BY_POPULATION.value
    assert weighted[scheme].eq(0.0).all()


def _kreis_stock() -> pd.DataFrame:
    """One Kreis reported at household sizes one and two."""
    return pd.DataFrame(
        {
            "district_ags": ["01001", "01001"],
            "household_size": [1, 2],
            "bedarfsgemeinschaften": [1000.0, 400.0],
        },
    )


def test_allocated_weights_sum_back_to_the_kreis_stock_per_household_size(
    gemeinden: pd.DataFrame,
) -> None:
    """Allocation moves the Kreis stock across Gemeinden without creating any."""
    allocated = allocate_bedarfsgemeinschaften_to_gemeinden(_kreis_stock(), gemeinden)
    scheme = WeightingScheme.BEDARFSGEMEINSCHAFT_ALLOCATED_BY_POPULATION.value
    total = allocated.query("household_size == 1")[scheme].sum()
    assert total == pytest.approx(1000.0)


def test_allocated_weights_split_the_stock_in_proportion_to_population(
    gemeinden: pd.DataFrame,
) -> None:
    """Populations of 75 and 25 take 750 and 250 of a stock of 1,000."""
    allocated = allocate_bedarfsgemeinschaften_to_gemeinden(_kreis_stock(), gemeinden)
    scheme = WeightingScheme.BEDARFSGEMEINSCHAFT_ALLOCATED_BY_POPULATION.value
    row = allocated.query("ags == '01001000' and household_size == 1").iloc[0]
    assert row[scheme] == pytest.approx(750.0)


def test_allocation_denominator_covers_gemeinden_without_a_cap(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
) -> None:
    """A Gemeinde whose cap is unknown keeps its share instead of ceding it."""
    caps_with_one_gap = caps.assign(
        kdu_cap=caps["kdu_cap"].where(caps["ags"] != "01002000"),
    )
    frame = build_cap_comparison(caps_with_one_gap, fallback, gemeinden)
    allocated = allocate_bedarfsgemeinschaften_to_gemeinden(_kreis_stock(), gemeinden)
    weighted = attach_weights(frame, allocated)
    scheme = WeightingScheme.BEDARFSGEMEINSCHAFT_ALLOCATED_BY_POPULATION.value
    covered = weighted.query("ags == '01001000' and household_size == 1").iloc[0]
    assert covered[scheme] == pytest.approx(750.0)


def test_allocated_national_total_does_not_exceed_the_reported_stock() -> None:
    """A Kreis the Gemeinde table omits contributes nothing rather than more."""
    stock = pd.DataFrame(
        {
            "district_ags": ["01001", "09999"],
            "household_size": [1, 1],
            "bedarfsgemeinschaften": [1000.0, 500.0],
        },
    )
    gemeinden = pd.DataFrame(
        {
            "ags": ["01001000", "01002000"],
            "district_ags": ["01001", "01001"],
            "population": [75, 25],
        },
    )
    allocated = allocate_bedarfsgemeinschaften_to_gemeinden(stock, gemeinden)
    scheme = WeightingScheme.BEDARFSGEMEINSCHAFT_ALLOCATED_BY_POPULATION.value
    assert allocated[scheme].sum() <= 1500.0


def test_summarise_cap_difference_eur_reports_the_weighted_median(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
) -> None:
    """Differences of +100 € and -100 € have an unweighted median of zero."""
    frame = build_cap_comparison(caps, fallback, gemeinden)
    allocated = allocate_bedarfsgemeinschaften_to_gemeinden(_kreis_stock(), gemeinden)
    weighted = attach_weights(frame, allocated)
    table = summarise_cap_difference_eur(weighted)
    row = table.query(
        "household_size == 1"
        " and statistic == 'median'"
        " and weighting_scheme == 'gemeinde_unweighted'",
    ).iloc[0]
    assert row["measure"] == "cap_difference_eur"
    assert row["value"] == pytest.approx(0.0)


def test_summarise_cap_difference_eur_reports_every_decile(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
) -> None:
    """The euro summary carries p10 through p90 so the deciles need no hand work."""
    frame = build_cap_comparison(caps, fallback, gemeinden)
    allocated = allocate_bedarfsgemeinschaften_to_gemeinden(_kreis_stock(), gemeinden)
    weighted = attach_weights(frame, allocated)
    table = summarise_cap_difference_eur(weighted)
    expected = {f"p{decile}0" for decile in range(1, 10)}
    assert expected <= set(table["statistic"])


EXTREME_SCHEMES = (
    WeightingScheme.BEDARFSGEMEINSCHAFT_ALLOCATED_TO_LOWEST_DEPARTURE,
    WeightingScheme.BEDARFSGEMEINSCHAFT_ALLOCATED_TO_HIGHEST_DEPARTURE,
)


@pytest.mark.parametrize("scheme", EXTREME_SCHEMES)
def test_extreme_allocation_conserves_the_kreis_stock(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
    scheme: WeightingScheme,
) -> None:
    """The Kreis stock of 1,000 is moved within the Kreis, never created or lost."""
    frame = build_cap_comparison(caps, fallback, gemeinden)
    allocated = allocate_bedarfsgemeinschaften_to_gemeinden(_kreis_stock(), gemeinden)
    weighted = attach_weights(frame, allocated)
    total = weighted.query("household_size == 1")[scheme.value].sum()
    assert total == pytest.approx(1000.0)


def test_lowest_departure_allocation_picks_the_least_favourable_gemeinde(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
) -> None:
    """Of departures of +100 € and -100 €, the stock goes to the -100 € Gemeinde."""
    frame = build_cap_comparison(caps, fallback, gemeinden)
    allocated = allocate_bedarfsgemeinschaften_to_gemeinden(_kreis_stock(), gemeinden)
    weighted = attach_weights(frame, allocated)
    scheme = WeightingScheme.BEDARFSGEMEINSCHAFT_ALLOCATED_TO_LOWEST_DEPARTURE.value
    row = weighted.query("ags == '01002000' and household_size == 1").iloc[0]
    assert row[scheme] == pytest.approx(1000.0)


def test_highest_departure_allocation_picks_the_most_favourable_gemeinde(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
) -> None:
    """Of departures of +100 € and -100 €, the stock goes to the +100 € Gemeinde."""
    frame = build_cap_comparison(caps, fallback, gemeinden)
    allocated = allocate_bedarfsgemeinschaften_to_gemeinden(_kreis_stock(), gemeinden)
    weighted = attach_weights(frame, allocated)
    scheme = WeightingScheme.BEDARFSGEMEINSCHAFT_ALLOCATED_TO_HIGHEST_DEPARTURE.value
    row = weighted.query("ags == '01001000' and household_size == 1").iloc[0]
    assert row[scheme] == pytest.approx(1000.0)


def _tied_departure_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two Gemeinden of one Kreis whose departure is -100 € at household size one."""
    caps = pd.DataFrame(
        {
            "ags": ["01001000", "01002000"],
            "household_size": [1, 1],
            "kdu_cap": [500.0, 400.0],
        },
    )
    fallback = pd.DataFrame(
        {
            "ags": ["01001000", "01002000"],
            "household_size": [1, 1],
            "wohngeld_fallback_cap": [600.0, 500.0],
        },
    )
    return caps, fallback


@pytest.mark.parametrize("scheme", EXTREME_SCHEMES)
def test_extreme_allocation_splits_a_tied_kreis_equally(
    gemeinden: pd.DataFrame,
    scheme: WeightingScheme,
) -> None:
    """Two Gemeinden tied on the departure take 500 each out of a stock of 1,000."""
    caps, fallback = _tied_departure_frames()
    frame = build_cap_comparison(caps, fallback, gemeinden)
    allocated = allocate_bedarfsgemeinschaften_to_gemeinden(_kreis_stock(), gemeinden)
    weighted = attach_weights(frame, allocated)
    row = weighted.query("ags == '01001000' and household_size == 1").iloc[0]
    assert row[scheme.value] == pytest.approx(500.0)


@pytest.mark.parametrize("scheme", EXTREME_SCHEMES)
def test_extreme_allocation_leaves_a_kreis_without_any_cap_at_zero(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
    scheme: WeightingScheme,
) -> None:
    """No Gemeinde of the Kreis has a cap, so the stock reaches none of them."""
    without_caps = caps.assign(kdu_cap=float("nan"))
    frame = build_cap_comparison(without_caps, fallback, gemeinden)
    allocated = allocate_bedarfsgemeinschaften_to_gemeinden(_kreis_stock(), gemeinden)
    weighted = attach_weights(frame, allocated)
    assert weighted[scheme.value].eq(0.0).all()


def test_plot_cap_difference_distribution_draws_household_size_one_euro_differences(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
) -> None:
    """The trace carries the euro departures of household size one, not the ratios."""
    frame = build_cap_comparison(caps, fallback, gemeinden)
    figure = plot_cap_difference_distribution(frame)
    assert sorted(figure.data[0].x) == pytest.approx([-100.0, 100.0])


def test_plot_cap_difference_distribution_names_the_counted_unit_on_the_axis(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
) -> None:
    """The vertical axis states what is counted and under which weighting."""
    frame = build_cap_comparison(caps, fallback, gemeinden)
    figure = plot_cap_difference_distribution(frame)
    assert figure.layout.yaxis.title.text == "# Gemeinden (unweighted)"


def _difference_frame(differences: list[float]) -> pd.DataFrame:
    """One-person euro departures, one row per Gemeinde."""
    return pd.DataFrame(
        {
            "ags": [f"0100{index:04d}" for index in range(len(differences))],
            "household_size": [1] * len(differences),
            "cap_difference_eur": differences,
        },
    )


def _figure_with_deciles_away_from_zero() -> go.Figure:
    """A figure whose three deciles all fall left of the reference line."""
    return plot_cap_difference_distribution(
        _difference_frame([-90.0, -60.0, -40.0, -25.0, -10.0]),
    )


def test_plot_cap_difference_distribution_draws_three_decile_lines() -> None:
    """Only p10, p50 and p90 are drawn; nine dotted lines read as clutter."""
    figure = _figure_with_deciles_away_from_zero()
    assert sum(shape.line.dash == "dot" for shape in figure.layout.shapes) == 3


def test_plot_cap_difference_distribution_keeps_the_reference_line_dashed() -> None:
    """The zero reference line is dashed, so it never reads as a decile line."""
    figure = _figure_with_deciles_away_from_zero()
    benchmark = [shape for shape in figure.layout.shapes if shape.x0 == 0.0]
    assert [shape.line.dash for shape in benchmark] == ["dash"]


def test_plot_cap_difference_distribution_draws_the_reference_line_heavier() -> None:
    """The zero reference line is wider than the decile lines beside it."""
    figure = _figure_with_deciles_away_from_zero()
    widths = {shape.line.dash: shape.line.width for shape in figure.layout.shapes}
    assert widths["dash"] > widths["dot"]


@pytest.mark.parametrize(
    ("differences", "expected"),
    [
        ([10.0, -5.0, 3.0], 0),
        ([0.0, 10.0, -5.0], 1),
        ([0.0, 0.0, 0.0, 12.0], 3),
    ],
)
def test_count_gemeinden_at_benchmark_counts_the_gemeinden_with_no_departure(
    differences: list[float],
    expected: int,
) -> None:
    """A Gemeinde is on the Grenze ohne schlüssiges Konzept at a departure of zero."""
    point_mass = count_gemeinden_at_benchmark(_difference_frame(differences))
    assert point_mass.count == expected


def test_count_gemeinden_at_benchmark_reports_the_share_of_those_compared() -> None:
    """One of four Gemeinden on the Grenze ohne schlüssiges Konzept is 0.25."""
    point_mass = count_gemeinden_at_benchmark(
        _difference_frame([0.0, 10.0, -5.0, 3.0]),
    )
    assert point_mass.share == pytest.approx(0.25)


def test_count_gemeinden_at_benchmark_absorbs_the_residue_of_the_markup() -> None:
    """A departure of 1e-13 € is the product's rounding, not a departure."""
    point_mass = count_gemeinden_at_benchmark(_difference_frame([1.1e-13, 20.0]))
    assert point_mass.count == 1


def test_count_gemeinden_at_benchmark_keeps_a_departure_of_one_cent() -> None:
    """A cent is the resolution local caps are published at, so it counts as a gap."""
    point_mass = count_gemeinden_at_benchmark(_difference_frame([0.01, 20.0]))
    assert point_mass.count == 0


def test_count_gemeinden_at_benchmark_ignores_other_household_sizes() -> None:
    """The point mass is stated at household size one, which every Träger publishes."""
    frame = pd.DataFrame(
        {
            "ags": ["01001000", "01001000"],
            "household_size": [1, 2],
            "cap_difference_eur": [12.0, 0.0],
        },
    )
    assert count_gemeinden_at_benchmark(frame).count == 0


def test_plot_cap_difference_distribution_labels_only_the_three_deciles(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
) -> None:
    """The reference line at zero carries no label, so only p10, p50 and p90 do."""
    at_benchmark = caps.assign(kdu_cap=[400.0, 600.0, 400.0, 480.0])
    frame = build_cap_comparison(at_benchmark, fallback, gemeinden)
    figure = plot_cap_difference_distribution(frame)
    assert len(figure.layout.annotations) == 3


def test_plot_cap_difference_distribution_names_the_estimand_on_the_axis(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
) -> None:
    """The figure carries no title, so the axis states the estimand and its unit."""
    frame = build_cap_comparison(caps, fallback, gemeinden)
    figure = plot_cap_difference_distribution(frame)
    assert figure.layout.xaxis.title.text == (
        "Angemessene KdU minus Wohngeld-based Proxy, Euro per month"
    )


_BUILT_TABLES = tuple(
    catalog_path(name)
    for name in ("kdu_caps", "wohngeld_fallback", "gemeinden", "wohnkostenstatistik")
)

requires_built_data = pytest.mark.skipif(
    not all(path.exists() for path in _BUILT_TABLES),
    reason="the cleaned tables in bld/data are absent; run `pixi run pytask` first",
)


def _weighted_built_frame() -> pd.DataFrame:
    """The built comparison frame with every weighting scheme attached."""
    gemeinden = pd.read_parquet(catalog_path("gemeinden"))
    frame = build_cap_comparison(
        pd.read_parquet(catalog_path("kdu_caps")),
        pd.read_parquet(catalog_path("wohngeld_fallback")),
        gemeinden,
    )
    allocated = allocate_bedarfsgemeinschaften_to_gemeinden(
        bedarfsgemeinschaft_weights(
            pd.read_parquet(catalog_path("wohnkostenstatistik")),
        ),
        gemeinden,
    )
    return attach_weights(frame, allocated)


def _built_mean_at_household_size_one(scheme: WeightingScheme) -> float:
    """The mean euro departure at household size one under `scheme`."""
    weighted = _weighted_built_frame().query("household_size == 1")
    return weighted_mean(weighted["cap_difference_eur"], weighted[scheme.value])


@requires_built_data
def test_lowest_departure_allocation_bounds_the_population_allocation_from_below() -> (
    None
):
    """Placing every claimant at the lowest departure cannot raise the mean."""
    lowest = _built_mean_at_household_size_one(
        WeightingScheme.BEDARFSGEMEINSCHAFT_ALLOCATED_TO_LOWEST_DEPARTURE,
    )
    by_population = _built_mean_at_household_size_one(
        WeightingScheme.BEDARFSGEMEINSCHAFT_ALLOCATED_BY_POPULATION,
    )
    assert lowest < by_population


@requires_built_data
def test_highest_departure_allocation_bounds_the_population_allocation_from_above() -> (
    None
):
    """Placing every claimant at the highest departure cannot lower the mean."""
    highest = _built_mean_at_household_size_one(
        WeightingScheme.BEDARFSGEMEINSCHAFT_ALLOCATED_TO_HIGHEST_DEPARTURE,
    )
    by_population = _built_mean_at_household_size_one(
        WeightingScheme.BEDARFSGEMEINSCHAFT_ALLOCATED_BY_POPULATION,
    )
    assert highest > by_population


@requires_built_data
@pytest.mark.parametrize("scheme", EXTREME_SCHEMES)
def test_extreme_allocation_conserves_the_published_stock_of_every_covered_kreis(
    scheme: WeightingScheme,
) -> None:
    """Every Kreis holding at least one cap keeps its published one-person stock."""
    weighted = _weighted_built_frame().query("household_size == 1")
    published = bedarfsgemeinschaft_weights(
        pd.read_parquet(catalog_path("wohnkostenstatistik")),
    ).query("household_size == 1")
    covered = weighted.loc[weighted["cap_difference_eur"].notna(), "district_ags"]
    expected = published.loc[
        published["district_ags"].isin(set(covered)),
        "bedarfsgemeinschaften",
    ].sum()
    assert weighted[scheme.value].sum() == pytest.approx(expected)


def _ratio_frame(ratios: dict[str, dict[int, float]]) -> pd.DataFrame:
    """A comparison frame carrying `cap_ratio` per Gemeinde and household size."""
    rows = [
        {"ags": ags, "household_size": size, "cap_ratio": ratio}
        for ags, by_size in ratios.items()
        for size, ratio in by_size.items()
    ]
    return pd.DataFrame(rows)


def test_cap_ratio_pairs_carry_the_ratio_at_both_household_sizes() -> None:
    """A Gemeinde observed at sizes one and four contributes both of its ratios."""
    pairs = cap_ratio_pairs_across_household_sizes(
        _ratio_frame({"01001000": {1: 0.95, 2: 1.02, 4: 1.08}}),
    )
    assert pairs.loc[
        0, ["cap_ratio_single_adult", "cap_ratio_four_person"]
    ].to_list() == [
        pytest.approx(0.95),
        pytest.approx(1.08),
    ]


def test_cap_ratio_pairs_omit_a_gemeinde_without_a_four_person_ratio() -> None:
    """A point needs both coordinates, so a Gemeinde missing one drops out."""
    pairs = cap_ratio_pairs_across_household_sizes(
        _ratio_frame({"01001000": {1: 0.95, 2: 1.02}}),
    )
    assert pairs.empty


def test_share_with_sign_flip_counts_the_gemeinden_that_change_side() -> None:
    """One of four Gemeinden above the Grenze at one size and below at the other."""
    pairs = cap_ratio_pairs_across_household_sizes(
        _ratio_frame(
            {
                "01001000": {1: 0.95, 4: 1.08},
                "01002000": {1: 0.95, 4: 0.90},
                "01003000": {1: 1.05, 4: 1.10},
                "01004000": {1: 1.05, 4: 1.20},
            },
        ),
    )
    assert share_with_sign_flip(pairs) == pytest.approx(0.25)


def test_share_with_sign_flip_leaves_a_gemeinde_on_the_grenze_unflipped() -> None:
    """A cap equal to the Grenze at both sizes departs to neither side."""
    pairs = cap_ratio_pairs_across_household_sizes(
        _ratio_frame({"01001000": {1: 1.0, 4: 1.0}}),
    )
    assert share_with_sign_flip(pairs) == pytest.approx(0.0)


def _ratio_scatter() -> go.Figure:
    """The scatter drawn from four Gemeinden spread either side of the Grenze."""
    return plot_cap_ratio_by_household_size(
        cap_ratio_pairs_across_household_sizes(
            _ratio_frame(
                {
                    "01001000": {1: 0.95, 4: 1.08},
                    "01002000": {1: 0.95, 4: 0.90},
                    "01003000": {1: 1.05, 4: 1.10},
                    "01004000": {1: 1.15, 4: 1.20},
                },
            ),
        ),
    )


def test_plot_cap_ratio_by_household_size_names_the_horizontal_estimand() -> None:
    """The horizontal axis states the measure and the household size it is read at."""
    assert _ratio_scatter().layout.xaxis.title.text == (
        "Angemessene KdU ÷ Wohngeld-based Proxy, single adult"
    )


def test_plot_cap_ratio_by_household_size_names_the_vertical_estimand() -> None:
    """The vertical axis states the same measure at the four-person household."""
    assert _ratio_scatter().layout.yaxis.title.text == (
        "Angemessene KdU ÷ Wohngeld-based Proxy, four-person household"
    )


def test_plot_cap_ratio_by_household_size_draws_an_identity_line() -> None:
    """A Gemeinde whose ratio does not move with size sits on the drawn diagonal."""
    lines = [trace for trace in _ratio_scatter().data if trace.mode == "lines"]
    assert [tuple(line.x) == tuple(line.y) for line in lines] == [True]


def test_plot_cap_ratio_by_household_size_gives_both_axes_the_same_range() -> None:
    """Equal ranges make the diagonal the 45-degree line it is read as."""
    figure = _ratio_scatter()
    assert figure.layout.xaxis.range == figure.layout.yaxis.range


def test_plot_cap_ratio_by_household_size_leaves_the_scale_unanchored() -> None:
    """Anchoring the scales widens the drawn range beyond the one set here."""
    assert _ratio_scatter().layout.yaxis.scaleanchor is None


def test_plot_cap_ratio_by_household_size_rules_both_axes_at_the_grenze() -> None:
    """A crosshair at one separates the four quadrants the sign flip is read from."""
    shapes = _ratio_scatter().layout.shapes
    assert sorted(shape.x0 == 1.0 for shape in shapes) == [False, True]


@requires_built_data
def test_cap_ratio_pairs_cover_every_gemeinde_observed_at_both_sizes() -> None:
    """The collected caps place 9,368 Gemeinden at household sizes one and four."""
    assert len(cap_ratio_pairs_across_household_sizes(_weighted_built_frame())) == 9368


@requires_built_data
def test_share_with_sign_flip_is_an_eighth_of_the_collected_gemeinden() -> None:
    """In 12.1 % of Gemeinden the cap sits above the Grenze at one of the two sizes."""
    pairs = cap_ratio_pairs_across_household_sizes(_weighted_built_frame())
    assert share_with_sign_flip(pairs) == pytest.approx(0.121, abs=5e-4)
