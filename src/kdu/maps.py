"""Join the cleaned tables to the Gemeinde boundaries and draw the choropleth.

The map frame is long, keyed `fid` by `household_size`, so that the household
size is a dimension of the data rather than part of a measure's name. The
figure carries one grey base layer and one measure layer; which measure and
which household size the measure layer shows is set by the controls built in
{mod}`kdu.final.map_controls`.
"""

from dataclasses import dataclass
from typing import Any

import pandas as pd
import plotly.graph_objects as go

from kdu.hatching import build_hatch_geojson
from kdu.measures import MEASURES, MeasureSpec, compute_colour_range

# Where the map opens, and how far in.
GERMANY_CENTRE = {"lat": 51.2, "lon": 10.4}
GERMANY_ZOOM = 4.7

# German number formatting: decimal comma, thousands separator point.
GERMAN_SEPARATORS = ",."

HAERTEFALL_COLUMN = "haertefall_regelung"
HAERTEFALL_HOVER = "<br>Härtefallregelung: zehn Prozent über dem Richtwert möglich"
HAERTEFALL_NOTE = (
    "Schraffur: eigene Härtefallregelung (Berlin: zehn Prozent, nicht enthalten)"
)
SICHERHEITSZUSCHLAG_NOTE = (
    "Ohne schlüssiges Konzept gilt der Wohngeld-Höchstbetrag zuzüglich zehn Prozent "
    "Sicherheitszuschlag (Bundessozialgericht B 4 AS 87/12 R)"
)

GEMEINDEFREIES_GEBIET = "Gemeindefreies Gebiet"

# The market rent comparison names the share above the local cap this, as a
# fraction of the rented stock.
SHARE_ABOVE_CAP_COLUMN = "share_above_local_kdu_cap"
PERCENT = 100

AGS_LENGTH = 8
SOURCE_AGS_LENGTH = 12

# The colours of the ordinal Mietenstufe scale, one per statutory step.
_MIETENSTUFE_COLOURS = (
    "#440154",
    "#443983",
    "#31688e",
    "#21918c",
    "#35b779",
    "#90d743",
    "#fde725",
)


