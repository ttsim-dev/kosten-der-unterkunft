"""Write the interactive Gemeinde choropleth."""

from pathlib import Path
from typing import Annotated, cast

import pandas as pd
from pytask import Product

from kdu.config import DATA_CATALOG
from kdu.geodata import load_geojson
from kdu.html import write_html_with_shared_geojson
from kdu.maps import build_choropleth, build_map_frame

_GEMEINDEN_GEOJSON = cast("Path", DATA_CATALOG["gemeinden_geojson"])
_KDU_GEMEINDEN = cast("Path", DATA_CATALOG["kdu_gemeinden"])
_GEMEINDE_LOOKUP = cast("Path", DATA_CATALOG["gemeinde_lookup"])
_GERMANY_MAP = cast("Path", DATA_CATALOG["germany_map"])


def task_map(
    gemeinden_geojson: Path = _GEMEINDEN_GEOJSON,
    kdu_gemeinden_file: Path = _KDU_GEMEINDEN,
    gemeinde_lookup_file: Path = _GEMEINDE_LOOKUP,
    germany_map_file: Annotated[Path, Product] = _GERMANY_MAP,
) -> None:
    """Read the map inputs, build the choropleth, and write it as HTML."""
    geojson = load_geojson(gemeinden_geojson)
    kdu_gemeinden = pd.read_csv(
        kdu_gemeinden_file,
        dtype=str,
        keep_default_na=False,
    )
    gemeinde_lookup = pd.read_feather(gemeinde_lookup_file)

    frame = build_map_frame(geojson, kdu_gemeinden, gemeinde_lookup)
    figure = build_choropleth(
        geojson,
        frame,
        vintage=_describe_vintage(kdu_gemeinden["valid_from"]),
    )

    write_html_with_shared_geojson(figure, germany_map_file)


def _describe_vintage(valid_from: pd.Series) -> str:
    """Summarise the effective dates of the underlying documents as a year range."""
    years = pd.to_numeric(valid_from.str.slice(0, 4), errors="coerce").dropna()
    if years.empty:
        return ""
    first, last = int(years.min()), int(years.max())
    return str(first) if first == last else f"{first}-{last}"
