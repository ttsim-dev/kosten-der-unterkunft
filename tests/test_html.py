"""Tests for writing the figure with each feature collection embedded once."""

from pathlib import Path
from typing import Any

import plotly.graph_objects as go

from kdu.html import write_html_with_shared_geojson


def _feature_collection() -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"fid": 0},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[9.0, 50.0], [9.0, 50.1], [9.1, 50.1], [9.0, 50.0]],
                    ],
                },
            },
        ],
    }


def _two_trace_figure() -> go.Figure:
    geojson = _feature_collection()
    traces = [
        go.Choroplethmap(
            geojson=geojson,
            locations=[0],
            featureidkey="properties.fid",
            z=[value],
        )
        for value in (0.0, 1.0)
    ]
    return go.Figure(data=traces)


def test_written_html_embeds_a_shared_feature_collection_once(tmp_path: Path) -> None:
    # Input: two traces drawing the same boundaries.
    path = tmp_path / "map.html"
    # Result.
    write_html_with_shared_geojson(_two_trace_figure(), path)
    html = path.read_text(encoding="utf-8")
    # Assert: the coordinates appear once, not once per trace.
    assert html.count("[9.1,50.1]") == 1


def test_written_html_binds_the_shared_collection_before_plotting(
    tmp_path: Path,
) -> None:
    # Input: two traces drawing the same boundaries.
    path = tmp_path / "map.html"
    # Result.
    write_html_with_shared_geojson(_two_trace_figure(), path)
    html = path.read_text(encoding="utf-8")
    # Assert: the binding runs in the script that plots, ahead of the call.
    script = html[html.rindex("<script") :]

    assert 0 < script.index("var kduGeojson0=") < script.index("Plotly.newPlot(")


def test_written_html_keeps_a_collection_used_only_once_inline(
    tmp_path: Path,
) -> None:
    # Input: a single trace, so nothing repeats.
    path = tmp_path / "map.html"
    figure = go.Figure(
        data=[
            go.Choroplethmap(
                geojson=_feature_collection(),
                locations=[0],
                featureidkey="properties.fid",
                z=[1.0],
            ),
        ],
    )
    # Result.
    write_html_with_shared_geojson(figure, path)
    html = path.read_text(encoding="utf-8")
    # Assert: no variable is introduced for it.
    assert "var kduGeojson0=" not in html


def test_written_html_carries_plotly_for_offline_use(tmp_path: Path) -> None:
    # Input: any figure.
    path = tmp_path / "map.html"
    # Result.
    write_html_with_shared_geojson(_two_trace_figure(), path)
    html = path.read_text(encoding="utf-8")
    # Assert: the library travels with the page instead of being fetched.
    assert "<script src=" not in html