def build_map_frame(
    *,
    geojson: dict[str, Any],
    kdu_caps: pd.DataFrame,
    wohngeld_fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
    gemeinde_types: pd.DataFrame,
    share_of_stock_above_cap: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Join every measure to the boundary features, one row per feature and size.

    Args:
        geojson: Gemeinde feature collection whose features carry `fid` and
            `gem_code`.
        kdu_caps: Local caps keyed `ags` by `household_size`.
        wohngeld_fallback: Statutory benchmark keyed `ags` by `household_size`.
        gemeinden: Gemeinde attributes keyed `ags`.
        gemeinde_types: Frame with `ags` and `gem_type`, marking the
            gemeindefreie Gebiete no KdU document applies to.
        share_of_stock_above_cap: Share of the local rented stock priced above
            the cap, keyed `ags` by `household_size`. Absent when that measure
            has not been computed, in which case its column is all missing.

    Returns:
        One row per boundary feature and household size, sorted by `fid` then
        `household_size`.

    Raises:
        ValueError: If a join drops or duplicates rows, or if a feature has no
            cap row.
    """
    features = _build_feature_table(geojson)
    measures = _join_measure_tables(
        kdu_caps=kdu_caps,
        wohngeld_fallback=wohngeld_fallback,
        share_of_stock_above_cap=share_of_stock_above_cap,
    )

    frame = features.merge(measures, on="ags", how="left", sort=False)
    _fail_if_features_lack_measures(frame)

    attributes = gemeinden.loc[:, ["ags", "district_name"]]
    frame = _merge_without_duplicating(frame, attributes, on="ags")
    types = gemeinde_types.loc[:, ["ags", "gem_type"]]
    frame = _merge_without_duplicating(frame, types, on="ags")

    columns = [
        "fid",
        "ags",
        "household_size",
        "municipality_name",
        "district_name",
        "gem_type",
        HAERTEFALL_COLUMN,
        *[spec.column for spec in MEASURES],
    ]
    return (
        frame.loc[:, columns]
        .sort_values(["fid", "household_size"])
        .reset_index(drop=True)
    )


@dataclass(frozen=True)
class MeasureDisplay:
    """Everything the figure needs to draw one measure at one household size."""

    measure_values: list[float | None]
    """Measure values in feature order."""
    lower: float
    """Lower bound of the colour range."""
    upper: float
    """Upper bound of the colour range."""
    title: str
    """Two-line figure title."""
    colourbar: dict[str, Any]
    """Colour bar specification."""


def build_measure_display(
    *,
    frame: pd.DataFrame,
    spec: MeasureSpec,
    household_size: int,
    vintage: str = "",
) -> MeasureDisplay:
    """Assemble the values, colour range, title and colour bar of one view.

    Args:
        frame: Map frame returned by `build_map_frame`.
        spec: Measure to display.
        household_size: Household size at which to read a size-dependent measure.
        vintage: Range of document effective dates shown in the subtitle.

    Returns:
        The display specification of that measure at that household size.
    """
    view = _select_household_size(frame=frame, spec=spec, household_size=household_size)
    lower, upper = compute_colour_range(view[spec.column], spec)
    return MeasureDisplay(
        measure_values=[
            None if pd.isna(value) else float(value) for value in view[spec.column]
        ],
        lower=lower,
        upper=upper,
        title=_build_title(
            view=view,
            spec=spec,
            household_size=household_size,
            vintage=vintage,
        ),
        colourbar=_build_colourbar(spec=spec, lower=lower, upper=upper),
    )


def build_choropleth(
    *,
    geojson: dict[str, Any],
    frame: pd.DataFrame,
    initial_measure: MeasureSpec,
    initial_household_size: int,
    vintage: str = "",
) -> go.Figure:
    """Build the two-layer choropleth showing one measure at one household size.

    Args:
        geojson: Gemeinde feature collection carrying `fid` properties.
        frame: Map frame returned by `build_map_frame`.
        initial_measure: Measure the map opens on.
        initial_household_size: Household size the map opens on.
        vintage: Range of document effective dates shown in the subtitle.

    Returns:
        A Plotly MapLibre figure whose second trace carries the measure.
    """
    display = build_measure_display(
        frame=frame,
        spec=initial_measure,
        household_size=initial_household_size,
        vintage=vintage,
    )
    view = _select_household_size(
        frame=frame,
        spec=initial_measure,
        household_size=initial_household_size,
    )
    figure = go.Figure(
        data=[
            _build_base_trace(geojson=geojson, view=view),
            go.Choroplethmap(
                geojson=geojson,
                locations=view["fid"],
                featureidkey="properties.fid",
                z=display.measure_values,
                zmin=display.lower,
                zmax=display.upper,
                zmid=initial_measure.diverging_midpoint,
                colorscale=build_colourscale(initial_measure),
                colorbar=display.colourbar,
                customdata=build_customdata(view),
                hovertemplate=build_hovertemplate(initial_measure),
                marker={"opacity": 0.7},
            ),
        ],
    )
    layers = build_hatch_layers(geojson=geojson, frame=frame, spec=initial_measure)
    figure.update_layout(
        title={"text": display.title},
        separators=GERMAN_SEPARATORS,
        map={
            "style": "carto-positron",
            "center": GERMANY_CENTRE,
            "zoom": GERMANY_ZOOM,
            "layers": layers,
        },
        annotations=build_footnotes(layers=layers, spec=initial_measure),
        margin={"r": 0, "t": 60, "l": 0, "b": 0},
    )
    return figure


def build_hatch_layers(
    *,
    geojson: dict[str, Any],
    frame: pd.DataFrame,
    spec: MeasureSpec,
) -> list[dict[str, Any]]:
    """Return the layers hatching Gemeinden with an explicit Härtefallregelung.

    Hatching rather than a fill, so the marked Gemeinden keep showing the
    selected measure underneath. Empty for measures no rent surcharge changes,
    and empty when no Gemeinde is marked.
    """
    if not spec.reflects_kdu_cap:
        return []
    marked = frame.loc[frame[HAERTEFALL_COLUMN], "fid"].drop_duplicates()
    lines = build_hatch_geojson(geojson=geojson, fids=set(marked.astype(int)))
    if not lines["features"]:
        return []
    return [
        {
            "source": lines,
            "type": "line",
            "color": "#1a1a1a",
            "line": {"width": 1},
        },
    ]


def build_footnotes(
    *,
    layers: list[dict[str, Any]],
    spec: MeasureSpec,
) -> list[dict[str, Any]]:
    """Caption what a displayed cap already contains and what it leaves out.

    Two separate surcharges of ten percent bear on a KdU cap and neither is
    legible from the number alone:

    - the Sicherheitszuschlag on the Wohngeldtabelle, already inside the
      Richtwerte of the Kreise without a schlüssiges Konzept
    - Berlin's Härtefallzuschlag, which is not included and marks the hatching
    """
    lines = []
    if layers:
        lines.append(HAERTEFALL_NOTE)
    if spec.reflects_kdu_cap:
        lines.append(SICHERHEITSZUSCHLAG_NOTE)
    if not lines:
        return []
    return [
        {
            "text": "<br>".join(lines),
            "xref": "paper",
            "yref": "paper",
            "x": 0.01,
            "y": 0.01,
            "xanchor": "left",
            "yanchor": "bottom",
            "showarrow": False,
            "align": "left",
            "bgcolor": "rgba(255, 255, 255, 0.8)",
            "font": {"size": 10},
        },
    ]


def build_customdata(view: pd.DataFrame) -> list[list[Any]]:
    """Assemble the per-Gemeinde tooltip fields in feature order.

    The third field is the Härtefall line, empty where the document prints no
    surcharge. An empty string renders as nothing, so one hovertemplate serves
    both cases.
    """
    return [
        [name, district, HAERTEFALL_HOVER if marked else ""]
        for name, district, marked in zip(
            view["municipality_name"],
            view["district_name"],
            view[HAERTEFALL_COLUMN],
            strict=True,
        )
    ]


def build_hovertemplate(spec: MeasureSpec) -> str:
    """Compose the tooltip of a measure."""
    unit = f" {spec.unit}" if spec.unit else ""
    haertefall = "%{customdata[2]}" if spec.reflects_kdu_cap else ""
    return (
        "<b>%{customdata[0]}</b><br>"
        "Kreis: %{customdata[1]}<br>"
        f"{spec.label}: %{{z:{spec.hover_format}}}{unit}"
        f"{haertefall}"
        "<extra></extra>"
    )


def build_colourscale(spec: MeasureSpec) -> str | list[list[float | str]]:
    """Return the colour scale of a measure.

    The Mietenstufe gets a stepped scale with one flat band per statutory step,
    so that neighbouring steps stay distinguishable and no value reads as lying
    between two steps.
    """
    if spec.diverging_midpoint is not None:
        return "RdBu"
    if not spec.is_ordinal:
        return "Viridis"
    scale: list[list[float | str]] = [[0.0, _MIETENSTUFE_COLOURS[0]]]
    for index in range(1, len(_MIETENSTUFE_COLOURS)):
        boundary = (index - 0.5) / (len(_MIETENSTUFE_COLOURS) - 1)
        scale.extend(
            [
                [boundary, _MIETENSTUFE_COLOURS[index - 1]],
                [boundary, _MIETENSTUFE_COLOURS[index]],
            ],
        )
    scale.append([1.0, _MIETENSTUFE_COLOURS[-1]])
    return scale


def describe_household_size(household_size: int) -> str:
    """Return the German label of a household size."""
    if household_size == 1:
        return "1 Person"
    return f"{household_size} Personen"


def count_covered_gemeinden(view: pd.DataFrame, spec: MeasureSpec) -> tuple[int, int]:
    """Count the Gemeinden carrying a value, and those the measure could cover.

    Gemeindefreie Gebiete are excluded from both counts: they are unpopulated
    tracts no KdU document applies to, so counting them would understate
    coverage.
    """
    applies = view["gem_type"].ne(GEMEINDEFREIES_GEBIET)
    return (
        int(view.loc[applies, spec.column].notna().sum()),
        int(applies.sum()),
    )


def _select_household_size(
    *,
    frame: pd.DataFrame,
    spec: MeasureSpec,
    household_size: int,
) -> pd.DataFrame:
    """Return the one row per feature that a measure displays at this size."""
    size = household_size if spec.varies_by_household_size else 1
    view = frame.loc[frame["household_size"].eq(size)]
    return view.sort_values("fid").reset_index(drop=True)


def _build_feature_table(geojson: dict[str, Any]) -> pd.DataFrame:
    """Return `fid`, `ags` and name for every boundary feature, in feature order."""
    return pd.DataFrame(
        {
            "fid": [feature["properties"]["fid"] for feature in geojson["features"]],
            "ags": [
                _derive_ags(feature["properties"]["gem_code"])
                for feature in geojson["features"]
            ],
            "municipality_name": [
                feature["properties"].get("gem_name") for feature in geojson["features"]
            ],
        },
    )


def _join_measure_tables(
    *,
    kdu_caps: pd.DataFrame,
    wohngeld_fallback: pd.DataFrame,
    share_of_stock_above_cap: pd.DataFrame | None,
) -> pd.DataFrame:
    """Derive every measure column, keyed by Gemeinde and household size."""
    keys = ["ags", "household_size"]
    caps = kdu_caps.loc[
        :,
        [*keys, "kdu_cap", "max_area_sqm", HAERTEFALL_COLUMN],
    ]
    benchmark = wohngeld_fallback.loc[
        :,
        [*keys, "mietenstufe", "wohngeld_fallback_cap"],
    ]
    joined = _merge_without_duplicating(caps, benchmark, on=keys)

    measures = joined.loc[:, keys].copy()
    measures["mietenstufe"] = pd.to_numeric(joined["mietenstufe"], errors="coerce")
    measures["kdu_cap"] = pd.to_numeric(joined["kdu_cap"], errors="coerce")
    measures["max_wohnflaeche"] = pd.to_numeric(
        joined["max_area_sqm"],
        errors="coerce",
    )
    measures["kdu_cap_per_sqm"] = measures["kdu_cap"] / measures["max_wohnflaeche"]
    measures["wohngeld_fallback_cap"] = pd.to_numeric(
        joined["wohngeld_fallback_cap"],
        errors="coerce",
    )
    measures["cap_ratio"] = measures["kdu_cap"] / measures["wohngeld_fallback_cap"]
    measures[HAERTEFALL_COLUMN] = _mark_haertefall(joined[HAERTEFALL_COLUMN])
    measures["share_of_stock_above_cap"] = _attach_share_of_stock(
        measures=measures,
        share_of_stock_above_cap=share_of_stock_above_cap,
    )
    return measures


def _attach_share_of_stock(
    *,
    measures: pd.DataFrame,
    share_of_stock_above_cap: pd.DataFrame | None,
) -> pd.Series:
    """Return the share above the cap as a percentage of the local rented stock.

    The market rent comparison reports the share as a fraction and covers only
    the Gemeinden the Zensus prices, so Gemeinden it omits stay missing.
    """
    if share_of_stock_above_cap is None:
        return pd.Series(float("nan"), index=measures.index, dtype=float)
    keys = ["ags", "household_size"]
    supplied = share_of_stock_above_cap.loc[:, [*keys, SHARE_ABOVE_CAP_COLUMN]]
    joined = _merge_without_duplicating(measures.loc[:, keys], supplied, on=keys)
    share = pd.to_numeric(joined[SHARE_ABOVE_CAP_COLUMN], errors="coerce")
    return (share * PERCENT).to_numpy()


def _mark_haertefall(column: pd.Series) -> pd.Series:
    """Mark the Gemeinden whose document prints a quantified Härtefall surcharge."""
    return pd.to_numeric(column, errors="coerce").eq(1).fillna(value=False).astype(bool)


def _derive_ags(value: object) -> str:
    """Reduce a boundary feature's twelve-digit code to the eight-digit AGS."""
    code = value[0] if isinstance(value, list) else value
    text = str(code)
    if len(text) <= AGS_LENGTH:
        return text.zfill(AGS_LENGTH)
    text = text.zfill(SOURCE_AGS_LENGTH)
    return f"{text[:5]}{text[-3:]}"


def _merge_without_duplicating(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    on: str | list[str],
) -> pd.DataFrame:
    """Left-join and fail if the row count changes.

    A many-to-many join inflates row counts silently, and every count and colour
    range downstream would then be wrong without anything visibly breaking.
    """
    merged = left.merge(right, on=on, how="left", sort=False)
    _fail_if_join_duplicated_rows(before=len(left), after=len(merged), on=on)
    return merged


def _fail_if_join_duplicated_rows(
    *, before: int, after: int, on: str | list[str]
) -> None:
    if before != after:
        msg = (
            f"Joining on {on} changed the row count from {before} to {after}; "
            f"the right-hand frame is not unique on those keys"
        )
        raise ValueError(msg)


def _fail_if_features_lack_measures(frame: pd.DataFrame) -> None:
    missing = frame.loc[frame["household_size"].isna(), "ags"].unique().tolist()
    if len(missing) > 0:
        msg = (
            f"Every boundary feature needs a cap row; "
            f"{len(missing)} lack one, for example {missing[:5]}"
        )
        raise ValueError(msg)


def _build_base_trace(
    *,
    geojson: dict[str, Any],
    view: pd.DataFrame,
) -> go.Choroplethmap:
    """Return the flat grey layer that shows Gemeinden without a value."""
    return go.Choroplethmap(
        geojson=geojson,
        locations=view["fid"],
        featureidkey="properties.fid",
        z=[0.0] * len(view),
        zmin=0,
        zmax=1,
        colorscale=[[0, "#d9d9d9"], [1, "#d9d9d9"]],
        showscale=False,
        hoverinfo="skip",
        marker={"opacity": 0.7},
    )


def _build_title(
    *,
    view: pd.DataFrame,
    spec: MeasureSpec,
    household_size: int,
    vintage: str,
) -> str:
    """Compose the two-line title: what the colour shows, then how to read it."""
    headline = spec.headline
    if spec.varies_by_household_size:
        headline = f"{headline}, {describe_household_size(household_size)}"
    covered, total = count_covered_gemeinden(view, spec)
    parts = [
        spec.context,
        f"{_format_count(covered)} von {_format_count(total)} Gemeinden mit Wert",
    ]
    if vintage:
        parts.append(f"Stand der Richtlinien {vintage}")
    return f"{headline}<br><sup>{' · '.join(parts)}</sup>"


def _format_count(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _build_colourbar(
    *,
    spec: MeasureSpec,
    lower: float,
    upper: float,
) -> dict[str, Any]:
    title = spec.unit or "Mietenstufe"
    if spec.is_ordinal:
        return {
            "title": {"text": title},
            "tickmode": "array",
            "tickvals": list(range(1, 8)),
            "ticktext": [str(value) for value in range(1, 8)],
        }
    return {
        "title": {"text": title},
        "tickmode": "array",
        "tickvals": [lower, upper],
        "ticktext": [
            f"≤{_format_bound(lower, spec)}",
            f"≥{_format_bound(upper, spec)}",
        ],
    }


def _format_bound(value: float, spec: MeasureSpec) -> str:
    """Format a colour-bar bound the German way: point thousands, comma decimals."""
    decimals = 2 if spec.hover_format.endswith(".2f") else 0
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
