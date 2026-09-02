"""The map view that frames a geographic box inside an image of a given size.

`compute_map_view` is Web Mercator geometry: it returns the centre and the zoom
at which a bounding box fits a frame of a stated pixel size, with a margin left
around it.
"""

import math

import pytest

from kdu.maps import (
    GERMANY_BOUNDS,
    GeographicBounds,
    compute_map_view,
)

MAP_TILE_SIZE_PIXELS = 512


def _mercator_y(latitude: float) -> float:
    """Return the Web Mercator ordinate of a latitude, in radians of the sphere."""
    return math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2))


def test_compute_map_view_centres_on_the_middle_of_the_bounds() -> None:
    """The view is centred on the midpoint of the box in the projection plane."""
    view = compute_map_view(
        bounds=GERMANY_BOUNDS,
        width_pixels=1400,
        height_pixels=900,
        margin_fraction=0.05,
    )
    expected_latitude = math.degrees(
        2
        * math.atan(
            math.exp(
                0.5
                * (
                    _mercator_y(GERMANY_BOUNDS.south)
                    + _mercator_y(GERMANY_BOUNDS.north)
                )
            )
        )
        - math.pi / 2,
    )
    assert view.center_latitude == pytest.approx(expected_latitude)


def test_compute_map_view_puts_the_narrower_dimension_in_the_frame() -> None:
    """Zoom is the largest at which both spans still fit the padded frame."""
    view = compute_map_view(
        bounds=GERMANY_BOUNDS,
        width_pixels=1400,
        height_pixels=900,
        margin_fraction=0.05,
    )
    scale = MAP_TILE_SIZE_PIXELS * 2**view.zoom
    longitude_pixels = scale * (GERMANY_BOUNDS.east - GERMANY_BOUNDS.west) / 360
    latitude_pixels = (
        scale
        * (_mercator_y(GERMANY_BOUNDS.north) - _mercator_y(GERMANY_BOUNDS.south))
        / (2 * math.pi)
    )
    assert max(longitude_pixels / 1400, latitude_pixels / 900) == pytest.approx(0.95)


def test_compute_map_view_leaves_no_span_outside_the_frame() -> None:
    """Neither span exceeds the frame it is fitted into."""
    view = compute_map_view(
        bounds=GERMANY_BOUNDS,
        width_pixels=1400,
        height_pixels=900,
        margin_fraction=0.05,
    )
    scale = MAP_TILE_SIZE_PIXELS * 2**view.zoom
    longitude_pixels = scale * (GERMANY_BOUNDS.east - GERMANY_BOUNDS.west) / 360
    assert longitude_pixels <= 1400


def test_compute_map_view_rejects_a_box_of_zero_width() -> None:
    """A box with no east-west extent has no zoom that frames it."""
    with pytest.raises(ValueError, match="west"):
        compute_map_view(
            bounds=GeographicBounds(west=10.0, east=10.0, south=47.0, north=55.0),
            width_pixels=1400,
            height_pixels=900,
            margin_fraction=0.05,
        )
