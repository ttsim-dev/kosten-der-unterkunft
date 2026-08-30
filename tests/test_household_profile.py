import numpy as np
import pandas as pd
import pytest

from kdu.analysis.household_profile import (
    DECILE_MOVE_THRESHOLD,
    N_DECILES,
    MarginalRatioStatus,
    bedarfsgemeinschaft_weights,
    build_familien_tilt,
    build_marginal_amounts,
    check_wogg_linked_tilt,
    decile_group,
    decile_transition_matrix,
    share_moving_at_least_deciles,
    spearman_correlation,
    summarise_distribution,
    weighted_quantile,
)


def make_long(
    kdu: dict[int, float],
    wogg: dict[int, float],
    ags: str = "01001000",
) -> pd.DataFrame:
    sizes = sorted(kdu)
    return pd.DataFrame(
        {
            "ags": [ags] * len(sizes),
            "household_size": sizes,
            "kdu_bkc_cap": [kdu[size] for size in sizes],
            "wogg_primary_cap": [wogg[size] for size in sizes],
        },
    )


def concat_long(*frames: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(frames, ignore_index=True)


PROPORTIONAL_WOGG = {1: 400.0, 2: 500.0, 3: 600.0, 4: 700.0}


def test_familien_tilt_is_zero_when_kdu_is_a_fixed_multiple_of_wohngeld() -> None:
    """A Gemeinde whose K is `c * W` at every h carries no Familien-Tilt."""
    multiple = 1.10
    long = make_long(
        kdu={size: multiple * cap for size, cap in PROPORTIONAL_WOGG.items()},
        wogg=PROPORTIONAL_WOGG,
    )

    tilt = build_familien_tilt(long)

    np.testing.assert_allclose(tilt.loc["01001000", "tilt_h4"], 0.0, atol=1e-12)


def test_familien_tilt_is_positive_when_kdu_rises_faster_than_wohngeld() -> None:
    """K rising faster with h than W does gives `F > 0`."""
    long = make_long(
        kdu={1: 440.0, 2: 580.0, 3: 720.0, 4: 875.0},
        wogg=PROPORTIONAL_WOGG,
    )

    tilt = build_familien_tilt(long)

    expected = np.log(875.0 / 700.0) - np.log(440.0 / 400.0)
    np.testing.assert_allclose(tilt.loc["01001000", "tilt_h4"], expected, atol=1e-12)
    assert tilt.loc["01001000", "tilt_h4"] > 0


def test_familien_tilt_is_negative_when_kdu_rises_more_slowly_than_wohngeld() -> None:
    """K rising more slowly with h than W does gives `F < 0`."""
    long = make_long(
        kdu={1: 440.0, 2: 480.0, 3: 520.0, 4: 560.0},
        wogg=PROPORTIONAL_WOGG,
    )

    tilt = build_familien_tilt(long)

    assert tilt.loc["01001000", "tilt_h4"] < 0


def test_familien_tilt_is_missing_when_the_reference_size_has_no_benchmark() -> None:
    """Without a Wohngeld Höchstbetrag at h=1 no tilt can be formed."""
    long = make_long(
        kdu={1: 440.0, 2: 580.0, 3: 720.0, 4: 875.0},
        wogg={1: np.nan, 2: 500.0, 3: 600.0, 4: 700.0},
    )

    tilt = build_familien_tilt(long)

    assert pd.isna(tilt.loc["01001000", "tilt_h4"])


def test_mean_log_relative_level_averages_over_the_available_sizes() -> None:
    """The average relative KdU level is the mean of `log(K/W)` across h."""
    long = make_long(
        kdu={size: 1.10 * cap for size, cap in PROPORTIONAL_WOGG.items()},
        wogg=PROPORTIONAL_WOGG,
    )

    tilt = build_familien_tilt(long)

    np.testing.assert_allclose(
        tilt.loc["01001000", "mean_log_relative_level"],
        np.log(1.10),
        atol=1e-12,
    )


def test_marginal_amounts_report_the_kdu_step_per_additional_person() -> None:
    """`ΔK(g,h) = K(g,h) - K(g,h-1)`."""
    long = make_long(kdu={1: 400.0, 2: 470.0}, wogg={1: 400.0, 2: 500.0})

    marginal = build_marginal_amounts(long)

    step = marginal.set_index("household_size").loc[2, "kdu_step"]
    np.testing.assert_allclose(step, 70.0, atol=1e-12)


def test_marginal_ratio_is_the_kdu_step_over_the_wohngeld_step() -> None:
    """`Q(g,h) = ΔK / ΔW`."""
    long = make_long(kdu={1: 400.0, 2: 470.0}, wogg={1: 400.0, 2: 500.0})

    marginal = build_marginal_amounts(long)

    ratio = marginal.set_index("household_size").loc[2, "marginal_ratio"]
    np.testing.assert_allclose(ratio, 0.70, atol=1e-12)


def test_marginal_ratio_is_missing_not_infinite_when_the_wogg_step_is_zero() -> None:
    """A zero Wohngeld step yields a missing ratio, never an infinity."""
    long = make_long(kdu={1: 400.0, 2: 470.0}, wogg={1: 500.0, 2: 500.0})

    marginal = build_marginal_amounts(long)

    ratio = marginal.set_index("household_size").loc[2, "marginal_ratio"]
    assert pd.isna(ratio)
    assert np.isfinite(marginal["marginal_ratio"].to_numpy(dtype="float64")).sum() == 0


def test_zero_wogg_step_is_recorded_as_its_own_status() -> None:
    """The reason a ratio is undefined is carried alongside it, not inferred."""
    long = make_long(kdu={1: 400.0, 2: 470.0}, wogg={1: 500.0, 2: 500.0})

    marginal = build_marginal_amounts(long)

    status = marginal.set_index("household_size").loc[2, "marginal_ratio_status"]
    assert status == MarginalRatioStatus.WOGG_STEP_ZERO


def test_missing_wogg_step_is_recorded_as_its_own_status() -> None:
    """Gemeinden without a statutory Mietenstufe get `wogg_step_missing`."""
    long = make_long(kdu={1: 400.0, 2: 470.0}, wogg={1: np.nan, 2: np.nan})

    marginal = build_marginal_amounts(long)

    status = marginal.set_index("household_size").loc[2, "marginal_ratio_status"]
    assert status == MarginalRatioStatus.WOGG_STEP_MISSING


def test_smallest_household_size_has_no_previous_size() -> None:
    """h=1 carries no step, and says so."""
    long = make_long(kdu={1: 400.0, 2: 470.0}, wogg={1: 400.0, 2: 500.0})

    marginal = build_marginal_amounts(long)

    status = marginal.set_index("household_size").loc[1, "marginal_ratio_status"]
    assert status == MarginalRatioStatus.NO_PREVIOUS_SIZE


def test_per_capita_amounts_divide_the_cap_by_household_size() -> None:
    """`K^pc(g,h) = K(g,h) / h`."""
    long = make_long(kdu={1: 400.0, 2: 470.0}, wogg={1: 400.0, 2: 500.0})

    marginal = build_marginal_amounts(long)

    per_capita = marginal.set_index("household_size").loc[2, "kdu_per_capita"]
    np.testing.assert_allclose(per_capita, 235.0, atol=1e-12)


def test_marginal_amounts_reject_non_contiguous_household_sizes() -> None:
    """A gap in h would silently turn one step into two."""
    long = make_long(kdu={1: 400.0, 3: 600.0}, wogg={1: 400.0, 3: 600.0})

    with pytest.raises(ValueError, match="contiguous"):
        build_marginal_amounts(long)


def test_spearman_correlation_of_a_series_with_itself_is_one() -> None:
    """Identical rankings correlate perfectly."""
    values = pd.Series([412.0, 388.0, 655.0, 500.0, 500.0, 721.0, 299.0])

    np.testing.assert_allclose(spearman_correlation(values, values), 1.0, atol=1e-12)


def test_spearman_correlation_of_a_reversed_series_is_minus_one() -> None:
    """A strictly reversed ranking correlates at -1."""
    values = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])

    np.testing.assert_allclose(
        spearman_correlation(values, values.iloc[::-1].reset_index(drop=True)),
        -1.0,
        atol=1e-12,
    )


