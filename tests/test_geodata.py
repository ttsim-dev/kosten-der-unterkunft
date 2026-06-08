"""Tests for boundary simplification."""

from kdu.geodata import round_ring, simplify_feature_collection


def test_round_ring_snaps_coordinates_and_drops_grid_duplicates():
    # Input: two points that round to the same grid cell, plus a distinct one.
    ring = [[10.001, 50.002], [10.004, 50.001], [11.0, 51.0], [10.001, 50.002]]
    # Expected: the first two collapse to (10.0, 50.0); ring stays closed.
    expected = [[10.0, 50.0], [11.0, 51.0], [10.0, 50.0], [10.0, 50.0]]
    # Result.
    result = round_ring(ring, decimals=2)
    # Assert.
    assert result == expected


def test_round_ring_returns_none_when_ring_collapses_below_polygon():
    # Input: all points round to one grid cell — no drawable polygon left.
    ring = [[10.001, 50.001], [10.002, 50.002], [10.001, 50.001]]
    # Expected / Result / Assert.
    assert round_ring(ring, decimals=2) is None


def test_simplify_feature_collection_preserves_properties():
    # Input: one polygon feature with a name property.
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"gem_name": "Musterstadt"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[10.0, 50.0], [10.0, 51.0], [11.0, 51.0], [10.0, 50.0]],
                    ],
                },
            },
        ],
    }
    # Expected: the property survives simplification unchanged.
    expected = "Musterstadt"
    # Result.
    result = simplify_feature_collection(geojson, decimals=2)
    # Assert.
    assert result["features"][0]["properties"]["gem_name"] == expected
