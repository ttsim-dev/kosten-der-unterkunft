"""Write a Plotly figure to a small, self-contained HTML page.

The page has to fit into an email attachment, and the boundaries are what
otherwise blow it up: every choropleth trace carries its own copy, and the
dropdown repeats one more through its hatch overlays. The copies are
byte-identical, so the page binds each collection to one JavaScript
variable and lets every user read it.

The plotly.js bundle stays inlined, so the boundaries and their measures
still draw without a network. Only the CARTO basemap under them needs one.
"""

import json
from pathlib import Path

import plotly.graph_objects as go

COLLECTION_PREFIX = '{"type":"FeatureCollection"'
VARIABLE_PREFIX = "kduGeojson"
_PLOT_CALL = "Plotly.newPlot("


def write_html_with_shared_geojson(figure: go.Figure, path: Path) -> None:
    """Write `figure` as a standalone HTML page, embedding each collection once.

    Args:
        figure: The figure to render.
        path: Destination of the written page.
    """
    html = figure.to_html(include_plotlyjs=True, full_html=True)
    path.write_text(_share_repeated_collections(html), encoding="utf-8")


def _share_repeated_collections(html: str) -> str:
    """Replace every repeated feature collection with a variable reference.

    Only the tail from the plotting call is rewritten: the inlined plotly.js
    ahead of it quotes the call in an error message, and a binding inserted
    there would sit inside a string literal instead of running.
    """
    call = html.rindex(_PLOT_CALL)
    bindings = []
    for index, collection in enumerate(_repeated_collections(html[call:])):
        name = f"{VARIABLE_PREFIX}{index}"
        bindings.append(f"var {name}={collection};")
        html = html[:call] + html[call:].replace(collection, name)
    return html[:call] + "".join(bindings) + html[call:]


def _repeated_collections(script: str) -> list[str]:
    """Return each feature collection literal that occurs more than once."""
    seen: dict[str, int] = {}
    start = script.find(COLLECTION_PREFIX)
    while start != -1:
        collection = script[start : _end_of_object(script, start)]
        seen[collection] = seen.get(collection, 0) + 1
        start = script.find(COLLECTION_PREFIX, start + len(collection))
    return [collection for collection, count in seen.items() if count > 1]


def _end_of_object(script: str, start: int) -> int:
    """Return the index just past the JSON object beginning at `start`."""
    _, length = json.JSONDecoder().raw_decode(script, start)
    return length
