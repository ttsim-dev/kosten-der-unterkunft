import numpy as np
import pandas as pd
import pytest

from kdu.analysis.within_mietenstufe import (
    Specification,
    Stratum,
    dispersion_within_mietenstufe,
    fit_variance_decomposition,
    stratified_dispersion,
    table_3,
    weighted_quantile,
)


def _frame(
    caps: dict[int, list[float]],
    *,
    household_size: int = 1,
    wogg_base_cap: float = 400.0,
    flagged: dict[int, list[bool]] | None = None,
) -> pd.DataFrame:
    """Build a minimal analysis frame from Mietenstufe to a list of KdU caps."""
    rows = []
    counter = 0
    for rent_level, values in caps.items():
        for position, value in enumerate(values):
            counter += 1
            is_flagged = False if flagged is None else flagged[rent_level][position]
            rows.append(
                {
                    "ags": f"{counter:08d}",
                    "household_size": household_size,
                    "wogg_rent_level": rent_level,
                    "kdu_bkc_cap": value,
                    "wogg_base_cap": wogg_base_cap,
                    "policy_region_id": f"{counter // 2:05d}",
                    "state_name": "Bayern" if counter % 2 else "Hessen",
                    "wogg_linked_flag": is_flagged,
                    "population": 1_000,
                },
            )
    frame = pd.DataFrame(rows)
    frame["kdu_over_wogg"] = frame["kdu_bkc_cap"] / frame["wogg_base_cap"]
    return frame


def test_fit_variance_decomposition_without_within_group_variation_explains_all() -> (
    None
):
    """A cap that is constant within every Mietenstufe leaves nothing unexplained."""
    frame = _frame({1: [400.0] * 5, 2: [500.0] * 5, 3: [600.0] * 5})

    fit = fit_variance_decomposition(frame, specification=Specification.MIETENSTUFE)

    assert fit.r_squared == pytest.approx(1.0)


def test_fit_variance_decomposition_without_within_group_variation_has_zero_residuals() -> (  # noqa: E501
    None
):
    """A cap that is constant within every Mietenstufe leaves a zero residual sd."""
    frame = _frame({1: [400.0] * 5, 2: [500.0] * 5, 3: [600.0] * 5})

    fit = fit_variance_decomposition(frame, specification=Specification.MIETENSTUFE)

    assert fit.residual_sd == pytest.approx(0.0, abs=1e-12)


def test_fit_variance_decomposition_recovers_known_residual_dispersion() -> None:
    """Log deviations of ±a around each Mietenstufe mean give sd `a*sqrt(n/(n-k))`."""
    log_a = 0.2
    levels = (1, 2, 3, 4)
    centres = {1: 400.0, 2: 500.0, 3: 600.0, 4: 700.0}
    caps = {
        level: [
            centres[level] * np.exp(sign * log_a) for sign in (-1.0, -1.0, 1.0, 1.0)
        ]
        for level in levels
    }
    frame = _frame(caps)

    fit = fit_variance_decomposition(frame, specification=Specification.MIETENSTUFE)

    n_obs, n_parameters = 4 * len(levels), len(levels)
    expected = log_a * np.sqrt(n_obs / (n_obs - n_parameters))
    assert fit.residual_sd == pytest.approx(expected)


def test_fit_variance_decomposition_with_state_effects_weakly_raises_r_squared() -> (
    None
):
    """Adding Bundesland effects to a nested specification cannot lower `R²`."""
    rng = np.random.default_rng(seed=20260827)
    caps = {
        level: list(400.0 + 60.0 * level + rng.normal(0.0, 40.0, size=40))
        for level in (1, 2, 3, 4)
    }
    frame = _frame(caps)

    pooled = fit_variance_decomposition(frame, specification=Specification.POOLED)
    with_state = fit_variance_decomposition(
        frame,
        specification=Specification.POOLED_WITH_STATE,
    )

    assert with_state.r_squared >= pooled.r_squared


def test_fit_variance_decomposition_counts_policy_regions_as_clusters() -> None:
    """Standard errors cluster on the Kreis, so the cluster count is the Kreis count."""
    frame = _frame({1: [400.0, 420.0, 440.0, 460.0], 2: [500.0, 520.0, 540.0, 560.0]})

    fit = fit_variance_decomposition(frame, specification=Specification.MIETENSTUFE)

    assert fit.n_policy_regions == frame["policy_region_id"].nunique()


def test_fit_variance_decomposition_clustering_widens_correlated_standard_errors() -> (
    None
):
    """Residuals that repeat within a Kreis inflate the clustered standard error."""
    rng = np.random.default_rng(seed=5471)
    n_clusters, per_cluster = 40, 5
    shock = rng.normal(0.0, 0.25, size=n_clusters)
    rows = []
    for cluster in range(n_clusters):
        for member in range(per_cluster):
            rows.append(  # noqa: PERF401
                {
                    "ags": f"{cluster * per_cluster + member:08d}",
                    "household_size": 1,
                    "wogg_rent_level": 1 + cluster % 3,
                    "kdu_bkc_cap": 500.0 * np.exp(shock[cluster]),
                    "wogg_base_cap": 400.0,
                    "policy_region_id": f"{cluster:05d}",
                    "state_name": "Bayern",
                    "wogg_linked_flag": False,
                    "population": 1_000,
                },
            )
    frame = pd.DataFrame(rows)

    fit = fit_variance_decomposition(frame, specification=Specification.MIETENSTUFE)

    coefficients = fit.coefficients
    assert (coefficients["cluster_se"] > coefficients["classical_se"]).all()


