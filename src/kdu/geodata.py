"""Load and simplify German Gemeinde boundaries.

The boundary source is the OpenDataSoft ``georef-germany-gemeinde``
dataset: ~11k municipalities, each carrying its 12-digit AGS
(``gem_code``) and name. Raw, it is ~58 MB — too heavy to render in a
notebook — so {func}`simplify_feature_collection` snaps coordinates to a
coarse grid, shrinking it to a few MB while keeping shared borders
aligned (identical shared vertices round identically).

Loading stamps each feature with a unique integer ``fid``: region names
are not unique in Germany, so the choropleth join must key on ``fid``
(or, for real data, on the AGS) rather than the name.
"""

import itertools
import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

Coordinate = tuple[float, float]
Ring = list[list[float]]

# Fewest points a closed ring can have: three corners plus the repeated first.
MIN_CLOSED_RING_POINTS = 4

# Cross product below which three coordinates count as one straight edge.
COLLINEAR_TOLERANCE = 1e-12


def load_geojson(path: Path) -> dict[str, Any]:
    """Load a GeoJSON file and stamp each feature with a unique ``fid``."""
    geojson = json.loads(path.read_text(encoding="utf-8"))
    for index, feature in enumerate(geojson["features"]):
        feature["properties"] = {**feature["properties"], "fid": index}
    return geojson


def simplify_feature_collection(
    geojson: dict[str, Any],
    *,
    decimals: int,
) -> dict[str, Any]:
    """Round every coordinate to ``decimals`` places and drop the slack.

    Snapping to a grid (``decimals=2`` ≈ 1 km) collapses runs of points
    that map to the same grid cell. Features whose geometry degenerates
    below a drawable polygon are dropped.
    """
    features = []
    for feature in geojson["features"]:
        geometry = _simplify_geometry(feature.get("geometry"), decimals=decimals)
        if geometry is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": feature["properties"],
            },
        )
    return {"type": "FeatureCollection", "features": features}


def _simplify_geometry(
    geometry: dict[str, Any] | None,
    *,
    decimals: int,
) -> dict[str, Any] | None:
    if geometry is None:
        return None
    kind = geometry["type"]
    if kind == "Polygon":
        rings = _clean_polygon(geometry["coordinates"], decimals=decimals)
        return {"type": "Polygon", "coordinates": rings} if rings else None
    if kind == "MultiPolygon":
        polygons = [
            cleaned
            for polygon in geometry["coordinates"]
            if (cleaned := _clean_polygon(polygon, decimals=decimals))
        ]
        return {"type": "MultiPolygon", "coordinates": polygons} if polygons else None
    msg = f"unsupported geometry type: {kind}"
    raise ValueError(msg)


def _clean_polygon(
    polygon: Sequence[Sequence[Sequence[float]]],
    *,
    decimals: int,
) -> list[Ring]:
    return [ring for raw in polygon if (ring := round_ring(raw, decimals=decimals))]


def round_ring(
    ring: Sequence[Sequence[float]],
    *,
    decimals: int,
) -> Ring | None:
    """Round a ring's coordinates and drop the points the shape does not need.

    Two kinds of point go: consecutive duplicates, which the grid snap
    creates wherever a run of vertices falls into one cell, and vertices
    lying exactly on the straight line between their neighbours, which
    the snap leaves behind along every axis-parallel edge. Neither
    changes the outline, so shared borders stay aligned.

    Returns a closed ring (first point repeated last) with at least four
    points, or ``None`` if the ring collapses below that.
    """
    cleaned: Ring = []
    previous: Coordinate | None = None
    for point in ring:
        rounded: Coordinate = (round(point[0], decimals), round(point[1], decimals))
        if rounded != previous:
            cleaned.append([rounded[0], rounded[1]])
        previous = rounded
    if cleaned and cleaned[0] != cleaned[-1]:
        cleaned.append(cleaned[0])
    if len(cleaned) < MIN_CLOSED_RING_POINTS:
        return None
    return _drop_collinear_points(cleaned)


def _drop_collinear_points(ring: Ring) -> Ring:
    """Remove every vertex that sits on the line between its neighbours.

    A ring that is one straight line throughout would lose its every point,
    which would drop the Gemeinde from the map, so such a ring is left alone.
    """
    kept: Ring = [ring[0]]
    for point, following in itertools.pairwise(ring[1:]):
        if not _is_collinear(kept[-1], point, following):
            kept.append(point)
    kept.append(ring[-1])
    return kept if len(kept) >= MIN_CLOSED_RING_POINTS else ring


def _is_collinear(
    first: Sequence[float],
    second: Sequence[float],
    third: Sequence[float],
) -> bool:
    cross = (second[0] - first[0]) * (third[1] - first[1]) - (second[1] - first[1]) * (
        third[0] - first[0]
    )
    return math.isclose(cross, 0.0, abs_tol=COLLINEAR_TOLERANCE)
