"""Write the Gemeinde choropleth, once with every measure and once per measure."""

from pathlib import Path
from typing import Annotated, Any

import pandas as pd
from pytask import Product

from kdu.config import (
    HOUSEHOLD_SIZES,
    MAP_MEASURES,
    PRESENTATION_MAP_MEASURES,
    catalog_path,
)
from kdu.figure_export import write_presentation_png
from kdu.final.map_controls import build_control_script
from kdu.geodata import load_geojson
from kdu.maps import build_choropleth, build_map_frame
from kdu.measures import MEASURES, MeasureSpec, get_measure

# The measure and household size the map opens on.
INITIAL_MEASURE = "cap_ratio"
INITIAL_HOUSEHOLD_SIZE = 1

# Plotly is loaded from a content delivery network rather than inlined, which
# keeps roughly three and a half megabytes out of every one of the eight files.
PLOTLY_SOURCE = "cdn"

_GEMEINDEN_GEOJSON = catalog_path("gemeinden_geojson")
_GEMEINDE_LOOKUP = catalog_path("gemeinde_lookup")
_KDU_CAPS = catalog_path("kdu_caps")
_WOHNGELD_FALLBACK = catalog_path("wohngeld_fallback")
_GEMEINDEN = catalog_path("gemeinden")
_GERMANY_MAP = catalog_path("germany_map")
_STANDALONE_MAPS = {
    measure: catalog_path(f"germany_map_{measure}") for measure in MAP_MEASURES
}
_PRESENTATION_MAPS = {
    measure: catalog_path(f"germany_map_{measure}_png")
    for measure in PRESENTATION_MAP_MEASURES
}

# The share of the local rented stock above the cap, produced by the market
# rent comparison.
_SHARE_OF_STOCK_ABOVE_CAP = catalog_path("share_of_stock_above_cap_gemeinde")


def task_map(
    gemeinden_geojson: Path = _GEMEINDEN_GEOJSON,
    gemeinde_lookup_file: Path = _GEMEINDE_LOOKUP,
    kdu_caps_file: Path = _KDU_CAPS,
    wohngeld_fallback_file: Path = _WOHNGELD_FALLBACK,
    gemeinden_file: Path = _GEMEINDEN,
    share_of_stock_above_cap_file: Path = _SHARE_OF_STOCK_ABOVE_CAP,
    germany_map_file: Annotated[Path, Product] = _GERMANY_MAP,
    standalone_map_files: Annotated[dict[str, Path], Product] = _STANDALONE_MAPS,
    presentation_map_files: Annotated[dict[str, Path], Product] = _PRESENTATION_MAPS,
) -> None:
    """Read the map inputs, build the choropleth, and write every map file."""
    geojson = load_geojson(gemeinden_geojson)
    kdu_caps = pd.read_parquet(kdu_caps_file)
    frame = build_map_frame(
        geojson=geojson,
        kdu_caps=kdu_caps,
        wohngeld_fallback=pd.read_parquet(wohngeld_fallback_file),
        gemeinden=pd.read_parquet(gemeinden_file),
        gemeinde_types=pd.read_feather(gemeinde_lookup_file),
        share_of_stock_above_cap=pd.read_parquet(share_of_stock_above_cap_file),
    )
    vintage = _describe_vintage(kdu_caps["valid_from"])

    _write_map(
        path=germany_map_file,
        geojson=geojson,
        frame=frame,
        measures=MEASURES,
        vintage=vintage,
    )
    for measure, path in standalone_map_files.items():
        _write_map(
            path=path,
            png_path=presentation_map_files.get(measure),
            geojson=geojson,
            frame=frame,
            measures=(get_measure(measure),),
            vintage=vintage,
        )


def _write_map(
    *,
    path: Path,
    geojson: dict[str, Any],
    frame: pd.DataFrame,
    measures: tuple[MeasureSpec, ...],
    vintage: str,
    png_path: Path | None = None,
) -> None:
    """Write one choropleth offering the given measures, and a static image of it.

    Args:
        path: Destination of the interactive HTML file.
        geojson: Gemeinde feature collection carrying `fid` properties.
        frame: Map frame the choropleth reads its values from.
        measures: Measures the map offers; the first is the one it opens on
            unless several are offered, in which case `INITIAL_MEASURE` is.
        vintage: Range of document effective dates shown in the subtitle.
        png_path: Where to also write a static image for the presentation, or
            `None` for a map the deck does not show.

    """
    initial_measure = get_measure(INITIAL_MEASURE) if len(measures) > 1 else measures[0]
    figure = build_choropleth(
        geojson=geojson,
        frame=frame,
        initial_measure=initial_measure,
        initial_household_size=INITIAL_HOUSEHOLD_SIZE,
        vintage=vintage,
    )
    script = build_control_script(
        geojson=geojson,
        frame=frame,
        measures=measures,
        household_sizes=HOUSEHOLD_SIZES,
        initial_measure=initial_measure,
        initial_household_size=INITIAL_HOUSEHOLD_SIZE,
        vintage=vintage,
    )
    figure.write_html(path, include_plotlyjs=PLOTLY_SOURCE, post_script=script)
    if png_path is not None:
        write_presentation_png(figure, png_path)


def _describe_vintage(valid_from: pd.Series) -> str:
    """Summarise the effective dates of the underlying documents as a year range."""
    years = pd.to_numeric(
        valid_from.astype("string").str.slice(0, 4),
        errors="coerce",
    ).dropna()
    if years.empty:
        return ""
    first, last = int(years.min()), int(years.max())
    return str(first) if first == last else f"{first}-{last}"
