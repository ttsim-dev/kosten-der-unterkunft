"""Build a measure-selectable Gemeinde choropleth from KdU data."""

from typing import Any

import pandas as pd
import plotly.graph_objects as go

from kdu.measures import MEASURES, MeasureSpec, compute_colour_range

GERMANY_CENTER = {"lat": 51.2, "lon": 10.4}
AGS_LENGTH = 8
SOURCE_AGS_LENGTH = 12


def build_map_frame(
    geojson: dict[str, Any],
    kdu: pd.DataFrame,
    lookup: pd.DataFrame,
) -> pd.DataFrame:
    """Join KdU measures and municipality metadata to features by AGS.

    Args:
        geojson: Gemeinde feature collection carrying `fid` and `gem_code`.
        kdu: Completed KdU data keyed by eight-digit `ags_gemeinde`.
        lookup: Gemeinde lookup containing `ags`, `kreis`, and `gem_type`.

    Returns:
        One row per GeoJSON feature, preserving feature order.

    Raises:
        ValueError: If a GeoJSON feature has no corresponding KdU row.
    """
    features = pd.DataFrame(
        {
            "fid": [feature["properties"]["fid"] for feature in geojson["features"]],
            "ags": [
                _derive_ags_8(feature["properties"]["gem_code"])
                for feature in geojson["features"]
            ],
            "name": [
                feature["properties"].get("gem_name") for feature in geojson["features"]
            ],
        },
    )
    measure_columns = [spec.column for spec in MEASURES]
    kdu_measures = pd.DataFrame(index=kdu.index)
    kdu_measures["ags"] = kdu["ags_gemeinde"].map(_normalise_ags_8)
    for column in measure_columns:
        kdu_measures[column] = pd.to_numeric(kdu[column], errors="coerce").astype(float)

    joined = features.merge(
        kdu_measures,
        on="ags",
        how="left",
        sort=False,
        validate="one_to_one",
        indicator="_kdu_join",
    )
    _fail_if_kdu_rows_are_missing(joined)

    lookup_names = pd.DataFrame(index=lookup.index)
    lookup_names["ags"] = lookup["ags"].map(_derive_ags_8)
    lookup_names["kreis"] = lookup["kreis"]
    lookup_names["gem_type"] = lookup["gem_type"]
    joined = joined.merge(
        lookup_names,
        on="ags",
        how="left",
        sort=False,
        validate="one_to_one",
    )
    columns = ["fid", "ags", "name", "kreis", "gem_type", *measure_columns]
    return joined.loc[:, columns].reset_index(drop=True)


def build_choropleth(
    geojson: dict[str, Any],
    frame: pd.DataFrame,
    *,
    initial_measure: str = MEASURES[0].key,
    vintage: str = "",
) -> go.Figure:
    """Build an interactive Gemeinde choropleth with a measure dropdown.

    Args:
        geojson: Gemeinde feature collection carrying `fid` properties.
        frame: Map frame returned by `build_map_frame`.
        initial_measure: Stable key of the measure shown initially.
        vintage: Range of document effective dates, e.g. `"2019-2026"`, shown in the
            subtitle. Omitted when empty.

    Returns:
        A two-layer Plotly MapLibre figure.

    Raises:
        ValueError: If `initial_measure` is not in `MEASURES` or a measure has no
            published values.
    """
    initial_spec = _get_measure(initial_measure)
    figure = go.Figure(
        data=[
            _build_base_trace(geojson=geojson, frame=frame),
            _build_measure_trace(
                geojson=geojson,
                frame=frame,
                spec=initial_spec,
            ),
        ],
    )
    buttons = [
        _build_measure_button(frame=frame, spec=spec, vintage=vintage)
        for spec in MEASURES
    ]
    figure.update_layout(
        title={"text": _build_title(frame=frame, spec=initial_spec, vintage=vintage)},
        map={"style": "carto-positron", "center": GERMANY_CENTER, "zoom": 4.7},
        margin={"r": 0, "t": 40, "l": 0, "b": 0},
        updatemenus=[{"buttons": buttons}],
    )
    return figure


def _derive_ags_8(value: object) -> str:
    code = value[0] if isinstance(value, list) else value
    text = str(code)
    if len(text) <= AGS_LENGTH:
        return text.zfill(AGS_LENGTH)
    text = text.zfill(SOURCE_AGS_LENGTH)
    return f"{text[:5]}{text[-3:]}"


def _normalise_ags_8(value: object) -> str:
    return str(value).zfill(AGS_LENGTH)


def _fail_if_kdu_rows_are_missing(joined: pd.DataFrame) -> None:
    missing_ags = joined.loc[joined["_kdu_join"].eq("left_only"), "ags"].tolist()
    if missing_ags:
        msg = f"Every Gemeinde needs a KdU row; missing AGS: {missing_ags[:5]}"
        raise ValueError(msg)


def _get_measure(key: str) -> MeasureSpec:
    try:
        return next(spec for spec in MEASURES if spec.key == key)
    except StopIteration:
        msg = f"Unknown measure: {key}"
        raise ValueError(msg) from None


def _build_base_trace(
    *,
    geojson: dict[str, Any],
    frame: pd.DataFrame,
) -> go.Choroplethmap:
    return go.Choroplethmap(
        geojson=geojson,
        locations=frame["fid"],
        featureidkey="properties.fid",
        z=[0.0] * len(frame),
        zmin=0,
        zmax=1,
        colorscale=[[0, "#d9d9d9"], [1, "#d9d9d9"]],
        showscale=False,
        hoverinfo="skip",
        marker={"opacity": 0.7},
    )


