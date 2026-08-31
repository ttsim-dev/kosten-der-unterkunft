"""Tests for the choropleth's join, its derived measures and its colour ranges."""

from typing import Any

import pandas as pd
import pytest

from kdu.config import MAP_MEASURES
from kdu.maps import (
    _derive_ags,
    _merge_without_duplicating,
    build_hovertemplate,
    build_map_frame,
    describe_household_size,
)
from kdu.measures import compute_colour_range, get_measure

HOUSEHOLD_SIZES = (1, 2, 3, 4, 5)


@pytest.fixture
def geojson() -> dict[str, Any]:
    """Two boundary features carrying the twelve-digit source code and a `fid`."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": None,
                "properties": {
                    "fid": 0,
                    "gem_code": "010010000000",
                    "gem_name": "Flensburg",
                },
            },
            {
                "type": "Feature",
                "geometry": None,
                "properties": {
                    "fid": 1,
                    "gem_code": "010020000000",
                    "gem_name": "Kiel",
                },
            },
        ],
    }


@pytest.fixture
def kdu_caps() -> pd.DataFrame:
    """Caps rising with household size for both Gemeinden."""
    return pd.DataFrame(
        {
            "ags": ["01001000"] * 5 + ["01002000"] * 5,
            "household_size": list(HOUSEHOLD_SIZES) * 2,
            "kdu_cap": [500.0, 600.0, 700.0, 800.0, 900.0] * 2,
            "max_area_sqm": [50.0, 60.0, 75.0, 85.0, 95.0] * 2,
            "haertefall_regelung": [None] * 10,
        },
    )


@pytest.fixture
def wohngeld_fallback() -> pd.DataFrame:
    """A benchmark of 400 euro at every size, so every ratio is a round number."""
    return pd.DataFrame(
        {
            "ags": ["01001000"] * 5 + ["01002000"] * 5,
            "household_size": list(HOUSEHOLD_SIZES) * 2,
            "mietenstufe": [3] * 10,
            "wohngeld_fallback_cap": [400.0] * 10,
        },
    )


@pytest.fixture
def gemeinden() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ags": ["01001000", "01002000"],
            "district_name": ["Kreisfreie Stadt Flensburg", "Kreisfreie Stadt Kiel"],
        },
    )


@pytest.fixture
def gemeinde_types() -> pd.DataFrame:
    return pd.DataFrame(
        {"ags": ["01001000", "01002000"], "gem_type": ["Stadt", "Stadt"]},
    )


@pytest.fixture
def frame(
    geojson: dict[str, Any],
    kdu_caps: pd.DataFrame,
    wohngeld_fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
    gemeinde_types: pd.DataFrame,
) -> pd.DataFrame:
    return build_map_frame(
        geojson=geojson,
        kdu_caps=kdu_caps,
        wohngeld_fallback=wohngeld_fallback,
        gemeinden=gemeinden,
        gemeinde_types=gemeinde_types,
    )


def test_derive_ags_reduces_twelve_digit_code_to_the_eight_digit_key() -> None:
    """The boundary source's twelve-digit code keeps its Kreis and Gemeinde parts."""
    assert _derive_ags("010010000000") == "01001000"


def test_build_map_frame_yields_one_row_per_feature_and_household_size(
    frame: pd.DataFrame,
) -> None:
    """Two features at five household sizes give ten rows."""
    assert len(frame) == 10


def test_build_map_frame_divides_the_cap_by_the_benchmark(
    frame: pd.DataFrame,
) -> None:
    """A 500 euro cap against a 400 euro benchmark is a ratio of 1.25."""
    row = frame.query("fid == 0 and household_size == 1")
    assert row["cap_ratio"].to_numpy()[0] == pytest.approx(1.25)


def test_build_map_frame_divides_the_cap_by_the_admissible_floor_area(
    frame: pd.DataFrame,
) -> None:
    """A 600 euro cap over 60 square metres is 10 euro per square metre."""
    row = frame.query("fid == 0 and household_size == 2")
    assert row["kdu_cap_per_sqm"].to_numpy()[0] == pytest.approx(10.0)


def test_build_map_frame_leaves_the_share_above_the_cap_missing_when_not_supplied(
    frame: pd.DataFrame,
) -> None:
    """The market rent comparison is optional; its measure is then unobserved."""
    assert frame["share_of_stock_above_cap"].isna().all()


def test_merge_without_duplicating_rejects_a_right_frame_with_repeated_keys() -> None:
    """A many-to-many join would inflate every count and colour range downstream."""
    left = pd.DataFrame({"ags": ["01001000"], "value": [1.0]})
    right = pd.DataFrame({"ags": ["01001000", "01001000"], "other": [2.0, 3.0]})
    with pytest.raises(ValueError, match="changed the row count"):
        _merge_without_duplicating(left, right, on="ags")


def test_every_registered_map_measure_resolves_to_a_specification() -> None:
    """The catalog's measure names and the measure registry agree."""
    assert tuple(get_measure(key).key for key in MAP_MEASURES) == MAP_MEASURES


def test_get_measure_rejects_an_unregistered_key() -> None:
    with pytest.raises(ValueError, match="Unknown measure"):
        get_measure("nettokaltmiete")


def test_colour_range_of_the_mietenstufe_spans_the_statutory_scale() -> None:
    """The Mietenstufe runs 1 to 7 whatever the observed values."""
    spec = get_measure("mietenstufe")
    assert compute_colour_range(pd.Series([2.0, 3.0]), spec) == (1.0, 7.0)


def test_colour_range_of_a_diverging_measure_is_symmetric_about_its_midpoint() -> None:
    """Equal departures above and below the benchmark must read equally strong."""
    spec = get_measure("cap_ratio")
    lower, upper = compute_colour_range(pd.Series([0.8, 1.0, 1.3]), spec)
    assert lower + upper == pytest.approx(2.0)


def test_colour_range_of_a_sequential_measure_spans_its_display_quantiles() -> None:
    """A single observed value collapses the 2nd and 98th percentile onto it."""
    spec = get_measure("kdu_cap")
    assert compute_colour_range(pd.Series([450.0]), spec) == (450.0, 450.0)


def test_hovertemplate_names_the_haertefall_field_only_for_a_cap_measure() -> None:
    """A rent surcharge changes a cap, not the Wohnfläche it is measured over."""
    assert "customdata[2]" not in build_hovertemplate(get_measure("max_wohnflaeche"))


def test_hovertemplate_names_the_haertefall_field_for_a_cap_measure() -> None:
    assert "customdata[2]" in build_hovertemplate(get_measure("kdu_cap"))


@pytest.mark.parametrize(
    ("household_size", "expected"),
    [(1, "1 Person"), (4, "4 Personen")],
)
def test_describe_household_size_uses_the_german_singular_and_plural(
    household_size: int,
    expected: str,
) -> None:
    assert describe_household_size(household_size) == expected