def test_weighted_quantile_matches_unweighted_on_equal_weights() -> None:
    """Equal weights reproduce the ordinary linear-interpolation quantile."""
    values = np.arange(11.0)

    result = weighted_quantile(values, np.ones(11), 0.9)

    assert result == pytest.approx(9.0)


def test_dispersion_within_mietenstufe_spread_matches_hand_computed_value() -> None:
    """`P90 − P10` on 0…10 within one Mietenstufe is `9 − 1 = 8`."""
    frame = _frame({1: list(np.arange(11.0))})

    dispersion = dispersion_within_mietenstufe(frame, value_column="kdu_bkc_cap")

    assert dispersion["p90_minus_p10"].to_numpy()[0] == pytest.approx(8.0)


def test_dispersion_within_mietenstufe_share_above_50_eur_matches_hand_count() -> None:
    """Two of five Gemeinden sit more than 50 € from their Mietenstufe median."""
    frame = _frame({1: [400.0, 460.0, 500.0, 540.0, 620.0]})

    dispersion = dispersion_within_mietenstufe(frame, value_column="kdu_bkc_cap")

    assert dispersion["share_abs_dev_above_50_eur"].to_numpy()[0] == pytest.approx(0.4)


def test_dispersion_within_mietenstufe_share_above_100_eur_matches_hand_count() -> None:
    """One of five Gemeinden sits more than 100 € from its Mietenstufe median."""
    frame = _frame({1: [400.0, 460.0, 500.0, 540.0, 620.0]})

    dispersion = dispersion_within_mietenstufe(frame, value_column="kdu_bkc_cap")

    assert dispersion["share_abs_dev_above_100_eur"].to_numpy()[0] == pytest.approx(0.2)


def test_dispersion_excluding_wogg_linked_gemeinden_raises_the_log_spread() -> None:
    """Dropping the Gemeinden pinned to `K/W = 1.10` widens the measured dispersion."""
    caps = {1: [440.0, 440.0, 440.0, 440.0, 300.0, 380.0, 520.0, 620.0]}
    flagged = {1: [True, True, True, True, False, False, False, False]}
    frame = _frame(caps, flagged=flagged)

    all_gemeinden = dispersion_within_mietenstufe(frame, value_column="kdu_over_wogg")
    unlinked = dispersion_within_mietenstufe(
        frame.loc[~frame["wogg_linked_flag"]],
        value_column="kdu_over_wogg",
    )

    assert unlinked["sd_log"].to_numpy()[0] > all_gemeinden["sd_log"].to_numpy()[0]


def test_fit_variance_decomposition_excluding_wogg_linked_lowers_r_squared() -> None:
    """The WoGG-linked Gemeinden carry no within-Mietenstufe variation, so they lift R²."""  # noqa: E501
    caps = {
        1: [440.0] * 8 + [300.0, 380.0, 520.0, 620.0],
        2: [550.0] * 8 + [400.0, 480.0, 640.0, 760.0],
    }
    flagged = {level: [True] * 8 + [False] * 4 for level in (1, 2)}
    frame = _frame(caps, flagged=flagged)

    with_flagged = fit_variance_decomposition(
        frame,
        specification=Specification.MIETENSTUFE,
    )
    without_flagged = fit_variance_decomposition(
        frame.loc[~frame["wogg_linked_flag"]],
        specification=Specification.MIETENSTUFE,
    )

    assert without_flagged.residual_sd > with_flagged.residual_sd


def test_stratified_dispersion_reports_every_requested_stratum() -> None:
    """Each stratum requested appears in the stratified dispersion output."""
    frame = _frame({1: [400.0, 500.0, 600.0]})
    frame["is_small_gemeinde"] = [True, False, True]
    frame["is_kreisfrei"] = [False, True, False]
    frame["wogg_linked_flag"] = [True, False, False]

    dispersion = stratified_dispersion(frame, value_column="kdu_bkc_cap")

    assert set(dispersion["stratum"].unique()) == {member.value for member in Stratum}


def test_table_3_reports_one_row_per_household_size_and_sample() -> None:
    """Table 3 pairs every household size with the with- and without-flagged sample."""
    caps = {1: [400.0, 450.0, 500.0], 2: [500.0, 560.0, 620.0]}
    frames = [
        _frame(caps, household_size=size, wogg_base_cap=400.0 + 50.0 * size)
        for size in (1, 2)
    ]
    frame = pd.concat(frames, ignore_index=True)

    table = table_3(frame)

    assert len(table) == 4
