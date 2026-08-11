"""Tests for the measure-selectable Gemeinde choropleth."""

from typing import Any

import numpy as np
import pandas as pd
import pytest

from kdu.maps import build_choropleth, build_map_frame
from kdu.measures import MEASURES, MeasureSpec, compute_colour_range


@pytest.fixture
def geojson() -> dict[str, Any]:
    """Return three minimal Gemeinde features in map order."""
    features = []
    properties = (
        {"fid": 0, "gem_code": "010010000000", "gem_name": "Flensburg"},
        {"fid": 1, "gem_code": "091620000000", "gem_name": "München"},
        {"fid": 2, "gem_code": "146270060060", "gem_name": "Großenhain"},
    )
    for index, feature_properties in enumerate(properties):
        longitude = 9.0 + index
        features.append(
            {
                "type": "Feature",
                "properties": feature_properties,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [longitude, 50.0],
                            [longitude, 50.1],
                            [longitude + 0.1, 50.1],
                            [longitude, 50.0],
                        ],
                    ],
                },
            },
        )
    return {"type": "FeatureCollection", "features": features}


@pytest.fixture
def kdu() -> pd.DataFrame:
    """Return completed KdU values for all three Gemeinden."""
    return pd.DataFrame(
        {
            "ags_gemeinde": ["01001000", "09162000", "14627060"],
            "wogg_mietstufe": [3, 7, np.nan],
            "max_bruttokaltmiete_eur_1p": [540, 849, 410],
            "max_bruttokaltmiete_eur_2p": [661, 1092, 500],
            "max_bruttokaltmiete_eur_4p": [929, 1569, 700],
            "max_bruttokaltmiete_eur_sqm": [10.80, 16.98, np.nan],
            "max_nettokaltmiete_eur_1p": [450, 700, 350],
            "max_nettokaltmiete_eur_4p": [800, 1300, 600],
            "max_wohnflaeche_sqm_1p": [50, 50, 45],
            "max_wohnflaeche_sqm_4p": [90, 90, 85],
            "wogg_hoechstbetrag_eur_1p": [456, 677, 408],
            "wogg_hoechstbetrag_eur_2p": [551, 820, 493],
            "wogg_hoechstbetrag_eur_4p": [766, 1139, 686],
            "kdu_vs_wogg_pct_1p": [18.4, 25.4, 0.5],
            "kdu_vs_wogg_pct_2p": [20.0, 33.2, 1.4],
            "kdu_vs_wogg_pct_4p": [21.3, 37.8, 2.0],
        },
    )


@pytest.fixture
def lookup() -> pd.DataFrame:
    """Return Kreis names keyed like the production lookup table."""
    return pd.DataFrame(
        {
            "ags": ["010010000000", "091620000000", "146270060060"],
            "kreis": ["Flensburg", "München", "Landkreis Meißen"],
            "gem_type": ["Stadt", "Stadt", "Gemeindefreies Gebiet"],
        },
    )


def test_build_map_frame_returns_features_and_measures_in_map_order(
    geojson: dict[str, Any],
    kdu: pd.DataFrame,
    lookup: pd.DataFrame,
) -> None:
    expected = pd.DataFrame(
        {
            "fid": [0, 1, 2],
            "ags": ["01001000", "09162000", "14627060"],
            "name": ["Flensburg", "München", "Großenhain"],
            "kreis": ["Flensburg", "München", "Landkreis Meißen"],
            "gem_type": ["Stadt", "Stadt", "Gemeindefreies Gebiet"],
            "wogg_mietstufe": [3.0, 7.0, np.nan],
            "max_bruttokaltmiete_eur_1p": [540.0, 849.0, 410.0],
            "max_bruttokaltmiete_eur_2p": [661.0, 1092.0, 500.0],
            "max_bruttokaltmiete_eur_4p": [929.0, 1569.0, 700.0],
            "max_bruttokaltmiete_eur_sqm": [10.80, 16.98, np.nan],
            "max_nettokaltmiete_eur_1p": [450.0, 700.0, 350.0],
            "max_nettokaltmiete_eur_4p": [800.0, 1300.0, 600.0],
            "max_wohnflaeche_sqm_1p": [50.0, 50.0, 45.0],
            "max_wohnflaeche_sqm_4p": [90.0, 90.0, 85.0],
            "wogg_hoechstbetrag_eur_1p": [456.0, 677.0, 408.0],
            "wogg_hoechstbetrag_eur_2p": [551.0, 820.0, 493.0],
            "wogg_hoechstbetrag_eur_4p": [766.0, 1139.0, 686.0],
            "kdu_vs_wogg_pct_1p": [18.4, 25.4, 0.5],
            "kdu_vs_wogg_pct_2p": [20.0, 33.2, 1.4],
            "kdu_vs_wogg_pct_4p": [21.3, 37.8, 2.0],
        },
    )

    result = build_map_frame(geojson=geojson, kdu=kdu, lookup=lookup)

    pd.testing.assert_frame_equal(result, expected)


def test_build_map_frame_raises_when_a_feature_has_no_kdu_row(
    geojson: dict[str, Any],
    kdu: pd.DataFrame,
    lookup: pd.DataFrame,
) -> None:
    incomplete_kdu = kdu.loc[kdu["ags_gemeinde"].ne("14627060")]

    with pytest.raises(ValueError, match="KdU"):
        build_map_frame(geojson=geojson, kdu=incomplete_kdu, lookup=lookup)


