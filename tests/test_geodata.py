"""Tests for boundary simplification."""

from kdu.geodata import round_ring, simplify_feature_collection


def test_round_ring_snaps_coordinates_and_drops_grid_duplicates() -> None:
    # Input: first two points round to the same cell; three distinct corners remain.
    ring = [
        [10.001, 50.002],
        [10.004, 50.001],
        [10.0, 51.0],
        [11.0, 50.5],
        [10.001, 50.002],
    ]
    # Expected: the collapsed duplicate is gone; a valid closed triangle remains.
    expected = [[10.0, 50.0], [10.0, 51.0], [11.0, 50.5], [10.0, 50.0]]
    # Result.
    result = round_ring(ring, decimals=2)
    # Assert.
    assert result == expected


def test_round_ring_returns_none_when_ring_collapses_below_polygon() -> None:
    # Input: all points round to one grid cell — no drawable polygon left.
    ring = [[10.001, 50.001], [10.002, 50.002], [10.001, 50.001]]
    # Expected / Result / Assert.
    assert round_ring(ring, decimals=2) is None


def test_simplify_feature_collection_preserves_properties() -> None:
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


def test_round_ring_drops_points_on_a_straight_edge() -> None:
    # Input: the midpoint of the bottom edge lies exactly on the line between corners.
    ring = [
        [10.0, 50.0],
        [10.5, 50.0],
        [11.0, 50.0],
        [11.0, 51.0],
        [10.0, 50.0],
    ]
    # Expected: the shape is unchanged, so the redundant vertex is gone.
    expected = [[10.0, 50.0], [11.0, 50.0], [11.0, 51.0], [10.0, 50.0]]
    # Result.
    result = round_ring(ring, decimals=2)
    # Assert.
    assert result == expected


def test_round_ring_keeps_a_ring_that_would_collapse_without_its_edge_points() -> None:
    # Input: a staircase whose corners alone still bound an area.
    ring = [[10.0, 50.0], [10.01, 50.0], [10.01, 50.01], [10.0, 50.01], [10.0, 50.0]]
    # Expected / Result / Assert: the four corners survive.
    assert round_ring(ring, decimals=2) == ring


def test_round_ring_keeps_a_degenerate_ring_it_cannot_thin_further() -> None:
    # Input: a sliver whose points all lie on one line.
    ring = [[10.0, 50.0], [10.01, 50.0], [10.02, 50.0], [10.0, 50.0]]
    # Expected / Result / Assert: dropping its edge points would erase the
    # Gemeinde, so the ring survives as it is.
    assert round_ring(ring, decimals=2) == ring