def test_spearman_correlation_uses_ranks_not_levels() -> None:
    """A monotone but non-linear transformation leaves the rank correlation at 1."""
    values = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])

    np.testing.assert_allclose(
        spearman_correlation(values, pd.Series(np.exp(values))),
        1.0,
        atol=1e-12,
    )


def test_spearman_correlation_is_missing_for_a_constant_series() -> None:
    """A series with no variation has no ranking to correlate."""
    values = pd.Series([1.0, 2.0, 3.0, 4.0])

    assert pd.isna(spearman_correlation(values, pd.Series([7.0] * 4)))


def test_decile_group_splits_into_equally_sized_groups() -> None:
    """Ten deciles over 100 observations hold ten Gemeinden each."""
    values = pd.Series(np.arange(100.0))

    counts = decile_group(values).value_counts()

    assert counts.unique().tolist() == [10]


def test_decile_transition_matrix_rows_sum_to_one() -> None:
    """Every row of the transition matrix is a conditional distribution."""
    rng = np.random.default_rng(seed=20260827)
    first = pd.Series(rng.normal(size=500))
    second = first + pd.Series(rng.normal(scale=0.5, size=500))

    matrix = decile_transition_matrix(first, second)

    np.testing.assert_allclose(matrix.to_numpy().sum(axis=1), np.ones(N_DECILES))


