"""Behaviour of the comparison against the Bundesagentur housing-cost record."""

import numpy as np
import pandas as pd
import pytest

from kdu.validation.validate_against_wohnkostenstatistik import (
    build_district_market_pressure,
    grouped_weighted_mean,
    validate_against_wohnkostenstatistik,
)


def test_grouped_weighted_mean_weights_by_population() -> None:
    """A Kreis cap is the mean over its Gemeinden weighted by inhabitants."""
    frame = pd.DataFrame(
        {
            "district_ags": ["05566", "05566"],
            "kdu_cap": [400.0, 500.0],
            "population": [1_000.0, 3_000.0],
        },
    )
    result = grouped_weighted_mean(frame, "kdu_cap", "population", ["district_ags"])
    assert result.loc["05566"] == pytest.approx(475.0)


def test_grouped_weighted_mean_ignores_gemeinden_without_a_cap() -> None:
    """A Gemeinde publishing no cap leaves both numerator and denominator alone."""
    frame = pd.DataFrame(
        {
            "district_ags": ["05566", "05566"],
            "kdu_cap": [400.0, np.nan],
            "population": [1_000.0, 9_000.0],
        },
    )
    result = grouped_weighted_mean(frame, "kdu_cap", "population", ["district_ags"])
    assert result.loc["05566"] == pytest.approx(400.0)


def test_build_district_market_pressure_evaluates_rent_at_admissible_area() -> None:
    """The market rent is the local rent per square metre times the admitted area."""
    caps = pd.DataFrame(
        {
            "ags": ["05566001"],
            "household_size": [1],
            "kdu_cap": [500.0],
            "max_area_sqm": [50.0],
        },
    )
    gemeinden = pd.DataFrame(
        {"ags": ["05566001"], "district_ags": ["05566"], "population": [1_000.0]},
    )
    zensus = pd.DataFrame(
        {"ags": ["05566001"], "nettokaltmiete_eur_per_sqm_mean": [7.0]},
    )
    fallback = pd.DataFrame(
        {
            "ags": ["05566001"],
            "household_size": [1],
            "wohngeld_fallback_cap": [480.0],
        },
    )
    result = build_district_market_pressure(caps, gemeinden, zensus, fallback)
    assert result["market_rent_eur"].iloc[0] == pytest.approx(350.0)


def test_validate_reports_the_bedarfsgemeinschaft_weighted_share() -> None:
    """The weighted share follows the Bedarfsgemeinschaften, not the Jobcenter count."""
    wohnkostenstatistik = pd.DataFrame(
        {
            "jobcenter_id": ["t00001", "t00002"],
            "district_ags": ["05566", "05570"],
            "household_size": [1, 1],
            "bedarfsgemeinschaften": [1_000.0, 3_000.0],
            "actual_bruttokaltmiete": [400.0, 400.0],
            "recognised_bruttokaltmiete": [360.0, 400.0],
            "non_recognised_share": [0.10, 0.00],
        },
    )
    market_pressure = pd.DataFrame(
        {
            "district_ags": ["05566", "05570"],
            "household_size": [1, 1],
            "kdu_cap": [400.0, 500.0],
            "wohngeld_fallback_cap": [480.0, 600.0],
            "max_area_sqm": [50.0, 50.0],
            "nettokaltmiete_eur_per_sqm": [7.0, 7.0],
            "market_rent_eur": [350.0, 350.0],
        },
    )
    result = validate_against_wohnkostenstatistik(
        wohnkostenstatistik,
        market_pressure,
    )
    assert result["bedarfsgemeinschaft_weighted_non_recognised_share"].iloc[
        0
    ] == pytest.approx(0.025)


def test_validate_reports_the_mean_shortfall_in_euro() -> None:
    """The shortfall is actual minus recognised Bruttokaltmiete."""
    wohnkostenstatistik = pd.DataFrame(
        {
            "jobcenter_id": ["t00001", "t00002"],
            "district_ags": ["05566", "05570"],
            "household_size": [1, 1],
            "bedarfsgemeinschaften": [1_000.0, 1_000.0],
            "actual_bruttokaltmiete": [400.0, 500.0],
            "recognised_bruttokaltmiete": [380.0, 460.0],
            "non_recognised_share": [0.05, 0.08],
        },
    )
    market_pressure = pd.DataFrame(
        {
            "district_ags": ["05566", "05570"],
            "household_size": [1, 1],
            "kdu_cap": [400.0, 500.0],
            "wohngeld_fallback_cap": [480.0, 600.0],
            "max_area_sqm": [50.0, 50.0],
            "nettokaltmiete_eur_per_sqm": [7.0, 7.0],
            "market_rent_eur": [350.0, 350.0],
        },
    )
    result = validate_against_wohnkostenstatistik(
        wohnkostenstatistik,
        market_pressure,
    )
    assert result["mean_shortfall_eur"].iloc[0] == pytest.approx(30.0)


def test_build_district_market_pressure_weights_the_fallback_by_population() -> None:
    """The Kreis fallback cap is the mean over its Gemeinden weighted by inhabitants."""
    caps = pd.DataFrame(
        {
            "ags": ["05566001", "05566002"],
            "household_size": [1, 1],
            "kdu_cap": [500.0, 500.0],
            "max_area_sqm": [50.0, 50.0],
        },
    )
    gemeinden = pd.DataFrame(
        {
            "ags": ["05566001", "05566002"],
            "district_ags": ["05566", "05566"],
            "population": [1_000.0, 3_000.0],
        },
    )
    zensus = pd.DataFrame(
        {
            "ags": ["05566001", "05566002"],
            "nettokaltmiete_eur_per_sqm_mean": [7.0, 7.0],
        },
    )
    fallback = pd.DataFrame(
        {
            "ags": ["05566001", "05566002"],
            "household_size": [1, 1],
            "wohngeld_fallback_cap": [400.0, 500.0],
        },
    )
    result = build_district_market_pressure(caps, gemeinden, zensus, fallback)
    assert result["wohngeld_fallback_cap"].iloc[0] == pytest.approx(475.0)


