"""Build a Gemeinde choropleth from placeholder data.

{func}`build_fake_frame` invents one random value per municipality so
the rendering pipeline can be exercised end to end. The real task swaps
it for actual data joined on ``fid`` (or the AGS) — the map code below
does not change.
"""

from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Roughly the geographic centre of Germany, for the map's initial view.
GERMANY_CENTER = {"lat": 51.2, "lon": 10.4}


def build_fake_frame(geojson: dict[str, Any], *, seed: int = 20260608) -> pd.DataFrame:
    """Build a one-row-per-feature frame with a random placeholder value."""
    rng = np.random.default_rng(seed=seed)
    records = [
        {
            "fid": feature["properties"]["fid"],
            "name": feature["properties"].get("gem_name"),
            "ags": feature["properties"].get("gem_code"),
        }
        for feature in geojson["features"]
    ]
    frame = pd.DataFrame(records)
    frame["value"] = rng.uniform(0, 100, size=len(frame))
    return frame


def build_choropleth(
    geojson: dict[str, Any],
    frame: pd.DataFrame,
    *,
    title: str = "Germany by Gemeinde — placeholder data",
) -> go.Figure:
    """Render the Gemeinde choropleth on a MapLibre base map.

    Uses {func}`plotly.express.choropleth_map`, which draws all ~11k
    polygons as a single GPU-accelerated layer — far smoother than the
    SVG choropleth at this polygon count.
    """
    figure = px.choropleth_map(
        frame,
        geojson=geojson,
        locations="fid",
        featureidkey="properties.fid",
        color="value",
        color_continuous_scale="Viridis",
        hover_name="name",
        hover_data={"fid": False, "ags": True, "value": ":.1f"},
        center=GERMANY_CENTER,
        zoom=4.7,
        map_style="carto-positron",
        opacity=0.7,
        title=title,
    )
    figure.update_layout(margin={"r": 0, "t": 40, "l": 0, "b": 0})
    return figure
