"""Render a Plotly figure to the static PNG the presentation deck embeds.

Every figure this project writes as interactive HTML is also written as a PNG
next to it, so that a slide renders the figure without loading Plotly and so that
the deck exports to PDF. This module is the single place that decides at what
size and resolution such a PNG is made.
"""

from pathlib import Path

import plotly.graph_objects as go

# The rendering geometry of a presentation PNG. A Slidev slide is 980 by 552 CSS
# pixels at the default 16:9 aspect ratio; the width and height below hold that
# ratio, and the scale factor of 2 renders at twice the device pixels so that the
# image is not upscaled on a high-density display or a projector.
PRESENTATION_WIDTH_PIXELS = 1600
PRESENTATION_HEIGHT_PIXELS = 900
PRESENTATION_SCALE = 2


def write_presentation_png(figure: go.Figure, path: Path) -> None:
    """Write `figure` to `path` as a PNG sized for a 16:9 slide.

    The image is rendered at 1600 by 900 logical pixels — 16:9, the aspect of a
    Slidev slide — with a device pixel ratio of 2, giving a 3200 by 1800 file.
    Whatever template the figure resolves to is kept, so a figure built under
    `plotly_dark` exports dark and sits on the deck's dark background without an
    opaque white rectangle around it.

    Args:
        figure: The figure to render. It is not modified.
        path: Destination file. Its parent directory must exist.

    """
    figure.write_image(
        path,
        format="png",
        width=PRESENTATION_WIDTH_PIXELS,
        height=PRESENTATION_HEIGHT_PIXELS,
        scale=PRESENTATION_SCALE,
    )