def test_decile_transition_matrix_is_the_identity_under_an_unchanged_ranking() -> None:
    """Nobody moves when the second ranking repeats the first."""
    values = pd.Series(np.arange(100.0))

    matrix = decile_transition_matrix(values, values)

    np.testing.assert_allclose(matrix.to_numpy(), np.eye(N_DECILES))


def test_decile_transition_matrix_requires_at_least_one_observation_per_decile() -> (
    None
):
    """Fewer observations than deciles cannot fill the matrix."""
    values = pd.Series([1.0, 2.0, 3.0])

    with pytest.raises(ValueError, match="at least"):
        decile_transition_matrix(values, values)


def test_share_moving_at_least_two_deciles_is_zero_under_an_unchanged_ranking() -> None:
    """An unchanged ranking moves nobody."""
    values = pd.Series(np.arange(100.0))

    share = share_moving_at_least_deciles(values, values)

    np.testing.assert_allclose(share, 0.0, atol=1e-12)


def test_share_moving_at_least_two_deciles_under_a_reversed_ranking() -> None:
    """Reversing the ranking moves everyone but the two middle deciles, which swap."""
    values = pd.Series(np.arange(100.0))

    share = share_moving_at_least_deciles(values, -values)

    np.testing.assert_allclose(share, 0.80, atol=1e-12)


def test_share_moving_counts_a_move_of_exactly_the_threshold() -> None:
    """The threshold is inclusive: a move of exactly two deciles counts."""
    values = pd.Series(np.arange(100.0))
    swapped = values.copy()
    swapped.iloc[0:10] = values.iloc[20:30].to_numpy()
    swapped.iloc[20:30] = values.iloc[0:10].to_numpy()

    share = share_moving_at_least_deciles(values, swapped)

    assert DECILE_MOVE_THRESHOLD == 2
    np.testing.assert_allclose(share, 0.20, atol=1e-12)


def test_weighted_quantile_matches_the_plain_median_under_equal_weights() -> None:
    """Equal weights give the ordinary median."""
    values = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])

    result = weighted_quantile(values, pd.Series(np.ones(5)), (0.5,))

    np.testing.assert_allclose(result, [3.0], atol=1e-12)


def test_weighted_quantile_follows_the_weights() -> None:
    """A dominant weight pulls the median onto its own value."""
    values = pd.Series([1.0, 2.0, 3.0])
    weights = pd.Series([1.0, 1.0, 100.0])

    result = weighted_quantile(values, weights, (0.5,))

    np.testing.assert_allclose(result, [3.0], atol=1e-12)


