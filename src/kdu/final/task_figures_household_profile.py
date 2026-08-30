"""The four §10.4 figures of P0.5, plus the D7 tilt-distribution figure.

The styling here is deliberately austere and separate from the exploratory
choropleth of `maps.py` (D12): grey carries the data, one accent colour carries
the WoGG-linked Gemeinden that D7 requires to stay visible, and every reference
line is labelled on the plot rather than in a legend.
"""

from pathlib import Path
from typing import Annotated, Any, cast

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pytask import Product

from kdu.analysis.household_profile import (
    DECILE_MOVE_THRESHOLD,
    HEADLINE_TILT_SIZE,
    HOUSEHOLD_PROFILE_GEMEINDE,
    HOUSEHOLD_PROFILE_GEMEINDE_H5,
    HOUSEHOLD_PROFILE_MARGINAL,
    N_DECILES,
    TILT_REFERENCE_SIZE,
    ZERO_TILT_TOLERANCE,
    check_wogg_linked_tilt,
    decile_transition_matrix,
    share_moving_at_least_deciles,
    spearman_correlation,
)
from kdu.config import DATA_CATALOG, FIGURES
from kdu.final.manifest import register_result
from kdu.geodata import load_geojson

_GEMEINDEN_GEOJSON = cast("Path", DATA_CATALOG["gemeinden_geojson"])

# Figure files, in the order §10.4 lists them; the last is the D7 obligation.
FIGURE_TILT_SCATTER = FIGURES / "fig_household_profile_tilt_scatter.html"
FIGURE_MARGINAL = FIGURES / "fig_household_profile_marginal_amounts.html"
FIGURE_TILT_MAP = FIGURES / "fig_household_profile_tilt_map.html"
FIGURE_TRANSITION = FIGURES / "fig_household_profile_decile_transition.html"
FIGURE_TILT_DISTRIBUTION = FIGURES / "fig_household_profile_tilt_distribution.html"

# Grey carries the data; the accent is reserved for the WoGG-linked Gemeinden.
GREY = "#8c8c8c"
DARK_GREY = "#3d3d3d"
ACCENT = "#c1121f"
LIGHT_GREY = "#e0e0e0"
# Diverging scale for the tilt map, neutral at zero.
TILT_COLORSCALE: tuple[tuple[float, str], ...] = (
    (0.0, "#2166ac"),
    (0.5, "#f7f7f7"),
    (1.0, "#b2182b"),
)
# Tilt range the map colour scale spans; larger values saturate rather than
# stretch the scale, and no observation is dropped for being extreme (§18).
TILT_COLOUR_LIMIT = 0.15
# Bin width of the tilt histograms, in log points.
TILT_BIN_WIDTH = 0.005
# Length of an eight-digit Gemeinde AGS.
AGS_LENGTH = 8
# Centre and zoom of every map in this module.
GERMANY_CENTER = {"lat": 51.2, "lon": 10.4}
GERMANY_ZOOM = 4.7

_MODULE = "P0.5"
_DATASET = "household_profile_gemeinde.parquet"
_SCRIPT = "src/kdu/final/task_figures_household_profile.py"
_CAP_LIMITATION = (
    "K is the maximum recognisable Bruttokaltmiete, not an actual KdU payment, "
    "and the comparison is conditional on the cap being in force (D11)."
)


def task_figures_household_profile(
    gemeinde_file: Path = HOUSEHOLD_PROFILE_GEMEINDE,
    gemeinde_h5_file: Path = HOUSEHOLD_PROFILE_GEMEINDE_H5,
    marginal_file: Path = HOUSEHOLD_PROFILE_MARGINAL,
    gemeinden_geojson: Path = _GEMEINDEN_GEOJSON,
    scatter_file: Annotated[Path, Product] = FIGURE_TILT_SCATTER,
    marginal_figure_file: Annotated[Path, Product] = FIGURE_MARGINAL,
    map_file: Annotated[Path, Product] = FIGURE_TILT_MAP,
    transition_file: Annotated[Path, Product] = FIGURE_TRANSITION,
    distribution_file: Annotated[Path, Product] = FIGURE_TILT_DISTRIBUTION,
) -> None:
    """Write the §10.4 figures and register each in the results manifest."""
    gemeinde = pd.read_parquet(gemeinde_file)
    gemeinde_h5 = pd.read_parquet(gemeinde_h5_file)
    marginal = pd.read_parquet(marginal_file)
    geojson = load_geojson(gemeinden_geojson)

    scatter_file.parent.mkdir(parents=True, exist_ok=True)
    build_tilt_scatter(gemeinde).write_html(scatter_file)
    build_marginal_figure(marginal).write_html(marginal_figure_file)
    build_tilt_map(geojson, gemeinde).write_html(map_file)
    build_transition_figure(gemeinde).write_html(transition_file)
    build_tilt_distribution(gemeinde, gemeinde_h5).write_html(distribution_file)

    _register_all(gemeinde, gemeinde_h5, marginal)


