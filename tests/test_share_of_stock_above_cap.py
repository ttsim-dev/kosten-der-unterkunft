"""Tests for the share of a Gemeinde's rented stock priced above a cap."""

import numpy as np
import pandas as pd
import pytest

from kdu.market_rent_comparison.share_of_stock_above_cap import (
    RENT_BANDS,
    _kalte_betriebskosten_per_gemeinde,
    build_gemeinde_shares,
    nettokaltmiete_threshold,
    share_above_threshold,
)

# Kalte Betriebskosten used throughout these tests, in euro per square metre.
BETRIEBSKOSTEN = 1.83


def _band_counts(**counts: float) -> np.ndarray:
    """Return one row of dwelling counts, naming bands by their upper edge."""
    row = [counts.get(f"upper_{band.upper_edge:.0f}", 0.0) for band in RENT_BANDS]
    return np.array([row])


def test_nettokaltmiete_threshold_subtracts_betriebskosten_from_rent_per_sqm() -> None:
    """A 500 euro cap over 50 square metres leaves 10 euro per square metre gross."""
    threshold = nettokaltmiete_threshold(
        np.array([500.0]),
        np.array([50.0]),
        np.array([BETRIEBSKOSTEN]),
    )
    expected = 10.0 - BETRIEBSKOSTEN
    np.testing.assert_allclose(threshold, [expected], atol=1e-12)


def test_nettokaltmiete_threshold_is_missing_when_no_wohnflaeche_is_stated() -> None:
    """A cap without an admissible Wohnfläche yields no threshold."""
    threshold = nettokaltmiete_threshold(
        np.array([500.0]),
        np.array([0.0]),
        np.array([BETRIEBSKOSTEN]),
    )
    assert np.isnan(threshold[0])


def test_share_above_threshold_interpolates_inside_the_containing_band() -> None:
    """A threshold at 7 euro leaves half of the 6-to-8 band and all of 8-to-10 above."""
    counts = _band_counts(upper_8=100.0, upper_10=100.0)
    share = share_above_threshold(counts, np.array([7.0]))
    np.testing.assert_allclose(share, [0.75], atol=1e-12)


def test_share_above_threshold_counts_a_band_in_full_when_it_sits_wholly_above() -> (
    None
):
    """A threshold on a band edge leaves every dwelling in higher bands above it."""
    counts = _band_counts(upper_6=40.0, upper_8=60.0)
    share = share_above_threshold(counts, np.array([6.0]))
    np.testing.assert_allclose(share, [0.6], atol=1e-12)


def test_share_above_threshold_is_one_when_every_dwelling_exceeds_the_cap() -> None:
    """A threshold below the lowest band places the whole stock above the cap."""
    counts = _band_counts(upper_4=10.0, upper_6=90.0)
    share = share_above_threshold(counts, np.array([0.0]))
    np.testing.assert_allclose(share, [1.0], atol=1e-12)


def test_share_above_threshold_is_zero_when_the_cap_exceeds_every_rent() -> None:
    """A threshold above the top band places no dwelling above the cap."""
    counts = _band_counts(upper_4=10.0, upper_6=90.0)
    share = share_above_threshold(counts, np.array([30.0]))
    np.testing.assert_allclose(share, [0.0], atol=1e-12)


def test_share_above_threshold_is_missing_where_no_dwellings_are_counted() -> None:
    """A Gemeinde with no rented stock yields no share."""
    share = share_above_threshold(_band_counts(), np.array([8.0]))
    assert np.isnan(share[0])


def test_share_above_threshold_rejects_counts_without_one_column_per_band() -> None:
    """Dwelling counts must carry a column for every Zensus rent band."""
    with pytest.raises(ValueError, match="one column per rent band"):
        share_above_threshold(np.zeros((1, 3)), np.array([8.0]))


def test_rent_bands_are_contiguous_and_ascending() -> None:
    """Each band starts where the previous one ends, so no dwelling is counted twice."""
    edges = [(band.lower_edge, band.upper_edge) for band in RENT_BANDS]
    assert [upper for _, upper in edges[:-1]] == [lower for lower, _ in edges[1:]]


