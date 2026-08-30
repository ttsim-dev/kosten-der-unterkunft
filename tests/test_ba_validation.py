import numpy as np
import pandas as pd
import pytest

from kdu.analysis.ba_validation import (
    BENCHMARK_COLUMN,
    CAP_COLUMN,
    CLUSTER_COLUMN,
    GAP_COLUMN,
    KREISE_ABSENT_FROM_KDU_TABLE,
    LOG_CAP_RATIO_COLUMN,
    NON_RECOGNISED_COLUMN,
    DescriptiveFit,
    LeastSquaresFit,
    LinkageGroup,
    Specification,
    fail_if_unexpected_kreis_absent,
    fit_least_squares,
    fit_specification,
    kreis_coverage,
    nationally_weighted_relevance,
    non_recognised_identity_deviation,
    regressor_variation,
    stamp_regressors,
    weighted_mean_by,
)


def _cluster_frame(
    n_clusters: int = 60,
    per_cluster: int = 4,
    slope: float = -0.05,
    cluster_sd: float = 0.4,
    seed: int = 20260827,
) -> pd.DataFrame:
    """Panel whose errors share a cluster component, so clustering must matter."""
    rng = np.random.default_rng(seed)
    cluster = np.repeat(np.arange(n_clusters), per_cluster)
    regressor = np.repeat(rng.normal(0.0, 1.0, n_clusters), per_cluster)
    shock = np.repeat(rng.normal(0.0, cluster_sd, n_clusters), per_cluster)
    noise = rng.normal(0.0, 0.05, n_clusters * per_cluster)
    return pd.DataFrame(
        {
            "cluster": [f"c{index:03d}" for index in cluster],
            "regressor": regressor,
            "outcome": 0.2 + slope * regressor + shock + noise,
        },
    )


def _design(frame: pd.DataFrame) -> np.ndarray:
    return np.column_stack(
        [np.ones(len(frame)), frame["regressor"].to_numpy(dtype=float)],
    )


def test_fit_least_squares_recovers_known_slope() -> None:
    """A synthetic frame built at a known slope returns that slope."""
    frame = _cluster_frame(slope=-0.05, cluster_sd=0.0)
    fit = fit_least_squares(
        design=_design(frame),
        outcome=frame["outcome"].to_numpy(dtype=float),
        clusters=frame["cluster"].to_numpy(),
        names=("intercept", "regressor"),
    )
    np.testing.assert_allclose(fit.estimate("regressor"), -0.05, atol=5e-3)


def test_clustered_se_exceeds_classical_under_cluster_shocks() -> None:
    """Errors correlated inside a cluster make the classical standard error too low."""
    frame = _cluster_frame(cluster_sd=0.4)
    fit = fit_least_squares(
        design=_design(frame),
        outcome=frame["outcome"].to_numpy(dtype=float),
        clusters=frame["cluster"].to_numpy(),
        names=("intercept", "regressor"),
    )
    assert fit.cluster_se("regressor") > fit.classical_se("regressor")


def test_fit_least_squares_reports_the_number_of_clusters() -> None:
    """`n_clusters` counts distinct cluster labels, not observations."""
    frame = _cluster_frame(n_clusters=60, per_cluster=4)
    fit = fit_least_squares(
        design=_design(frame),
        outcome=frame["outcome"].to_numpy(dtype=float),
        clusters=frame["cluster"].to_numpy(),
        names=("intercept", "regressor"),
    )
    assert (fit.n_obs, fit.n_clusters) == (240, 60)