def build_tilt_scatter(gemeinde: pd.DataFrame) -> go.Figure:
    """Plot the average relative KdU level against the Familien-Tilt.

    Args:
        gemeinde: Per-Gemeinde frame with `mean_log_relative_level`,
            `tilt_h4` and `wogg_linked_flag`.

    Returns:
        A scatter with the WoGG-linked Gemeinden drawn on top in the accent
        colour, so the horizontal line they form at F=0 is unmistakable.

    """
    tilt_column = f"tilt_h{HEADLINE_TILT_SIZE}"
    frame = gemeinde.loc[
        gemeinde[tilt_column].notna() & gemeinde["mean_log_relative_level"].notna()
    ]
    flagged = frame["wogg_linked_flag"]
    figure = go.Figure(
        [
            _scatter_trace(
                frame.loc[~flagged],
                tilt_column,
                name="Not WoGG-linked",
                colour=GREY,
            ),
            _scatter_trace(
                frame.loc[flagged],
                tilt_column,
                name="WoGG-linked (§ 12 WoGG plus Sicherheitszuschlag)",
                colour=ACCENT,
            ),
        ],
    )
    figure.add_hline(y=0, line={"color": DARK_GREY, "width": 1})
    figure.add_vline(x=0, line={"color": DARK_GREY, "width": 1})
    _annotate(
        figure,
        (0.02, 0.97, "F &gt; 0: cap relatively higher for four-person households"),
        (0.02, 0.03, "F &lt; 0: cap relatively higher for singles"),
    )
    _style(
        figure,
        title=(
            f"Relative KdU level and Familien-Tilt, {len(frame):,} Gemeinden "
            f"(h=1-4 balanced sample)"
        ),
        x_title="Average relative KdU level, mean of log(K/W) over h=1-4",
        y_title=f"Familien-Tilt F = log(K{HEADLINE_TILT_SIZE}/W"
        f"{HEADLINE_TILT_SIZE}) - log(K1/W1)",
    )
    return figure


def build_marginal_figure(marginal: pd.DataFrame) -> go.Figure:
    """Show the distribution of `ΔK` per additional person, one facet per size.

    The statutory Wohngeld step is drawn as a labelled reference line in each
    facet, so the local schedule is read against the benchmark it is compared
    with rather than against nothing.
    """
    sizes = sorted(
        size
        for size in marginal["household_size"].unique()
        if size > marginal["household_size"].min()
    )
    figure = make_subplots(
        rows=len(sizes),
        cols=1,
        shared_xaxes=True,
        subplot_titles=[f"{size}. person in the Bedarfsgemeinschaft" for size in sizes],
        vertical_spacing=0.06,
    )
    for row, size in enumerate(sizes, start=1):
        block = marginal.loc[marginal["household_size"] == size]
        figure.add_trace(
            go.Histogram(
                x=block["kdu_step"],
                xbins={"start": 0, "end": 400, "size": 5},
                marker={"color": GREY},
                showlegend=False,
                hovertemplate="ΔK %{x:.0f} EUR<br>%{y} Gemeinden<extra></extra>",
            ),
            row=row,
            col=1,
        )
        median_wogg = float(block["wogg_step"].median())
        figure.add_vline(
            x=median_wogg,
            line={"color": ACCENT, "width": 1.5, "dash": "dash"},
            row=row,
            col=1,
        )
        figure.add_annotation(
            x=median_wogg,
            y=1,
            yref=f"y{row} domain" if row > 1 else "y domain",
            text=f"median statutory step {median_wogg:.0f} EUR",
            showarrow=False,
            xanchor="left",
            yanchor="top",
            font={"size": 11, "color": ACCENT},
            row=row,
            col=1,
        )
    _style(
        figure,
        title=(
            "Marginal KdU amount per additional person, "
            f"{int(marginal['ags'].nunique()):,} Gemeinden"
        ),
        x_title="ΔK = K(h) - K(h-1), EUR per month",
        y_title="Gemeinden",
    )
    figure.update_layout(height=240 * len(sizes))
    return figure