def _cap_comparison_result(
    kdu_cap: list[float],
    wohngeld_fallback_cap: list[float],
    recognised: list[float],
) -> pd.DataFrame:
    """Run the comparison over Jobcenter that differ only in caps and recognition."""
    districts = [f"0556{index}" for index in range(len(recognised))]
    wohnkostenstatistik = pd.DataFrame(
        {
            "jobcenter_id": [f"t0000{index}" for index in range(len(recognised))],
            "district_ags": districts,
            "household_size": [1] * len(recognised),
            "bedarfsgemeinschaften": [1_000.0] * len(recognised),
            "actual_bruttokaltmiete": recognised,
            "recognised_bruttokaltmiete": recognised,
            "non_recognised_share": [0.0] * len(recognised),
        },
    )
    market_pressure = pd.DataFrame(
        {
            "district_ags": districts,
            "household_size": [1] * len(recognised),
            "kdu_cap": kdu_cap,
            "wohngeld_fallback_cap": wohngeld_fallback_cap,
            "max_area_sqm": [50.0] * len(recognised),
            "nettokaltmiete_eur_per_sqm": [7.0] * len(recognised),
            "market_rent_eur": [350.0] * len(recognised),
        },
    )
    return validate_against_wohnkostenstatistik(wohnkostenstatistik, market_pressure)


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        ("correlation_log_kdu_cap_log_recognised", 1.0),
        ("correlation_log_wohngeld_fallback_log_recognised", -1.0),
    ],
)
def test_validate_correlates_each_cap_with_recognised_bruttokaltmiete(
    column: str,
    expected: float,
) -> None:
    """A cap proportional to what is recognised correlates perfectly in logs."""
    result = _cap_comparison_result(
        kdu_cap=[400.0, 500.0, 600.0],
        wohngeld_fallback_cap=[300.0, 240.0, 200.0],
        recognised=[320.0, 400.0, 480.0],
    )
    assert result[column].iloc[0] == pytest.approx(expected)


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        ("median_recognised_over_kdu_cap", 0.9),
        ("median_recognised_over_wohngeld_fallback", 0.5),
    ],
)
def test_validate_reports_the_median_ratio_of_recognised_to_each_cap(
    column: str,
    expected: float,
) -> None:
    """The median ratio is taken over Jobcenter, one weight each."""
    result = _cap_comparison_result(
        kdu_cap=[500.0, 500.0, 500.0],
        wohngeld_fallback_cap=[900.0, 900.0, 900.0],
        recognised=[400.0, 450.0, 500.0],
    )
    assert result[column].iloc[0] == pytest.approx(expected)


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        ("share_recognised_above_kdu_cap", 0.25),
        ("share_recognised_above_wohngeld_fallback", 0.5),
    ],
)
def test_validate_reports_the_share_of_jobcenter_recognising_above_each_cap(
    column: str,
    expected: float,
) -> None:
    """A Jobcenter counts as above a cap when its mean recognised amount exceeds it."""
    result = _cap_comparison_result(
        kdu_cap=[400.0, 400.0, 400.0, 400.0],
        wohngeld_fallback_cap=[300.0, 300.0, 300.0, 300.0],
        recognised=[500.0, 350.0, 250.0, 250.0],
    )
    assert result[column].iloc[0] == pytest.approx(expected)


def test_validate_counts_only_jobcenter_carrying_both_caps() -> None:
    """A Kreis missing either cap is left out of the cap comparison."""
    result = _cap_comparison_result(
        kdu_cap=[400.0, 500.0, np.nan],
        wohngeld_fallback_cap=[300.0, 240.0, 200.0],
        recognised=[320.0, 400.0, 480.0],
    )
    assert result["jobcenter_with_both_caps"].iloc[0] == 2


def test_validate_counts_only_jobcenter_with_a_market_rent_in_the_correlation() -> None:
    """A Kreis without a Zensus rent contributes levels but not the correlation."""
    wohnkostenstatistik = pd.DataFrame(
        {
            "jobcenter_id": ["t00001", "t00002", "t00003"],
            "district_ags": ["05566", "05570", "05580"],
            "household_size": [1, 1, 1],
            "bedarfsgemeinschaften": [1_000.0, 1_000.0, 1_000.0],
            "actual_bruttokaltmiete": [400.0, 500.0, 450.0],
            "recognised_bruttokaltmiete": [380.0, 460.0, 430.0],
            "non_recognised_share": [0.05, 0.08, 0.04],
        },
    )
    market_pressure = pd.DataFrame(
        {
            "district_ags": ["05566", "05570", "05580"],
            "household_size": [1, 1, 1],
            "kdu_cap": [400.0, 500.0, 450.0],
            "wohngeld_fallback_cap": [480.0, 600.0, 540.0],
            "max_area_sqm": [50.0, 50.0, 50.0],
            "nettokaltmiete_eur_per_sqm": [7.0, 7.0, np.nan],
            "market_rent_eur": [350.0, 350.0, np.nan],
        },
    )
    result = validate_against_wohnkostenstatistik(
        wohnkostenstatistik,
        market_pressure,
    )
    assert result["jobcenter_with_market_rent"].iloc[0] == 2