def test_compute_colour_range_returns_concrete_percentiles() -> None:
    values = pd.Series([0.0, 25.0, 50.0, 75.0, 100.0, np.nan])

    result = compute_colour_range(values=values, spec=MEASURES[1])

    assert result == pytest.approx((2.0, 98.0))


def test_compute_colour_range_raises_for_all_missing_values() -> None:
    values = pd.Series([np.nan, np.nan])

    with pytest.raises(ValueError, match="non-missing"):
        compute_colour_range(values=values, spec=MEASURES[1])


def test_compute_colour_range_returns_full_ordinal_range() -> None:
    ordinal_spec = MeasureSpec(
        key="level",
        column="level",
        label="Stufe",
        unit="",
        hover_format="d",
        is_ordinal=True,
    )

    result = compute_colour_range(values=pd.Series([2.0, 5.0]), spec=ordinal_spec)

    assert result == (1, 7)


def test_compute_colour_range_returns_symmetric_diverging_range() -> None:
    diverging_spec = MeasureSpec(
        key="difference",
        column="difference",
        label="Differenz",
        unit="%",
        hover_format="+,.1f",
        is_ordinal=False,
        is_diverging=True,
    )
    values = pd.Series([-100.0, -25.0, 0.0, 50.0, np.nan])

    result = compute_colour_range(values=values, spec=diverging_spec)

    assert result == pytest.approx((-95.5, 95.5))


def test_measures_include_wohngeld_comparison_options_in_display_order() -> None:
    result = [
        (
            spec.key,
            spec.label,
            spec.unit,
            spec.hover_format,
            spec.is_diverging,
        )
        for spec in MEASURES[-6:]
    ]

    assert result == [
        (
            "wogg_hoechstbetrag_eur_1p",
            "Wohngeld-Höchstbetrag, 1 Person",
            "€",
            ",.0f",
            False,
        ),
        (
            "wogg_hoechstbetrag_eur_2p",
            "Wohngeld-Höchstbetrag, 2 Personen",
            "€",
            ",.0f",
            False,
        ),
        (
            "wogg_hoechstbetrag_eur_4p",
            "Wohngeld-Höchstbetrag, 4 Personen",
            "€",
            ",.0f",
            False,
        ),
        (
            "kdu_vs_wogg_pct_1p",
            "KdU ggü. Wohngeld-Höchstbetrag, 1 Person",
            "%",
            "+,.1f",
            True,
        ),
        (
            "kdu_vs_wogg_pct_2p",
            "KdU ggü. Wohngeld-Höchstbetrag, 2 Personen",
            "%",
            "+,.1f",
            True,
        ),
        (
            "kdu_vs_wogg_pct_4p",
            "KdU ggü. Wohngeld-Höchstbetrag, 4 Personen",
            "%",
            "+,.1f",
            True,
        ),
    ]


def test_build_choropleth_has_base_measure_and_fifteen_dropdown_options(
    geojson: dict[str, Any],
    kdu: pd.DataFrame,
    lookup: pd.DataFrame,
) -> None:
    frame = build_map_frame(geojson=geojson, kdu=kdu, lookup=lookup)

    figure = build_choropleth(geojson=geojson, frame=frame)

    assert (
        len(figure.data),
        len(figure.layout.updatemenus[0].buttons),
        figure.layout.updatemenus[0].buttons[0].label,
    ) == (2, 15, "Mietstufe (KdU-Dokument, sonst § 12 WoGG)")


def test_build_choropleth_preserves_missing_values_in_measure_layer(
    geojson: dict[str, Any],
    kdu: pd.DataFrame,
    lookup: pd.DataFrame,
) -> None:
    frame = build_map_frame(geojson=geojson, kdu=kdu, lookup=lookup)

    figure = build_choropleth(geojson=geojson, frame=frame)

    assert np.isnan(figure.data[1].z[2])


def test_build_choropleth_centres_diverging_measure_range_on_zero(
    geojson: dict[str, Any],
    kdu: pd.DataFrame,
    lookup: pd.DataFrame,
) -> None:
    frame = build_map_frame(geojson=geojson, kdu=kdu, lookup=lookup)

    figure = build_choropleth(
        geojson=geojson,
        frame=frame,
        initial_measure="kdu_vs_wogg_pct_1p",
    )

    assert figure.data[1].zmin == pytest.approx(-figure.data[1].zmax)


def test_build_choropleth_colours_negative_red_and_positive_blue(
    geojson: dict[str, Any],
    kdu: pd.DataFrame,
    lookup: pd.DataFrame,
) -> None:
    frame = build_map_frame(geojson=geojson, kdu=kdu, lookup=lookup)

    figure = build_choropleth(
        geojson=geojson,
        frame=frame,
        initial_measure="kdu_vs_wogg_pct_1p",
    )
    colorscale = figure.data[1].colorscale

    assert (colorscale[0][1], colorscale[-1][1]) == (
        "rgb(103,0,31)",
        "rgb(5,48,97)",
    )


def test_build_choropleth_counts_only_real_gemeinden_in_coverage(
    geojson: dict[str, Any],
    kdu: pd.DataFrame,
    lookup: pd.DataFrame,
) -> None:
    kdu.loc[kdu["ags_gemeinde"].eq("14627060"), "wogg_mietstufe"] = 4
    frame = build_map_frame(geojson=geojson, kdu=kdu, lookup=lookup)

    figure = build_choropleth(geojson=geojson, frame=frame)

    assert figure.layout.title.text.endswith("2 von 2 Gemeinden")