def build_tilt_map(geojson: dict[str, Any], gemeinde: pd.DataFrame) -> go.Figure:
    """Map the Familien-Tilt, on a diverging scale neutral at zero."""
    tilt_column = f"tilt_h{HEADLINE_TILT_SIZE}"
    frame = _map_frame(geojson, gemeinde[tilt_column])
    figure = go.Figure(
        [
            go.Choroplethmap(
                geojson=geojson,
                locations=frame["fid"],
                featureidkey="properties.fid",
                z=[0.0] * len(frame),
                zmin=0,
                zmax=1,
                colorscale=[[0, LIGHT_GREY], [1, LIGHT_GREY]],
                showscale=False,
                hoverinfo="skip",
            ),
            go.Choroplethmap(
                geojson=geojson,
                locations=frame["fid"],
                featureidkey="properties.fid",
                z=frame["value"],
                zmin=-TILT_COLOUR_LIMIT,
                zmax=TILT_COLOUR_LIMIT,
                colorscale=[list(stop) for stop in TILT_COLORSCALE],
                colorbar={
                    "title": {"text": "F", "side": "right"},
                    "thickness": 12,
                },
                customdata=frame[["name"]].to_numpy(),
                hovertemplate="%{customdata[0]}<br>F = %{z:+.3f}<extra></extra>",
                marker={"opacity": 0.85},
            ),
        ],
    )
    figure.update_layout(
        title={
            "text": (
                f"Familien-Tilt F = log(K{HEADLINE_TILT_SIZE}/W"
                f"{HEADLINE_TILT_SIZE}) - log(K1/W1), "
                f"{int(gemeinde[tilt_column].notna().sum()):,} Gemeinden"
            ),
        },
        map={
            "style": "carto-positron",
            "center": GERMANY_CENTER,
            "zoom": GERMANY_ZOOM,
        },
        margin={"r": 0, "t": 60, "l": 0, "b": 40},
        annotations=[
            {
                "text": (
                    "Grey: no Bruttokaltmiete cap, or no statutory Mietenstufe and "
                    "therefore no Wohngeld benchmark (119 Gemeinden). "
                    f"Values beyond ±{TILT_COLOUR_LIMIT:.2f} saturate the scale."
                ),
                "showarrow": False,
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": -0.02,
                "xanchor": "left",
                "font": {"size": 11, "color": DARK_GREY},
            },
        ],
    )
    return figure


def build_transition_figure(gemeinde: pd.DataFrame) -> go.Figure:
    """Draw the decile transition matrix between the h=1 and h=4 cap rankings."""
    matrix = decile_transition_matrix(
        gemeinde[f"log_relative_level_h{TILT_REFERENCE_SIZE}"],
        gemeinde[f"log_relative_level_h{HEADLINE_TILT_SIZE}"],
    )
    figure = go.Figure(
        go.Heatmap(
            z=matrix.to_numpy(),
            x=list(matrix.columns),
            y=list(matrix.index),
            colorscale=[[0, "#ffffff"], [1, DARK_GREY]],
            zmin=0,
            zmax=float(matrix.to_numpy().max()),
            text=[[f"{share:.0%}" for share in row] for row in matrix.to_numpy()],
            texttemplate="%{text}",
            textfont={"size": 10},
            colorbar={"title": {"text": "Row share", "side": "right"}, "thickness": 12},
            hovertemplate=(
                "h=1 decile %{y} → h=4 decile %{x}<br>%{z:.1%} of the row"
                "<extra></extra>"
            ),
        ),
    )
    moved = share_moving_at_least_deciles(
        gemeinde[f"log_relative_level_h{TILT_REFERENCE_SIZE}"],
        gemeinde[f"log_relative_level_h{HEADLINE_TILT_SIZE}"],
    )
    correlation = spearman_correlation(
        gemeinde[f"log_relative_level_h{TILT_REFERENCE_SIZE}"],
        gemeinde[f"log_relative_level_h{HEADLINE_TILT_SIZE}"],
    )
    _style(
        figure,
        title=(
            f"Decile transition of the proxy error log(K/W), h=1 against "
            f"h={HEADLINE_TILT_SIZE}"
        ),
        x_title=f"Decile of log(K/W) at h={HEADLINE_TILT_SIZE}",
        y_title="Decile of log(K/W) at h=1",
    )
    figure.add_annotation(
        text=(
            f"Spearman {correlation:.3f}; {moved:.1%} of Gemeinden move at least "
            f"{DECILE_MOVE_THRESHOLD} deciles"
        ),
        showarrow=False,
        xref="paper",
        yref="paper",
        x=0,
        y=1.08,
        xanchor="left",
        font={"size": 12, "color": DARK_GREY},
    )
    figure.update_yaxes(autorange="reversed", dtick=1)
    figure.update_xaxes(dtick=1)
    figure.update_layout(height=620, width=720)
    return figure


