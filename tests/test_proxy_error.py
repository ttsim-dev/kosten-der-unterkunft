import numpy as np
import pandas as pd
import pytest

from kdu.analysis.proxy_error import (
    PRIMARY_BENCHMARK,
    RENT_POINT_LABELS,
    BenchmarkVariant,
    add_proxy_error_measures,
    at_safety_markup,
    build_analysis_frame,
    build_rent_grid,
    coverage_by_state,
    describe,
    describe_by,
    linkage_overlap,
    observation_weights,
    proxy_error_by_household_size,
    rent_dependent_error,
    weighted_quantile,
    winsorise_for_display,
)
from kdu.config import WeightingScheme, catalog_path


@pytest.fixture(scope="session")
def analysis_frame() -> pd.DataFrame:
    return build_analysis_frame(
        sample=pd.read_parquet(catalog_path("analysis_sample_main")),
        crosswalk=pd.read_parquet(catalog_path("municipality_crosswalk")),
    )


def _row(frame: pd.DataFrame, household_size: int, group: str) -> pd.Series:
    table = proxy_error_by_household_size(frame)
    selected = table.loc[
        (table["household_size"] == household_size) & (table["group"] == group)
    ]
    return selected.iloc[0]


def _toy() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "kdu_bkc_cap": [500.0, 400.0, 456.0, np.nan],
            "wogg_base_cap": [400.0, 500.0, 456.0, 400.0],
            "wogg_climate_component": [20.0, 20.0, 20.0, 20.0],
        },
    )


def test_euro_difference_is_cap_minus_benchmark() -> None:
    measures = add_proxy_error_measures(_toy(), variant=BenchmarkVariant.BASE)
    assert measures["proxy_error_eur"].tolist()[:3] == [100.0, -100.0, 0.0]


def test_relative_difference_is_percent_of_benchmark() -> None:
    measures = add_proxy_error_measures(_toy(), variant=BenchmarkVariant.BASE)
    assert measures["proxy_error_pct"].iloc[0] == pytest.approx(25.0)


def test_log_difference_is_hundred_times_log_ratio() -> None:
    measures = add_proxy_error_measures(_toy(), variant=BenchmarkVariant.BASE)
    expected = 100.0 * np.log(500.0 / 400.0)
    assert measures["proxy_error_log"].iloc[0] == pytest.approx(expected)


def test_absolute_proxy_error_is_unsigned() -> None:
    measures = add_proxy_error_measures(_toy(), variant=BenchmarkVariant.BASE)
    assert measures["proxy_error_abs"].tolist()[:3] == [100.0, 100.0, 0.0]


def test_climate_variant_adds_the_climate_component_to_the_benchmark() -> None:
    measures = add_proxy_error_measures(
        _toy(), variant=BenchmarkVariant.BASE_PLUS_CLIMATE
    )
    assert measures["benchmark_eur"].iloc[0] == pytest.approx(420.0)


def test_missing_benchmark_yields_a_missing_proxy_error() -> None:
    measures = add_proxy_error_measures(_toy(), variant=BenchmarkVariant.BASE)
    assert pd.isna(measures["proxy_error_eur"].iloc[3])


@pytest.mark.parametrize("ratio", [0.5, 0.9, 1.0, 1.1, 1.5, 3.0])
def test_log_difference_is_monotone_in_the_cap_ratio(ratio: float) -> None:
    """`L` rises strictly with `K/W`, which is why §8.1 prefers it for maps."""
    benchmark = 400.0
    lower = add_proxy_error_measures(
        pd.DataFrame(
            {"kdu_bkc_cap": [benchmark * ratio], "wogg_base_cap": [benchmark]},
        ),
        variant=BenchmarkVariant.BASE,
    )["proxy_error_log"].iloc[0]
    higher = add_proxy_error_measures(
        pd.DataFrame(
            {"kdu_bkc_cap": [benchmark * ratio * 1.01], "wogg_base_cap": [benchmark]},
        ),
        variant=BenchmarkVariant.BASE,
    )["proxy_error_log"].iloc[0]
    assert higher > lower


def test_rent_dependent_error_is_zero_below_both_caps() -> None:
    """`e(m) = 0` while actual rent stays under the lower of the two caps."""
    assert rent_dependent_error(rent=300.0, cap=500.0, benchmark=400.0) == 0.0


def test_rent_dependent_error_saturates_at_the_cap_difference() -> None:
    """`e(m) = K − W` once actual rent clears the higher of the two caps."""
    assert rent_dependent_error(rent=900.0, cap=500.0, benchmark=400.0) == 100.0


def test_rent_dependent_error_saturates_for_a_negative_difference() -> None:
    assert rent_dependent_error(rent=900.0, cap=400.0, benchmark=500.0) == -100.0


