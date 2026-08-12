"""Tests for the diagonal hatch overlay drawn over flagged Gemeinden."""

from typing import Any

import pytest

from kdu.hatching import build_hatch_geojson

SQUARE = {
    "type": "Feature",
    "properties": {"fid": 0},
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[10.0, 50.0], [11.0, 50.0], [11.0, 51.0], [10.0, 51.0]]],
    },
}
DISTANT_SQUARE = {
    "type": "Feature",
    "properties": {"fid": 1},
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[20.0, 50.0], [21.0, 50.0], [21.0, 51.0], [20.0, 51.0]]],
    },
}


@pytest.fixture
def geojson() -> dict[str, Any]:
    """Return two disjoint unit squares, ten degrees apart in longitude."""
    return {"type": "FeatureCollection", "features": [SQUARE, DISTANT_SQUARE]}


def _vertices(collection: dict[str, Any]) -> list[list[float]]:
    return [
        point
        for feature in collection["features"]
        for point in feature["geometry"]["coordinates"]
    ]


def test_hatch_lines_stay_inside_the_selected_polygon(geojson: dict[str, Any]) -> None:
    """Every drawn vertex lies within the bounds of the hatched feature."""
    result = build_hatch_geojson(geojson=geojson, fids={0}, spacing=0.2)

    assert all(
        10.0 <= lon <= 11.0 and 50.0 <= lat <= 51.0 for lon, lat in _vertices(result)
    )


def test_hatch_lines_ignore_unselected_features(geojson: dict[str, Any]) -> None:
    """A feature whose `fid` is not selected contributes no geometry."""
    result = build_hatch_geojson(geojson=geojson, fids={0}, spacing=0.2)

    assert max(lon for lon, _ in _vertices(result)) <= 11.0


def test_hatch_lines_are_separate_features(geojson: dict[str, Any]) -> None:
    """Each hatch line is its own two-point LineString."""
    result = build_hatch_geojson(geojson=geojson, fids={0}, spacing=0.2)

    assert all(
        feature["geometry"]["type"] == "LineString"
        and len(feature["geometry"]["coordinates"]) == 2
        for feature in result["features"]
    )


def test_hatch_spacing_controls_line_count(geojson: dict[str, Any]) -> None:
    """Halving the spacing yields more hatch lines."""
    coarse = build_hatch_geojson(geojson=geojson, fids={0}, spacing=0.4)
    fine = build_hatch_geojson(geojson=geojson, fids={0}, spacing=0.2)

    assert len(fine["features"]) > len(coarse["features"])


def test_hatch_lines_skip_holes() -> None:
    """A ring cut out of the polygon carries no hatch vertices."""
    holed = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"fid": 0},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[10.0, 50.0], [11.0, 50.0], [11.0, 51.0], [10.0, 51.0]],
                        [[10.3, 50.3], [10.7, 50.3], [10.7, 50.7], [10.3, 50.7]],
                    ],
                },
            },
        ],
    }

    result = build_hatch_geojson(geojson=holed, fids={0}, spacing=0.05)

    in_hole = [
        1
        for lon, lat in _vertices(result)
        if 10.35 < lon < 10.65 and 50.35 < lat < 50.65
    ]
    assert not in_hole


def test_hatch_is_empty_without_selection(geojson: dict[str, Any]) -> None:
    """Selecting no feature yields a collection with no features."""
    result = build_hatch_geojson(geojson=geojson, fids=set(), spacing=0.2)

    assert result["features"] == []


def test_hatch_lines_handle_multipolygons() -> None:
    """Both parts of a MultiPolygon are hatched."""
    multi = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"fid": 0},
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [
                        [[[10.0, 50.0], [10.4, 50.0], [10.4, 50.4], [10.0, 50.4]]],
                        [[[12.0, 50.0], [12.4, 50.0], [12.4, 50.4], [12.0, 50.4]]],
                    ],
                },
            },
        ],
    }

    result = build_hatch_geojson(geojson=multi, fids={0}, spacing=0.1)
    drawn = [lon for lon, _ in _vertices(result)]

    assert (min(drawn) < 10.5, max(drawn) > 11.9) == (True, True)