def build_tilt_distribution(
    gemeinde: pd.DataFrame,
    gemeinde_h5: pd.DataFrame,
) -> go.Figure:
    """Show the tilt distribution with and without the WoGG-linked Gemeinden (D7).

    The WoGG-linked Gemeinden apply a fixed multiple of the § 12 WoGG table at
    every household size, so their tilt is zero up to the rounding of published
    euro amounts. They pile up in the bin at zero and pull the pooled
    distribution towards it. Both distributions are therefore drawn, and the
    spike is annotated with its own count rather than smoothed away.
    """
    tilt_column = f"tilt_h{HEADLINE_TILT_SIZE}"
    tilt = gemeinde[tilt_column].dropna()
    flag = gemeinde["wogg_linked_flag"].reindex(tilt.index)
    check = check_wogg_linked_tilt(gemeinde[tilt_column], gemeinde["wogg_linked_flag"])
    bins = {"start": -0.5, "end": 0.5, "size": TILT_BIN_WIDTH}
    n_at_zero = int((tilt.abs() <= ZERO_TILT_TOLERANCE).sum())
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.10,
        subplot_titles=(
            f"All {len(tilt):,} Gemeinden with a Wohngeld benchmark",
            f"Excluding the {int(check['n_flagged']):,} WoGG-linked Gemeinden "
            f"({int(check['n_unflagged']):,} left)",
        ),
    )
    figure.add_trace(
        go.Histogram(
            x=tilt,
            xbins=bins,
            marker={"color": GREY},
            showlegend=False,
            hovertemplate="F %{x:.3f}<br>%{y} Gemeinden<extra></extra>",
        ),
        row=1,
        col=1,
    )
    figure.add_trace(
        go.Histogram(
            x=tilt.loc[flag],
            xbins=bins,
            marker={"color": ACCENT},
            showlegend=False,
            hovertemplate="F %{x:.3f}<br>%{y} WoGG-linked Gemeinden<extra></extra>",
        ),
        row=1,
        col=1,
    )
    figure.add_trace(
        go.Histogram(
            x=tilt.loc[~flag],
            xbins=bins,
            marker={"color": GREY},
            showlegend=False,
            hovertemplate="F %{x:.3f}<br>%{y} Gemeinden<extra></extra>",
        ),
        row=2,
        col=1,
    )
    figure.update_layout(barmode="overlay", height=680)
    figure.add_annotation(
        x=0,
        y=n_at_zero,
        text=(
            f"{n_at_zero:,} Gemeinden at exactly F = 0, "
            f"{check['share_exactly_zero_flagged']:.0%} of the "
            f"{int(check['n_flagged']):,} WoGG-linked ones among them; the rest of "
            f"that group lies within {check['max_abs_tilt_flagged']:.3f} of zero, "
            "which is the rounding of published euro amounts"
        ),
        showarrow=True,
        arrowhead=0,
        ax=60,
        ay=-30,
        xanchor="left",
        align="left",
        font={"size": 11, "color": ACCENT},
        row=1,
        col=1,
    )
    median_h5 = float(gemeinde_h5["tilt_h5"].dropna().median())
    _style(
        figure,
        title="Familien-Tilt with and without the WoGG-linked Gemeinden",
        x_title=f"Familien-Tilt F at h={HEADLINE_TILT_SIZE}",
        y_title="Gemeinden",
    )
    figure.add_annotation(
        text=(
            "The h=5 tilt is reported separately on the h=1-5 balanced subsample "
            f"of {int(gemeinde_h5['tilt_h5'].notna().sum()):,} Gemeinden "
            f"(median {median_h5:+.4f}) and is never pooled with this sample."
        ),
        showarrow=False,
        xref="paper",
        yref="paper",
        x=0,
        y=-0.10,
        xanchor="left",
        font={"size": 11, "color": DARK_GREY},
    )
    return figure