def test_summarise_distribution_reports_the_share_above_zero() -> None:
    """`share_positive` is the weighted share of strictly positive values."""
    values = pd.Series([-1.0, 0.0, 1.0, 2.0])

    summary = summarise_distribution(values)

    np.testing.assert_allclose(summary["share_positive"], 0.5, atol=1e-12)


def test_summarise_distribution_reports_the_spike_at_zero() -> None:
    """`share_exact_zero` makes the WoGG-linked pile-up countable."""
    values = pd.Series([-1.0, 0.0, 0.0, 2.0])

    summary = summarise_distribution(values)

    np.testing.assert_allclose(summary["share_exact_zero"], 0.5, atol=1e-12)


def test_check_wogg_linked_tilt_confirms_a_proportional_flagged_group() -> None:
    """Flagged Gemeinden whose K is proportional to W show a zero maximum tilt."""
    tilt = pd.Series([0.0, 0.0, 0.12, -0.08], index=list("abcd"))
    flag = pd.Series([True, True, False, False], index=list("abcd"))

    diagnostic = check_wogg_linked_tilt(tilt, flag)

    np.testing.assert_allclose(diagnostic["max_abs_tilt_flagged"], 0.0, atol=1e-12)
    np.testing.assert_allclose(diagnostic["share_exactly_zero_flagged"], 1.0)


def test_check_wogg_linked_tilt_exposes_a_flagged_group_that_is_not_flat() -> None:
    """A flagged Gemeinden with a real tilt is reported, not absorbed."""
    tilt = pd.Series([0.0, 0.30, 0.12, -0.08], index=list("abcd"))
    flag = pd.Series([True, True, False, False], index=list("abcd"))

    diagnostic = check_wogg_linked_tilt(tilt, flag)

    np.testing.assert_allclose(diagnostic["max_abs_tilt_flagged"], 0.30, atol=1e-12)
    np.testing.assert_allclose(diagnostic["share_exactly_zero_flagged"], 0.5)


def test_tilt_is_reported_for_every_requested_household_size() -> None:
    """The h=3 and h=5 tilts sit beside the headline h=4 tilt."""
    long = make_long(
        kdu={1: 440.0, 2: 580.0, 3: 720.0, 4: 875.0, 5: 1000.0},
        wogg={1: 400.0, 2: 500.0, 3: 600.0, 4: 700.0, 5: 800.0},
    )

    tilt = build_familien_tilt(long, sizes=(3, 4, 5))

    assert {"tilt_h3", "tilt_h4", "tilt_h5"} <= set(tilt.columns)


def test_tilt_frame_keeps_one_row_per_gemeinde() -> None:
    """The tilt frame is keyed by AGS alone."""
    long = concat_long(
        make_long(kdu={1: 440.0, 2: 580.0, 3: 720.0, 4: 875.0}, wogg=PROPORTIONAL_WOGG),
        make_long(
            kdu={1: 400.0, 2: 500.0, 3: 600.0, 4: 700.0},
            wogg=PROPORTIONAL_WOGG,
            ags="01002000",
        ),
    )

    tilt = build_familien_tilt(long)

    assert tilt.index.tolist() == ["01001000", "01002000"]


def test_bedarfsgemeinschaft_weights_split_the_kreis_stock_by_population() -> None:
    """Scheme 4 of §8.2 gives a Gemeinde its share of its Kreis's BG stock."""
    gemeinde = pd.DataFrame(
        {
            "policy_region_id": ["01001", "01001"],
            "population": [3000.0, 1000.0],
        },
        index=pd.Index(["01001000", "01001001"], name="ags"),
    )
    stocks = pd.DataFrame(
        {
            "policy_region_id": ["01001"],
            "household_size": [4],
            "bg_stock": [800.0],
        },
    )

    weights = bedarfsgemeinschaft_weights(gemeinde, stocks, household_size=4)

    np.testing.assert_allclose(weights.to_numpy(), [600.0, 200.0])
