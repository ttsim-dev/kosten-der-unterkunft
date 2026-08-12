"""Draw a diagonal hatch over selected Gemeinde polygons.

Plotly's map choropleths fill each polygon with a solid colour and offer no
pattern fill, so an overlay that marks a subset of Gemeinden without hiding
their measure colour has to be drawn as line geometry. This module clips a
family of parallel 45° lines against the selected polygons and returns them as
a GeoJSON line collection, ready to hang off `layout.map.layers`. Living in the
layout rather than in a trace is what lets the measure dropdown switch the
overlay on and off, since a button may restyle only one trace at a time.
"""

import math
from typing import Any

import numpy as np

# Converts a perpendicular gap between lines into a spacing along the `y - x` axis.
DIAGONAL_STEP = math.sqrt(2.0)

# Latitude at which one degree of longitude is scaled, so the hatching looks square.
GERMANY_REFERENCE_LATITUDE = 51.2

# Fewest vertices that can bound an area; shorter rings enclose nothing.
MIN_RING_POINTS = 3


def build_hatch_geojson(
    *,
    geojson: dict[str, Any],
    fids: set[int],
    spacing: float = 0.05,
    reference_latitude: float = GERMANY_REFERENCE_LATITUDE,
) -> dict[str, Any]:
    """Clip parallel diagonal lines against the polygons of the selected features.

    Args:
        geojson: Feature collection whose features carry a `fid` property.
        fids: `fid` values of the features to hatch. Others are ignored.
        spacing: Perpendicular gap between adjacent hatch lines, in degrees.
        reference_latitude: Latitude used to scale longitude so the lines meet the
            meridians at a constant on-screen angle.

    Returns:
        A feature collection of two-point LineStrings, one per hatch line. Its
        `features` list is empty when no feature is selected.
    """
    scale = math.cos(math.radians(reference_latitude))
    edges = _collect_edges(geojson=geojson, fids=fids, scale=scale)
    features: list[dict[str, Any]] = []
    if edges.size:
        for offset in _line_offsets(edges=edges, spacing=spacing):
            features.extend(
                _build_line_feature(start=start, end=end, scale=scale)
                for start, end in _clip_line(edges=edges, offset=offset)
            )
    return {"type": "FeatureCollection", "features": features}


def _build_line_feature(
    *,
    start: np.ndarray,
    end: np.ndarray,
    scale: float,
) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {},
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [start[0] / scale, start[1]],
                [end[0] / scale, end[1]],
            ],
        },
    }


def _collect_edges(
    *,
    geojson: dict[str, Any],
    fids: set[int],
    scale: float,
) -> np.ndarray:
    """Return every polygon edge of the selected features as `(x1, y1, x2, y2)`.

    Outer rings and holes are pooled into one array. The even-odd rule then
    resolves both holes and disjoint polygons without tracking which ring a
    crossing came from.
    """
    edges: list[np.ndarray] = []
    for feature in geojson["features"]:
        if feature["properties"].get("fid") not in fids:
            continue
        for ring in _iter_rings(feature["geometry"]):
            points = np.asarray(ring, dtype=float)
            if len(points) < MIN_RING_POINTS:
                continue
            points[:, 0] *= scale
            closed = np.vstack([points, points[:1]])
            edges.append(np.hstack([closed[:-1], closed[1:]]))
    return np.vstack(edges) if edges else np.empty((0, 4))


def _iter_rings(geometry: dict[str, Any]) -> list[list[list[float]]]:
    if geometry["type"] == "Polygon":
        return geometry["coordinates"]
    if geometry["type"] == "MultiPolygon":
        return [ring for polygon in geometry["coordinates"] for ring in polygon]
    return []


def _line_offsets(*, edges: np.ndarray, spacing: float) -> np.ndarray:
    """Return the `y - x` offsets of the hatch lines covering the edge bounds."""
    offsets = np.concatenate([edges[:, 1] - edges[:, 0], edges[:, 3] - edges[:, 2]])
    step = spacing * DIAGONAL_STEP
    first = math.ceil(offsets.min() / step) * step
    return np.arange(first, offsets.max(), step)


def _clip_line(
    *,
    edges: np.ndarray,
    offset: float,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Return the parts of the line `y - x == offset` that fall inside the polygons.

    Crossings are collected with a half-open rule so that a line passing exactly
    through a vertex is counted once rather than twice, then sorted along the
    line and paired off under the even-odd rule.
    """
    start_side = edges[:, 1] - edges[:, 0] - offset
    end_side = edges[:, 3] - edges[:, 2] - offset
    crosses = (start_side <= 0) & (end_side > 0) | (end_side <= 0) & (start_side > 0)
    if not crosses.any():
        return []

    crossing = edges[crosses]
    lower = start_side[crosses]
    upper = end_side[crosses]
    alpha = (lower / (lower - upper))[:, None]
    points = crossing[:, :2] + alpha * (crossing[:, 2:] - crossing[:, :2])
    points = points[np.argsort(points[:, 0] + points[:, 1])]
    return [
        (points[index], points[index + 1]) for index in range(0, len(points) - 1, 2)
    ]
