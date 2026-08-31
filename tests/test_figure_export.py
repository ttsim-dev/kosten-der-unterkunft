import struct
from pathlib import Path

import plotly.graph_objects as go
import pytest

from kdu.figure_export import (
    PRESENTATION_HEIGHT_PIXELS,
    PRESENTATION_SCALE,
    PRESENTATION_WIDTH_PIXELS,
    write_presentation_png,
)

PNG_MAGIC_BYTES = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def figure() -> go.Figure:
    return go.Figure(go.Bar(x=[1, 2, 3], y=[4, 5, 6]))


@pytest.fixture
def written_png(figure: go.Figure, tmp_path: Path) -> Path:
    path = tmp_path / "figure.png"
    write_presentation_png(figure, path)
    return path


def test_write_presentation_png_writes_png_magic_bytes(written_png: Path) -> None:
    assert written_png.read_bytes()[:8] == PNG_MAGIC_BYTES


def test_write_presentation_png_writes_the_scaled_slide_width(
    written_png: Path,
) -> None:
    assert _png_pixel_size(written_png)[0] == (
        PRESENTATION_WIDTH_PIXELS * PRESENTATION_SCALE
    )


def test_write_presentation_png_writes_the_scaled_slide_height(
    written_png: Path,
) -> None:
    assert _png_pixel_size(written_png)[1] == (
        PRESENTATION_HEIGHT_PIXELS * PRESENTATION_SCALE
    )


def test_write_presentation_png_leaves_the_figure_layout_size_unset(
    figure: go.Figure,
    tmp_path: Path,
) -> None:
    write_presentation_png(figure, tmp_path / "figure.png")
    assert figure.layout.width is None


def _png_pixel_size(path: Path) -> tuple[int, int]:
    """Return the (width, height) recorded in the PNG's IHDR chunk."""
    header = path.read_bytes()[16:24]
    width, height = struct.unpack(">II", header)
    return int(width), int(height)