def test_rent_dependent_error_is_partial_between_the_caps() -> None:
    assert rent_dependent_error(rent=450.0, cap=500.0, benchmark=400.0) == 50.0


def test_rent_grid_carries_the_five_prescribed_rent_points() -> None:
    grid = build_rent_grid(
        pd.DataFrame(
            {
                "ags": ["01001000"],
                "household_size": [1],
                "cap_eur": [500.0],
                "benchmark_eur": [400.0],
                "proxy_error_eur": [100.0],
                "wogg_linked_flag": [False],
            },
        ),
    )
    assert grid["rent_point"].tolist() == list(RENT_POINT_LABELS)


def test_rent_grid_evaluates_the_min_difference_at_every_point() -> None:
    grid = build_rent_grid(
        pd.DataFrame(
            {
                "ags": ["01001000"],
                "household_size": [1],
                "cap_eur": [500.0],
                "benchmark_eur": [400.0],
                "proxy_error_eur": [100.0],
                "wogg_linked_flag": [False],
            },
        ),
    )
    expected = [
        min(320.0, 500.0) - min(320.0, 400.0),
        min(400.0, 500.0) - min(400.0, 400.0),
        min(450.0, 500.0) - min(450.0, 400.0),
        min(500.0, 500.0) - min(500.0, 400.0),
        min(600.0, 500.0) - min(600.0, 400.0),
    ]
    assert grid["benefit_relevant_error_eur"].tolist() == expected


def test_weighted_quantile_reduces_to_the_plain_quantile_under_equal_weights() -> None:
    values = pd.Series([1.0, 2.0, 3.0, 4.0])
    weights = pd.Series([1.0, 1.0, 1.0, 1.0])
    assert weighted_quantile(values, weights, 0.5) == pytest.approx(2.5)


def test_weighted_quantile_follows_the_weight_mass() -> None:
    values = pd.Series([1.0, 100.0])
    weights = pd.Series([999.0, 1.0])
    assert weighted_quantile(values, weights, 0.5) == pytest.approx(1.0, abs=0.2)


def test_winsorising_clips_to_the_requested_tails() -> None:
    clipped = winsorise_for_display(pd.Series(range(101)).astype(float), share=0.01)
    assert (clipped.min(), clipped.max()) == (1.0, 99.0)


def test_winsorising_keeps_the_number_of_observations() -> None:
    values = pd.Series(range(101)).astype(float)
    assert len(winsorise_for_display(values, share=0.01)) == len(values)


def test_analysis_frame_covers_the_main_sample(analysis_frame: pd.DataFrame) -> None:
    """D3's 9,442 Gemeinden all appear, benchmark or not."""
    assert analysis_frame["ags"].nunique() == 9442


def test_comparison_runs_on_the_9323_gemeinden_with_a_benchmark(
    analysis_frame: pd.DataFrame,
) -> None:
    """A2: 119 Gemeinden have no statutory Mietenstufe, so no benchmark exists."""
    comparable = analysis_frame.query("household_size == 1 and comparable")
    assert len(comparable) == 9323


def test_population_weights_sum_to_the_main_sample_population(
    analysis_frame: pd.DataFrame,
) -> None:
    """The population weight reproduces the coverage figure of `coverage_notes.md`."""
    single = analysis_frame.query("household_size == 1")
    weights = observation_weights(single, WeightingScheme.GEMEINDE_POPULATION)
    assert weights.sum() == pytest.approx(75_508_364, rel=1e-9)


def test_policy_region_weights_sum_to_the_number_of_kreise(
    analysis_frame: pd.DataFrame,
) -> None:
    """Scheme 3 gives every Kreis weight one, whatever its Gemeinde count."""
    single = analysis_frame.query("household_size == 1")
    weights = observation_weights(single, WeightingScheme.POLICY_REGION_UNWEIGHTED)
    assert weights.sum() == pytest.approx(single["policy_region_id"].nunique())


def test_unweighted_scheme_gives_every_gemeinde_weight_one(
    analysis_frame: pd.DataFrame,
) -> None:
    single = analysis_frame.query("household_size == 1")
    weights = observation_weights(single, WeightingScheme.GEMEINDE_UNWEIGHTED)
    assert weights.sum() == pytest.approx(len(single))


@pytest.mark.parametrize(
    ("household_size", "expected"),
    [(1, 10.3), (2, 10.1), (4, 10.1)],
)
def test_pooled_median_reproduces_the_decision_log(
    analysis_frame: pd.DataFrame,
    household_size: int,
    expected: float,
) -> None:
    """D7's pooled median `K/W`, in percent, over all comparable Gemeinden."""
    row = _row(analysis_frame, household_size, "all")
    assert row["median_pct"] == pytest.approx(expected, abs=0.15)