def _validation_frame() -> pd.DataFrame:
    """Small Jobcenter panel with a planted `log(K/W)` slope of −0.05."""
    frame = _cluster_frame(n_clusters=40, per_cluster=4, slope=-0.05, cluster_sd=0.02)
    frame = frame.rename(columns={"cluster": CLUSTER_COLUMN})
    frame["household_size"] = np.tile([1, 2, 3, 4], 40)
    frame["state_name"] = np.where(frame.index < len(frame) // 2, "Hessen", "Bayern")
    frame[BENCHMARK_COLUMN] = 500.0
    frame[CAP_COLUMN] = 500.0 * np.exp(frame["regressor"] / 10.0)
    frame["max_area_sqm"] = 60.0
    frame["market_rent_eur_per_sqm"] = 8.0
    frame[NON_RECOGNISED_COLUMN] = 0.2 + (-0.5) * np.log(
        frame[CAP_COLUMN] / frame[BENCHMARK_COLUMN],
    )
    frame[GAP_COLUMN] = frame[NON_RECOGNISED_COLUMN] * 600.0
    frame["share_at_exact_ratio"] = 0.0
    frame["share_linked_union"] = 0.0
    frame["validation_sample"] = "main"
    frame["bg_stock"] = 100.0
    return stamp_regressors(frame)


def _fitted(specification: Specification) -> DescriptiveFit:
    fit = fit_specification(
        _validation_frame(),
        specification=specification,
        linkage_group=LinkageGroup.ALL,
    )
    assert fit is not None
    return fit


def test_fit_specification_recovers_the_planted_slope() -> None:
    """A frame built with `N = 0.2 − 0.5·log(K/W)` returns β = −0.5."""
    fit = _fitted(Specification.CAP_VS_BENCHMARK)
    np.testing.assert_allclose(fit.beta, -0.5, atol=1e-8)


def test_fit_specification_reports_clusters_as_jobcenter() -> None:
    """Standard errors cluster on the Jobcenter, as §14.4 requires."""
    assert _fitted(Specification.CAP_VS_BENCHMARK).n_clusters == 40


def test_regressor_variation_flags_a_degenerate_cap_ratio() -> None:
    """Where `K/W` is pinned at the Sicherheitszuschlag the regressor has no spread."""
    frame = _validation_frame()
    frame[CAP_COLUMN] = frame[BENCHMARK_COLUMN] * 1.10
    frame["share_at_exact_ratio"] = 1.0
    variation = regressor_variation(stamp_regressors(frame))
    degenerate = variation.loc[
        (variation["linkage_group"] == LinkageGroup.EXACT_RATIO_ONLY.value)
        & (variation["regressor"] == LOG_CAP_RATIO_COLUMN)
    ]
    assert float(degenerate["sd"].iloc[0]) == pytest.approx(0.0, abs=1e-12)


def test_weighted_mean_by_matches_a_hand_computed_average() -> None:
    """Weighting by population reproduces the average worked out by hand."""
    frame = pd.DataFrame(
        {
            "ags_kreis": ["06411", "06411", "06412"],
            "value": [400.0, 600.0, 500.0],
            "population": [1.0, 3.0, 2.0],
        },
    )
    means = weighted_mean_by(frame, ("ags_kreis",), ("value",), "population")
    assert means.set_index("ags_kreis").loc["06411", "value"] == pytest.approx(550.0)


def test_weighted_mean_by_ignores_weights_of_missing_values() -> None:
    """A missing value drops its own weight instead of poisoning the whole cell."""
    frame = pd.DataFrame(
        {
            "ags_kreis": ["06411", "06411"],
            "value": [400.0, np.nan],
            "population": [1.0, 9.0],
        },
    )
    means = weighted_mean_by(frame, ("ags_kreis",), ("value",), "population")
    assert means.set_index("ags_kreis").loc["06411", "value"] == pytest.approx(400.0)


def _relevance_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    proxy_error = pd.DataFrame(
        {
            "policy_region_id": ["06411", "06411", "06412"],
            "household_size": [1, 1, 1],
            "proxy_error_eur": [10.0, 30.0, 100.0],
            "population": [1.0, 1.0, 1.0],
        },
    )
    stocks = pd.DataFrame(
        {
            "policy_region_id": ["06411", "06412"],
            "household_size": [1, 1],
            "bg_stock": [300.0, 100.0],
        },
    )
    return proxy_error, stocks


def test_nationally_weighted_relevance_matches_a_hand_computed_bg_average() -> None:
    """`D̄^BG` averages the Kreis means with the Kreis BG stocks as weights."""
    proxy_error, stocks = _relevance_inputs()
    relevance = nationally_weighted_relevance(proxy_error, stocks).set_index(
        "household_size",
    )
    assert relevance.loc[1, "bg_weighted_mean"] == pytest.approx(40.0)


def test_nationally_weighted_relevance_bg_weights_sum_to_the_stock_total() -> None:
    """The reported weight total equals the sum of the BG stocks that entered."""
    proxy_error, stocks = _relevance_inputs()
    relevance = nationally_weighted_relevance(proxy_error, stocks).set_index(
        "household_size",
    )
    assert relevance.loc[1, "bg_total"] == pytest.approx(400.0)


def test_non_recognised_identity_holds_to_floating_tolerance() -> None:
    """`N^BA = 1 − R^BA` in every published cell."""
    outcomes = pd.DataFrame(
        {
            "region_level": ["kreis"] * 4,
            "region_code": ["06411", "06411", "06412", "06412"],
            "breakdown": ["household_size"] * 4,
            "category": ["1_person"] * 2 + ["2_persons"] * 2,
            "cost_component": ["bruttokaltmiete"] * 4,
            "basis": ["per_bg"] * 4,
            "outcome": [
                "ba_recognition_rate",
                "ba_non_recognised_share",
                "ba_recognition_rate",
                "ba_non_recognised_share",
            ],
            "value": [0.97, 0.03, 0.95, 0.05],
        },
    )
    assert non_recognised_identity_deviation(outcomes) == pytest.approx(0.0, abs=1e-12)


def _coverage_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    jobcenter_crosswalk = pd.DataFrame(
        {
            "jobcenter_id": ["t43106", "t43107", "t43108"],
            "ags_kreis": ["06415", "06411", "06412"],
            "sample": ["main", "main", "main"],
        },
    )
    municipality_crosswalk = pd.DataFrame(
        {
            "ags": ["06411000", "06412000"],
            "ags_kreis": ["06411", "06412"],
        },
    )
    return jobcenter_crosswalk, municipality_crosswalk


def test_kreis_coverage_marks_hanau_as_absent_from_the_kdu_table() -> None:
    """Hanau is reported with its own status rather than dropped by the join."""
    jobcenter_crosswalk, municipality_crosswalk = _coverage_inputs()
    coverage = kreis_coverage(
        jobcenter_crosswalk,
        municipality_crosswalk,
        kdu_kreise=frozenset({"06411"}),
    ).set_index("ags_kreis")
    assert coverage.loc["06415", "status"] == "absent_from_kdu_table"


def test_kreis_coverage_records_the_documented_reason_for_hanau() -> None:
    """The reason comes from `KREISE_ABSENT_FROM_KDU_TABLE`, not from a blank cell."""
    jobcenter_crosswalk, municipality_crosswalk = _coverage_inputs()
    coverage = kreis_coverage(
        jobcenter_crosswalk,
        municipality_crosswalk,
        kdu_kreise=frozenset({"06411"}),
    ).set_index("ags_kreis")
    assert coverage.loc["06415", "reason"] == KREISE_ABSENT_FROM_KDU_TABLE["06415"]


def test_kreis_coverage_separates_a_kreis_without_a_main_sample_cap() -> None:
    """A Kreis in the KdU table but outside the main sample gets its own status."""
    jobcenter_crosswalk, municipality_crosswalk = _coverage_inputs()
    coverage = kreis_coverage(
        jobcenter_crosswalk,
        municipality_crosswalk,
        kdu_kreise=frozenset({"06411"}),
    ).set_index("ags_kreis")
    assert coverage.loc["06412", "status"] == "no_main_sample_cap"


def test_fail_if_unexpected_kreis_absent_raises_on_an_undocumented_kreis() -> None:
    """A new Kreis missing from the KdU table must stop the build, not vanish."""
    coverage = pd.DataFrame(
        {
            "ags_kreis": ["06415", "06499"],
            "status": ["absent_from_kdu_table", "absent_from_kdu_table"],
        },
    )
    with pytest.raises(ValueError, match="06499"):
        fail_if_unexpected_kreis_absent(coverage)


def test_fail_if_unexpected_kreis_absent_accepts_the_documented_kreis() -> None:
    """Hanau alone is expected, so a coverage frame holding only it passes."""
    coverage = pd.DataFrame(
        {"ags_kreis": ["06415"], "status": ["absent_from_kdu_table"]},
    )
    assert fail_if_unexpected_kreis_absent(coverage) is None


def test_least_squares_fit_rejects_an_unknown_coefficient_name() -> None:
    """Asking for a coefficient the design never held is an error, not a NaN."""
    frame = _cluster_frame(n_clusters=10, per_cluster=2)
    fit: LeastSquaresFit = fit_least_squares(
        design=_design(frame),
        outcome=frame["outcome"].to_numpy(dtype=float),
        clusters=frame["cluster"].to_numpy(),
        names=("intercept", "regressor"),
    )
    with pytest.raises(KeyError, match="market_rent"):
        fit.estimate("market_rent")