def _scatter_trace(
    frame: pd.DataFrame,
    tilt_column: str,
    *,
    name: str,
    colour: str,
) -> go.Scattergl:
    return go.Scattergl(
        x=frame["mean_log_relative_level"],
        y=frame[tilt_column],
        mode="markers",
        name=name,
        marker={"color": colour, "size": 4, "opacity": 0.45},
        customdata=frame[["gemeinde", "kreis"]].to_numpy(),
        hovertemplate=(
            "%{customdata[0]} (%{customdata[1]})<br>"
            "mean log(K/W) %{x:+.3f}<br>F %{y:+.3f}<extra></extra>"
        ),
    )


def _map_frame(geojson: dict[str, Any], values: pd.Series) -> pd.DataFrame:
    frame = pd.DataFrame(
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
    frame["name"] = frame["name"].map(_first_of)
    frame["value"] = values.reindex(frame["ags"]).to_numpy()
    return frame


def _derive_ags_8(value: object) -> str:
    code = value[0] if isinstance(value, list) else value
    text = str(code)
    if len(text) <= AGS_LENGTH:
        return text.zfill(AGS_LENGTH)
    return f"{text[:5]}{text[-3:]}"


def _first_of(value: object) -> str:
    return str(value[0]) if isinstance(value, list) and value else str(value)


def _style(figure: go.Figure, *, title: str, x_title: str, y_title: str) -> None:
    figure.update_layout(
        title={"text": title, "font": {"size": 15}},
        template="simple_white",
        font={"color": DARK_GREY},
        margin={"r": 30, "t": 70, "l": 60, "b": 60},
        legend={"orientation": "h", "y": -0.14, "x": 0},
    )
    figure.update_xaxes(title={"text": x_title})
    figure.update_yaxes(title={"text": y_title})


def _annotate(figure: go.Figure, *annotations: tuple[float, float, str]) -> None:
    for x_position, y_position, text in annotations:
        figure.add_annotation(
            text=text,
            showarrow=False,
            xref="paper",
            yref="paper",
            x=x_position,
            y=y_position,
            xanchor="left",
            font={"size": 11, "color": DARK_GREY},
        )


def _register_all(
    gemeinde: pd.DataFrame,
    gemeinde_h5: pd.DataFrame,
    marginal: pd.DataFrame,
) -> None:
    tilt_column = f"tilt_h{HEADLINE_TILT_SIZE}"
    tilt = gemeinde[tilt_column].dropna()
    unflagged = tilt.loc[~gemeinde["wogg_linked_flag"].reindex(tilt.index)]
    check = check_wogg_linked_tilt(gemeinde[tilt_column], gemeinde["wogg_linked_flag"])
    steps = marginal.loc[marginal["household_size"] == HEADLINE_TILT_SIZE]
    levels = (
        gemeinde[f"log_relative_level_h{TILT_REFERENCE_SIZE}"],
        gemeinde[f"log_relative_level_h{HEADLINE_TILT_SIZE}"],
    )
    flagged_share = float(check["n_flagged"]) / len(tilt)
    share_at_zero = float((tilt.abs() <= ZERO_TILT_TOLERANCE).mean())
    wogg_linked_limitation = (
        f"{int(check['n_flagged']):,} Gemeinden ({flagged_share:.1%}) of "
        "`linked_union` lean on the § 12 WoGG table plus a fixed "
        "Sicherheitszuschlag; where K is that fixed multiple of W at every h "
        "the tilt is zero by construction, and every distribution is shown "
        "with and without them (D7, A22)."
    )
    register_result(
        filename=FIGURE_TILT_SCATTER.name,
        analysis_module=_MODULE,
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"The Familien-Tilt has a median of {tilt.median():+.4f} "
            f"({unflagged.median():+.4f} excluding the WoGG-linked Gemeinden) and a "
            f"P10-P90 range of {unflagged.quantile(0.10):+.4f} to "
            f"{unflagged.quantile(0.90):+.4f}, and correlates at only "
            f"{_level_tilt_correlation(gemeinde, tilt_column):+.3f} "
            "with the average relative KdU level, so the household-size structure "
            "is a second dimension of regional variation rather than a restatement "
            "of the level."
        ),
        limitation=wogg_linked_limitation,
    )
    register_result(
        filename=FIGURE_MARGINAL.name,
        analysis_module=_MODULE,
        dataset="household_profile_marginal.parquet",
        script=_SCRIPT,
        interpretation=(
            f"The median local cap rises by {steps['kdu_step'].median():.0f} EUR for "
            f"the {HEADLINE_TILT_SIZE}. person, against a statutory Wohngeld step of "
            f"{steps['wogg_step'].median():.0f} EUR, with a P10-P90 range of "
            f"{steps['kdu_step'].quantile(0.10):.0f} to "
            f"{steps['kdu_step'].quantile(0.90):.0f} EUR across Gemeinden."
        ),
        limitation=(
            "ΔK is the increment of a cap, never an actual payment; where the "
            "statutory step is missing or zero the ratio ΔK/ΔW is reported as "
            "missing rather than as an infinity."
        ),
    )
    register_result(
        filename=FIGURE_TILT_MAP.name,
        analysis_module=_MODULE,
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"{_between_kreis_share(gemeinde, tilt_column):.1%} of the variance of "
            "the tilt lies between Kreise rather than within them, and "
            f"{share_at_zero:.1%} of Gemeinden sit exactly at zero, "
            "almost all of them WoGG-linked."
        ),
        limitation=(
            "A steeper cap schedule reflects the local housing stock and the "
            "definition of Vergleichsräume as much as any administrative choice; "
            "the map is descriptive and carries no causal reading. " + _CAP_LIMITATION
        ),
    )
    register_result(
        filename=FIGURE_TRANSITION.name,
        analysis_module=_MODULE,
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"The proxy error log(K/W) correlates at "
            f"{spearman_correlation(*levels):.3f} between h=1 and "
            f"h={HEADLINE_TILT_SIZE}, and "
            f"{share_moving_at_least_deciles(*levels):.1%} of Gemeinden move at "
            f"least {DECILE_MOVE_THRESHOLD} of the {N_DECILES} deciles between the "
            "two household sizes."
        ),
        limitation=(
            "Deciles are equally sized groups of Gemeinden, not of people, and a "
            "decile move reflects relative position at one Stichtag, not a change "
            "of local policy."
        ),
    )
    register_result(
        filename=FIGURE_TILT_DISTRIBUTION.name,
        analysis_module=_MODULE,
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"{check['share_exactly_zero_flagged']:.0%} of the "
            f"{int(check['n_flagged']):,} WoGG-linked Gemeinden have a tilt of "
            f"exactly zero and none exceeds {check['max_abs_tilt_flagged']:.4f} in "
            "absolute value, so D7's claim holds to the rounding of published euro "
            "amounts; removing them shifts the median from "
            f"{tilt.median():+.4f} to {unflagged.median():+.4f} and widens the "
            "P10-P90 range by "
            f"{_range_width(unflagged) - _range_width(tilt):+.4f} log points."
        ),
        limitation=(
            "The h=5 panel runs on the h=1-5 balanced subsample of "
            f"{int(gemeinde_h5['tilt_h5'].notna().sum()):,} Gemeinden and is never "
            "pooled with the h=1-4 main sample (D3)."
        ),
    )


def _between_kreis_share(gemeinde: pd.DataFrame, tilt_column: str) -> float:
    """Return the share of the tilt's variance lying between Kreise."""
    frame = gemeinde.loc[gemeinde[tilt_column].notna(), [tilt_column, "kreis"]]
    total = float(frame[tilt_column].var(ddof=0))
    demeaned = frame.groupby("kreis")[tilt_column].transform(
        lambda block: block - block.mean(),
    )
    return 1.0 - float(demeaned.var(ddof=0)) / total


def _level_tilt_correlation(gemeinde: pd.DataFrame, tilt_column: str) -> float:
    return spearman_correlation(
        gemeinde["mean_log_relative_level"],
        gemeinde[tilt_column],
    )


def _range_width(values: pd.Series) -> float:
    return float(values.quantile(0.90) - values.quantile(0.10))