@pytest.mark.parametrize(
    ("household_size", "expected"),
    [(1, 12.6), (2, 10.5), (4, 11.2)],
)
def test_median_excluding_the_linked_union_differs_from_the_exact_ratio_split(
    analysis_frame: pd.DataFrame,
    household_size: int,
    expected: float,
) -> None:
    """Dropping `linked_union` does not give D7's table; the groups differ (A12)."""
    row = _row(analysis_frame, household_size, "excluding_wogg_linked")
    assert row["median_pct"] == pytest.approx(expected, abs=0.25)


def test_linked_union_is_not_a_superset_of_the_exact_ratio_group(
    analysis_frame: pd.DataFrame,
) -> None:
    """Some Gemeinden sit exactly at `K/W = 1.10` and are not in `linked_union` (A22)."""
    overlap = linkage_overlap(analysis_frame)
    assert overlap.loc[overlap["household_size"] == 1, "n_exact_only"].iloc[0] > 0


@pytest.mark.parametrize(
    ("household_size", "expected"),
    [(1, 13.9), (2, 10.8), (4, 12.6)],
)
def test_median_excluding_the_definitional_ratio_reproduces_the_decision_log(
    analysis_frame: pd.DataFrame,
    household_size: int,
    expected: float,
) -> None:
    """D7's table is the exact-ratio split: `K/W = 1.10` out, everything else in."""
    row = _row(analysis_frame, household_size, "excluding_at_safety_markup")
    assert row["median_pct"] == pytest.approx(expected, abs=0.1)


@pytest.mark.parametrize(
    ("household_size", "expected"),
    [(1, 12.9), (2, 11.4), (4, 14.4)],
)
def test_share_at_the_definitional_ratio_reproduces_the_decision_log(
    analysis_frame: pd.DataFrame,
    household_size: int,
    expected: float,
) -> None:
    """D7's share of Gemeinden sitting exactly at the 10 % Sicherheitszuschlag."""
    row = _row(analysis_frame, household_size, "all")
    assert row["share_at_safety_markup_pct"] == pytest.approx(expected, abs=0.1)


def test_every_headline_row_comes_as_a_with_and_without_pair(
    analysis_frame: pd.DataFrame,
) -> None:
    """D7: no household size may be reported without the flagged/unflagged split."""
    table = proxy_error_by_household_size(analysis_frame)
    groups = table.groupby("household_size")["group"].apply(set)
    required = {"all", "excluding_wogg_linked", "wogg_linked_only"}
    assert all(required <= value for value in groups)


def test_describe_reports_every_section_8_3_statistic(
    analysis_frame: pd.DataFrame,
) -> None:
    single = analysis_frame.query("household_size == 1 and comparable")
    stats = describe(
        single,
        value_column="proxy_error_eur",
        weights=observation_weights(single, WeightingScheme.GEMEINDE_UNWEIGHTED),
    )
    assert set(stats) >= {
        "n_gemeinden",
        "n_policy_regions",
        "population_covered",
        "mean",
        "std",
        "p10",
        "p25",
        "median",
        "p75",
        "p90",
        "min",
        "max",
        "share_positive",
        "share_negative",
        "share_abs_gt_25",
        "share_abs_gt_50",
        "share_abs_gt_100",
        "mean_absolute",
    }


def test_shares_positive_and_negative_and_zero_exhaust_the_sample(
    analysis_frame: pd.DataFrame,
) -> None:
    single = analysis_frame.query("household_size == 1 and comparable")
    stats = describe(
        single,
        value_column="proxy_error_eur",
        weights=observation_weights(single, WeightingScheme.GEMEINDE_UNWEIGHTED),
    )
    zero_share = 100.0 * float((single["proxy_error_eur"] == 0).mean())
    assert stats["share_positive"] + stats["share_negative"] + zero_share == (
        pytest.approx(100.0)
    )


def test_breakdown_by_state_covers_all_sixteen_bundeslaender(
    analysis_frame: pd.DataFrame,
) -> None:
    single = analysis_frame.query("household_size == 1 and comparable")
    table = describe_by(single, group_column="bundesland")
    assert len(table) == 16


def test_coverage_table_reports_all_gemeinden_not_only_the_sample() -> None:
    """Table 1 counts every Gemeinde in Germany as the denominator."""
    table = coverage_by_state(
        sample=pd.read_parquet(catalog_path("analysis_sample_main")),
        crosswalk=pd.read_parquet(catalog_path("municipality_crosswalk")),
    )
    assert table["n_gemeinden_total"].sum() == 10980