def _build_measure_trace(
    *,
    geojson: dict[str, Any],
    frame: pd.DataFrame,
    spec: MeasureSpec,
) -> go.Choroplethmap:
    lower, upper = compute_colour_range(values=frame[spec.column], spec=spec)
    return go.Choroplethmap(
        geojson=geojson,
        locations=frame["fid"],
        featureidkey="properties.fid",
        z=frame[spec.column],
        customdata=_build_customdata(frame=frame, spec=spec),
        hovertemplate=_build_hovertemplate(spec),
        zmin=lower,
        zmax=upper,
        colorscale=_build_colorscale(spec),
        colorbar=_build_colorbar(spec=spec, lower=lower, upper=upper),
        marker={"opacity": 0.7},
    )


def _build_measure_button(
    *,
    frame: pd.DataFrame,
    spec: MeasureSpec,
    vintage: str = "",
) -> dict[str, Any]:
    lower, upper = compute_colour_range(values=frame[spec.column], spec=spec)
    trace_update = {
        "z": [frame[spec.column].tolist()],
        "customdata": [_build_customdata(frame=frame, spec=spec)],
        "hovertemplate": [_build_hovertemplate(spec)],
        "zmin": [lower],
        "zmax": [upper],
        "colorscale": [_build_colorscale(spec)],
        "colorbar": [_build_colorbar(spec=spec, lower=lower, upper=upper)],
    }
    return {
        "label": spec.label,
        "method": "update",
        "args": [
            trace_update,
            {"title.text": _build_title(frame=frame, spec=spec, vintage=vintage)},
            [1],
        ],
    }


def _build_customdata(*, frame: pd.DataFrame, spec: MeasureSpec) -> list[list[Any]]:
    return [
        [name, kreis, value]
        for name, kreis, value in zip(
            frame["name"],
            frame["kreis"],
            frame[spec.column],
            strict=True,
        )
    ]


def _build_hovertemplate(spec: MeasureSpec) -> str:
    unit = f" {spec.colourbar_title or spec.unit}" if spec.unit else ""
    return (
        "<b>%{customdata[0]}</b><br>"
        "Kreis: %{customdata[1]}<br>"
        f"{_hover_label(spec)}: %{{customdata[2]:{spec.hover_format}}}{unit}"
        "<extra></extra>"
    )


def _hover_label(spec: MeasureSpec) -> str:
    """Strip the dropdown's group prefix so tooltips stay short."""
    return spec.label.split(" · ", maxsplit=1)[-1]


def _build_title(
    *,
    frame: pd.DataFrame,
    spec: MeasureSpec,
    vintage: str = "",
) -> str:
    """Compose the two-line figure title.

    The first line names what the colour shows, the second gives the legal basis,
    the unit, how many Gemeinden carry a value, and why the rest do not.
    """
    headline = spec.headline or spec.label
    parts = [spec.context] if spec.context else []
    parts.append(_describe_coverage(frame=frame, spec=spec))
    if vintage:
        parts.append(f"Stand der Richtlinien {vintage}")
    return f"{headline}<br><sup>{' · '.join(parts)}</sup>"


def _describe_coverage(*, frame: pd.DataFrame, spec: MeasureSpec) -> str:
    """Split the Gemeinden into those with a value and the reasons the rest lack one."""
    is_gemeinde = frame["gem_type"].ne("Gemeindefreies Gebiet")
    present = frame.loc[is_gemeinde, spec.column].notna()
    denominator = int(is_gemeinde.sum())
    covered = int(present.sum())
    pieces = [
        f"{_format_count(covered)} von {_format_count(denominator)} Gemeinden mit Wert",
    ]
    remainder = denominator - covered
    if spec.counterpart_column and spec.counterpart_column in frame.columns:
        counterpart = int(
            (~present & frame.loc[is_gemeinde, spec.counterpart_column].notna()).sum(),
        )
        if counterpart:
            pieces.append(f"{_format_count(counterpart)} {spec.counterpart_text}")
            remainder -= counterpart
    if remainder:
        pieces.append(f"{_format_count(remainder)} ohne Angabe")
    return ", ".join(pieces)


def _format_count(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _build_colorscale(spec: MeasureSpec) -> str | list[list[float | str]]:
    if spec.is_diverging:
        return "RdBu"
    if not spec.is_ordinal:
        return "Viridis"
    colours = (
        "#440154",
        "#443983",
        "#31688e",
        "#21918c",
        "#35b779",
        "#90d743",
        "#fde725",
    )
    scale: list[list[float | str]] = [[0.0, colours[0]]]
    for index in range(1, len(colours)):
        boundary = (index - 0.5) / (len(colours) - 1)
        scale.extend([[boundary, colours[index - 1]], [boundary, colours[index]]])
    scale.append([1.0, colours[-1]])
    return scale


def _build_colorbar(
    *,
    spec: MeasureSpec,
    lower: float,
    upper: float,
) -> dict[str, Any]:
    title = spec.colourbar_title or spec.unit or "Mietstufe"
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
            f"≤{_format_tick(lower, spec)}",
            f"≥{_format_tick(upper, spec)}",
        ],
    }


def _format_tick(value: float, spec: MeasureSpec) -> str:
    decimals = 2 if spec.hover_format.endswith(".2f") else 0
    return f"{value:,.{decimals}f}"