def test_build_gemeinde_shares_reports_the_difference_between_the_two_caps() -> None:
    """The local cap and the fallback are compared on the same rented stock."""
    kdu_caps = pd.DataFrame(
        {
            "ags": ["01001000"],
            "household_size": [1],
            "kdu_cap": [500.0],
            "max_area_sqm": [50.0],
        },
    )
    wohngeld_fallback = pd.DataFrame(
        {
            "ags": ["01001000"],
            "household_size": [1],
            "mietenstufe": [3],
            "wohngeld_fallback_cap": [400.0],
        },
    )
    zensus_rents = pd.DataFrame(
        {"ags": ["01001000"]}
        | {
            band.column: [100.0 if band.upper_edge in {8.0, 10.0} else 0.0]
            for band in RENT_BANDS
        },
    )

    gemeinden = pd.DataFrame(
        {"ags": ["01001000"], "district_ags": ["01001"]},
    )
    wohnkostenstatistik = pd.DataFrame(
        {
            "district_ags": ["01001"],
            "household_size": [1],
            "bedarfsgemeinschaften": [100.0],
            "kalte_betriebskosten_per_sqm": [BETRIEBSKOSTEN],
        },
    )

    shares = build_gemeinde_shares(
        kdu_caps,
        wohngeld_fallback,
        zensus_rents,
        gemeinden,
        wohnkostenstatistik,
    )

    # Local cap: 500 / 50 - 1.83 = 8.17, so the 6-to-8 band is wholly below and
    # 8-to-10 contributes (10 - 8.17) / 2 of its 100 dwellings.
    np.testing.assert_allclose(
        shares.loc[0, "share_above_local_kdu_cap"],
        (10.0 - (10.0 - BETRIEBSKOSTEN)) / 2.0 * 100.0 / 200.0,
        atol=1e-12,
    )
    # Fallback: 400 / 50 - 1.83 = 6.17, leaving (8 - 6.17) / 2 of the 6-to-8
    # band and all of 8-to-10 above.
    expected_fallback = ((8.0 - (8.0 - BETRIEBSKOSTEN)) / 2.0 * 100.0 + 100.0) / 200.0
    np.testing.assert_allclose(
        shares.loc[0, "share_above_wohngeld_fallback_cap"],
        expected_fallback,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        shares.loc[0, "absolute_share_difference"],
        abs(
            shares.loc[0, "share_above_local_kdu_cap"]
            - shares.loc[0, "share_above_wohngeld_fallback_cap"],
        ),
        atol=1e-12,
    )


def test_kalte_betriebskosten_are_weighted_by_bedarfsgemeinschaften() -> None:
    """A Kreis reporting two household sizes is averaged by its claimant counts."""
    gemeinden = pd.DataFrame({"ags": ["09999000"], "district_ags": ["09999"]})
    wohnkostenstatistik = pd.DataFrame(
        {
            "district_ags": ["09999", "09999"],
            "household_size": [1, 2],
            "bedarfsgemeinschaften": [300.0, 100.0],
            "kalte_betriebskosten_per_sqm": [2.00, 1.00],
        },
    )

    betriebskosten = _kalte_betriebskosten_per_gemeinde(
        pd.Series(["09999000"]),
        gemeinden,
        wohnkostenstatistik,
    )

    # (300 * 2.00 + 100 * 1.00) / 400 = 1.75
    np.testing.assert_allclose(betriebskosten.to_numpy(), [1.75], atol=1e-12)


def test_a_kreis_reporting_no_betriebskosten_takes_the_national_mean() -> None:
    """A Gemeinde whose Kreis is absent falls back to the claimant-weighted mean."""
    gemeinden = pd.DataFrame(
        {"ags": ["09999000", "08888000"], "district_ags": ["09999", "08888"]},
    )
    wohnkostenstatistik = pd.DataFrame(
        {
            "district_ags": ["09999"],
            "household_size": [1],
            "bedarfsgemeinschaften": [400.0],
            "kalte_betriebskosten_per_sqm": [1.75],
        },
    )

    betriebskosten = _kalte_betriebskosten_per_gemeinde(
        pd.Series(["08888000"]),
        gemeinden,
        wohnkostenstatistik,
    )

    np.testing.assert_allclose(betriebskosten.to_numpy(), [1.75], atol=1e-12)