def test_coverage_table_reproduces_the_main_sample_size() -> None:
    table = coverage_by_state(
        sample=pd.read_parquet(catalog_path("analysis_sample_main")),
        crosswalk=pd.read_parquet(catalog_path("municipality_crosswalk")),
    )
    assert table["n_gemeinden_main_sample"].sum() == 9442


def test_quality_shares_sum_to_one_hundred_in_every_state() -> None:
    table = coverage_by_state(
        sample=pd.read_parquet(catalog_path("analysis_sample_main")),
        crosswalk=pd.read_parquet(catalog_path("municipality_crosswalk")),
    )
    total = (
        table["share_quality_a"] + table["share_quality_b"] + table["share_quality_c"]
    )
    np.testing.assert_allclose(total.to_numpy(), 100.0, atol=1e-6)


def _linkage_toy() -> pd.DataFrame:
    """Four Gemeinden covering every cell of the union-by-exact-ratio cross."""
    return pd.DataFrame(
        {
            "ags": ["1", "2", "3", "4"],
            "household_size": [1, 1, 1, 1],
            "wogg_linked_flag": [True, True, False, False],
            "at_safety_markup": [True, False, True, False],
            "comparable": [True, True, True, True],
        },
    )


def test_linkage_overlap_counts_the_gemeinden_in_both_groups() -> None:
    """`n_both` is the Gemeinden the two detectors agree on."""
    overlap = linkage_overlap(_linkage_toy())
    assert overlap.loc[0, "n_both"] == 1


def test_linkage_overlap_counts_the_exact_ratio_gemeinden_the_union_misses() -> None:
    """`exact_ratio` is not contained in `linked_union`, so `n_exact_only` > 0."""
    overlap = linkage_overlap(_linkage_toy())
    assert overlap.loc[0, "n_exact_only"] == 1


def test_linkage_overlap_ignores_gemeinden_without_a_wohngeld_benchmark() -> None:
    """Only the comparable rows count: A2's Gemeinden have no benchmark at all."""
    frame = _linkage_toy().assign(comparable=[True, False, False, False])
    assert linkage_overlap(frame).loc[0, "n_linked_union"] == 1


def test_linkage_overlap_counts_each_gemeinde_once_across_benchmark_variants() -> None:
    """The proxy-error frame carries a row per benchmark variant; a Gemeinde is one."""
    toy = _linkage_toy()
    both_variants = pd.concat(
        [toy.assign(benchmark_variant="base"), toy.assign(benchmark_variant="klima")],
        ignore_index=True,
    )
    assert linkage_overlap(both_variants).loc[0, "n_comparable"] == len(toy)


def test_safety_markup_variant_scales_the_base_cap_by_the_bsg_markup() -> None:
    """`W × 1.10` is the § 12 WoGG table plus the BSG Sicherheitszuschlag (D15)."""
    measures = add_proxy_error_measures(
        _toy(),
        variant=BenchmarkVariant.BASE_PLUS_SAFETY_MARKUP,
    )
    assert measures["benchmark_eur"].iloc[0] == pytest.approx(440.0)


def test_primary_benchmark_is_the_safety_markup_variant() -> None:
    """Headline numbers compare against the fallback the BSG prescribes (D15)."""
    assert PRIMARY_BENCHMARK is BenchmarkVariant.BASE_PLUS_SAFETY_MARKUP


def test_add_proxy_error_measures_defaults_to_the_primary_benchmark() -> None:
    measures = add_proxy_error_measures(_toy())
    assert measures["benchmark_variant"].iloc[0] == str(PRIMARY_BENCHMARK)


def test_safety_markup_variant_leaves_the_log_error_dispersion_unchanged(
    analysis_frame: pd.DataFrame,
) -> None:
    """Scaling `W` by a constant shifts every `L` alike, so the spread is invariant."""
    base = add_proxy_error_measures(analysis_frame, variant=BenchmarkVariant.BASE)
    marked = add_proxy_error_measures(
        analysis_frame,
        variant=BenchmarkVariant.BASE_PLUS_SAFETY_MARKUP,
    )
    assert marked["proxy_error_log"].std() == pytest.approx(
        base["proxy_error_log"].std(),
    )


@pytest.mark.parametrize("variant", list(BenchmarkVariant))
def test_safety_markup_flag_is_independent_of_the_benchmark_variant(
    variant: BenchmarkVariant,
) -> None:
    """`K/W = 1.10` identifies the BSG-linked Kreise whatever `W` a table uses."""
    frame = add_proxy_error_measures(
        pd.DataFrame(
            {
                "kdu_bkc_cap": [501.6, 486.0],
                "wogg_base_cap": [456.0, 456.0],
                "wogg_climate_component": [19.2, 19.2],
            },
        ),
        variant=variant,
    )
    assert at_safety_markup(frame).tolist() == [True, False]
