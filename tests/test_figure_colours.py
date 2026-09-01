"""Every figure the deck embeds must read on the deck's white slide.

The presentation renders each figure as a static PNG placed on a light slide, so
a figure resolves to a light template and every colour it sets explicitly is
chosen for contrast against white rather than against a dark plot ground. The
thresholds below are the WCAG 2.1 contrast minima: 4.5 to 1 for type, 3 to 1 for
a graphical element such as a bar, a box or a rule.
"""

import re

import plotly.io as pio
import pytest

from kdu.eligibility import microsimulation
from kdu.kdu_vs_wohngeld import cap_comparison, mietenstufe_dispersion
from kdu.market_rent_comparison import market_rent_correlation, share_of_stock_above_cap

TEXT_CONTRAST_MINIMUM = 4.5
GRAPHIC_CONTRAST_MINIMUM = 3.0

# A gridline separates without competing with the data, so it stays close to the
# white ground rather than clearing a contrast threshold.
GRIDLINE_CONTRAST_MAXIMUM = 2.0

WHITE = (255, 255, 255)

FIGURE_MODULES = (
    cap_comparison,
    mietenstufe_dispersion,
    market_rent_correlation,
    share_of_stock_above_cap,
    microsimulation,
)

TEXT_COLOURS = (
    (cap_comparison, "NEUTRAL_COLOUR"),
    (mietenstufe_dispersion, "NEUTRAL_COLOUR"),
    (market_rent_correlation, "FALLBACK_COLOUR"),
    (share_of_stock_above_cap, "DIFFERENCE_COLOUR"),
    (microsimulation, "LOCAL_CAP_COLOUR"),
    (microsimulation, "FALLBACK_COLOUR"),
)

GRAPHIC_COLOURS = (
    (cap_comparison, "ACCENT_COLOUR"),
    (mietenstufe_dispersion, "ACCENT_COLOUR"),
    (market_rent_correlation, "LOCAL_CAP_COLOUR"),
    (share_of_stock_above_cap, "FALLBACK_COLOUR"),
    (share_of_stock_above_cap, "LOCAL_CAP_COLOUR"),
    (microsimulation, "ANNOTATION_LINE_COLOUR"),
)

GRIDLINE_COLOURS = (
    (market_rent_correlation, "GRID_COLOUR"),
    (share_of_stock_above_cap, "GRID_COLOUR"),
)

ANNOTATION_BACKGROUNDS = (
    (cap_comparison, "ANNOTATION_BACKGROUND"),
    (microsimulation, "ANNOTATION_BACKGROUND"),
)


def _parse_colour(colour: str) -> tuple[int, int, int]:
    """Return the red, green and blue channels of a hexadecimal or rgba colour."""
    if colour.startswith("#"):
        digits = colour.removeprefix("#")
        return (
            int(digits[0:2], 16),
            int(digits[2:4], 16),
            int(digits[4:6], 16),
        )
    channels = re.findall(r"[\d.]+", colour)
    return (int(channels[0]), int(channels[1]), int(channels[2]))


def _relative_luminance(colour: tuple[int, int, int]) -> float:
    """Return the WCAG relative luminance of a colour."""
    channels = []
    for channel in colour:
        value = channel / 255
        linear = value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
        channels.append(linear)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast_ratio(colour: str, other: tuple[int, int, int]) -> float:
    """Return the WCAG contrast ratio between two colours."""
    first = _relative_luminance(_parse_colour(colour))
    second = _relative_luminance(other)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize("module", FIGURE_MODULES)
def test_figure_module_resolves_to_a_light_template(module: object) -> None:
    """Importing a figure module leaves the default template light."""
    assert module is not None
    assert pio.templates.default == "plotly_white"


@pytest.mark.parametrize(("module", "name"), TEXT_COLOURS)
def test_text_colour_is_readable_on_white(module: object, name: str) -> None:
    """A colour that carries type clears the WCAG minimum against white."""
    assert _contrast_ratio(getattr(module, name), WHITE) >= TEXT_CONTRAST_MINIMUM


@pytest.mark.parametrize(("module", "name"), GRAPHIC_COLOURS)
def test_graphic_colour_is_visible_on_white(module: object, name: str) -> None:
    """A colour that carries a bar, box or rule clears the WCAG minimum."""
    assert _contrast_ratio(getattr(module, name), WHITE) >= GRAPHIC_CONTRAST_MINIMUM


@pytest.mark.parametrize(("module", "name"), GRIDLINE_COLOURS)
def test_gridline_colour_stays_close_to_the_white_ground(
    module: object,
    name: str,
) -> None:
    """A gridline is faint enough not to compete with the data."""
    assert _contrast_ratio(getattr(module, name), WHITE) <= GRIDLINE_CONTRAST_MAXIMUM


@pytest.mark.parametrize(("module", "name"), ANNOTATION_BACKGROUNDS)
def test_annotation_background_matches_the_white_plot_ground(
    module: object,
    name: str,
) -> None:
    """A label sits on the plot's own white ground, not on a dark box."""
    assert _parse_colour(getattr(module, name)) == WHITE
