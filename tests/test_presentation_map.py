"""The static image of the choropleth frames Germany and drops the screen chrome.

The interactive map is read on a screen, where a title names the measure and a
footnote carries the case law. The static image is placed on a slide that
carries its own heading and its own text, so it shows the country and the colour
bar alone, framed so that Germany fills the image.
"""

import math

import plotly.graph_objects as go
import pytest

from kdu.maps import (
    GERMANY_BOUNDS,
    GERMANY_CENTRE,
    GERMANY_ZOOM,
    HAERTEFALL_NOTE,
    PRESENTATION_FOOTNOTE_FONT_SIZE,
    SICHERHEITSZUSCHLAG_NOTE,
    GeographicBounds,
    build_presentation_map,
    compute_map_view,
)

MAP_TILE_SIZE_PIXELS = 512


def _mercator_y(latitude: float) -> float:
    """Return the Web Mercator ordinate of a latitude, in radians of the sphere."""
    return math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2))


@pytest.fixture
def screen_map() -> go.Figure:
    """A choropleth carrying the title, footnote and screen bounds of the HTML map."""
    figure = go.Figure(data=[go.Choroplethmap(z=[1.0], colorbar={"title": {}})])
    figure.update_layout(
        title={"text": "Örtliche Mietobergrenze<br><sup>1 Person</sup>"},
        map={
            "style": "carto-positron",
            "center": GERMANY_CENTRE,
            "zoom": GERMANY_ZOOM,
        },
        annotations=[
            {
                "text": f"{HAERTEFALL_NOTE}<br>{SICHERHEITSZUSCHLAG_NOTE}",
                "font": {"size": 14},
                "showarrow": False,
            },
        ],
        margin={"r": 0, "t": 60, "l": 0, "b": 0},
    )
    return figure


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


def test_build_presentation_map_drops_the_title(screen_map: go.Figure) -> None:
    """The slide carries the heading, so the image carries no title."""
    assert build_presentation_map(screen_map).layout.title.text == ""


def test_build_presentation_map_zooms_past_the_screen_view(
    screen_map: go.Figure,
) -> None:
    """Germany fills the image rather than sitting inside a ring of neighbours."""
    assert build_presentation_map(screen_map).layout.map.zoom > GERMANY_ZOOM


def test_build_presentation_map_drops_the_sicherheitszuschlag_note(
    screen_map: go.Figure,
) -> None:
    """The legal citation is too long to set legibly at slide scale."""
    annotations = build_presentation_map(screen_map).layout.annotations
    assert SICHERHEITSZUSCHLAG_NOTE not in annotations[0].text


def test_build_presentation_map_keeps_the_haertefall_note(
    screen_map: go.Figure,
) -> None:
    """The hatching is visible in the image, so its one-line key stays."""
    annotations = build_presentation_map(screen_map).layout.annotations
    assert annotations[0].text == HAERTEFALL_NOTE


def test_build_presentation_map_enlarges_the_footnote(screen_map: go.Figure) -> None:
    """What survives is set large enough to read when the image is projected."""
    annotations = build_presentation_map(screen_map).layout.annotations
    assert annotations[0].font.size == PRESENTATION_FOOTNOTE_FONT_SIZE


def test_build_presentation_map_enlarges_the_colour_bar_ticks(
    screen_map: go.Figure,
) -> None:
    """The colour bar is the image's only remaining type and is read at a glance."""
    presentation = build_presentation_map(screen_map)
    assert (
        presentation.data[0].colorbar.tickfont.size >= PRESENTATION_FOOTNOTE_FONT_SIZE
    )


def test_build_presentation_map_keeps_room_for_the_colour_bar(
    screen_map: go.Figure,
) -> None:
    """The bar and its tick labels sit in a margin rather than off the image."""
    assert build_presentation_map(screen_map).layout.margin.r > 0


def test_build_presentation_map_places_the_colour_bar_inside_the_image(
    screen_map: go.Figure,
) -> None:
    """The bar is positioned against the image, so its tick labels are not clipped."""
    colourbar = build_presentation_map(screen_map).data[0].colorbar
    assert (colourbar.xref, colourbar.x < 1.0) == ("container", True)


def test_build_presentation_map_leaves_the_screen_figure_untouched(
    screen_map: go.Figure,
) -> None:
    """The interactive map keeps its title, its footnote and its own bounds."""
    build_presentation_map(screen_map)
    assert (
        screen_map.layout.title.text,
        screen_map.layout.map.zoom,
        SICHERHEITSZUSCHLAG_NOTE in screen_map.layout.annotations[0].text,
    ) == ("Örtliche Mietobergrenze<br><sup>1 Person</sup>", GERMANY_ZOOM, True)
