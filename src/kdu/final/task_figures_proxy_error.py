"""Build the five §8.5 main figures, the §8.4 rent figure, and their §21 texts.

Every figure is austere on purpose (D12): grey carries the data, one accent
colour carries the emphasis, and the plot is labelled directly wherever a
legend would otherwise sit between the reader and the numbers.

Two rules from the decision log shape the output:

- **§8.5.** The h=1 and h=4 maps share one colour scale, centred on zero, so
  that a colour means the same thing on both.
- **D7.** Every map carries a with/without pair: a dropdown switches between
  all Gemeinden and the Gemeinden that are not WoGG-linked, because in the
  latter the 10 % gap is a definitional identity rather than a finding.

The §21 interpretations are generated from the figures' own numbers and written
to `bld/figures/interpretations_proxy_error.md`, so no placeholder can survive
into the text.
"""

from pathlib import Path
from typing import Annotated, Any, cast

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from pytask import Product

from kdu.analysis.proxy_error import (
    PRIMARY_BENCHMARK,
    RENT_POINT_LABELS,
    LinkageGroup,
    describe,
    iter_household_sizes,
    linkage_groups,
    observation_weights,
    symmetric_colour_range,
    weighted_quantile,
    winsorise_for_display,
)
from kdu.analysis.task_proxy_error import PROXY_ERROR_FRAME, RENT_GRID_FRAME
from kdu.config import DATA_CATALOG, FIGURES, WeightingScheme
from kdu.final.manifest import register_result
from kdu.geodata import load_geojson

_GEMEINDEN_GEOJSON = cast("Path", DATA_CATALOG["gemeinden_geojson"])

MAP_H1 = FIGURES / "fig_proxy_error_log_map_h1.html"
MAP_H4 = FIGURES / "fig_proxy_error_log_map_h4.html"
ECDF = FIGURES / "fig_proxy_error_ecdf_by_household_size.html"
ABSOLUTE_DISTRIBUTION = FIGURES / "fig_proxy_error_absolute_distribution.html"
STATE_HEATMAP = FIGURES / "fig_proxy_error_state_household_heatmap.html"
RENT_FIGURE = FIGURES / "fig_rent_dependent_proxy_error.html"
INTERPRETATIONS = FIGURES / "interpretations_proxy_error.md"

_SCRIPT = "src/kdu/final/task_figures_proxy_error.py"
_DATASET = "proxy_error_gemeinde_household.parquet"

# The two household sizes §8.5 maps, on one shared colour scale.
MAPPED_HOUSEHOLD_SIZES: tuple[int, ...] = (1, 4)

# Tail share clipped when setting a colour range; graphical scaling only (§18).
COLOUR_WINSORISE_SHARE = 0.01

# Ink: grey carries the data, the accent carries the emphasis.
GREY = "#8a8a8a"
GREY_LIGHT = "#d0d0d0"
ACCENT = "#1f6f8b"
ACCENT_WARM = "#b4483c"
DIVERGING_SCALE: tuple[tuple[float, str], ...] = (
    (0.0, "#7b3294"),
    (0.5, "#f7f7f7"),
    (1.0, "#1f6f8b"),
)

_TEMPLATE_NAME = "kdu_austere"


def task_figures_proxy_error(
    proxy_error_file: Path = PROXY_ERROR_FRAME,
    rent_grid_file: Path = RENT_GRID_FRAME,
    geojson_file: Path = _GEMEINDEN_GEOJSON,
    map_h1_file: Annotated[Path, Product] = MAP_H1,
    map_h4_file: Annotated[Path, Product] = MAP_H4,
    ecdf_file: Annotated[Path, Product] = ECDF,
    absolute_file: Annotated[Path, Product] = ABSOLUTE_DISTRIBUTION,
    heatmap_file: Annotated[Path, Product] = STATE_HEATMAP,
    rent_file: Annotated[Path, Product] = RENT_FIGURE,
    interpretations_file: Annotated[Path, Product] = INTERPRETATIONS,
) -> None:
    """Write every §8.5 figure, the §8.4 rent figure, and the §21 texts."""
    register_template()

    frame = pd.read_parquet(proxy_error_file)
    primary = frame.loc[
        (frame["benchmark_variant"] == str(PRIMARY_BENCHMARK)) & frame["comparable"]
    ].reset_index(drop=True)
    rent_grid = pd.read_parquet(rent_grid_file)

    colour_range = shared_colour_range(primary)
    geojson = load_geojson(geojson_file)

    figures = {
        map_h1_file: build_log_map(
            primary, geojson, household_size=1, colour_range=colour_range
        ),
        map_h4_file: build_log_map(
            primary, geojson, household_size=4, colour_range=colour_range
        ),
        ecdf_file: build_ecdf(primary),
        absolute_file: build_absolute_distribution(primary),
        heatmap_file: build_state_heatmap(primary),
        rent_file: build_rent_figure(rent_grid),
    }
    for path, figure in figures.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        figure.write_html(path, include_plotlyjs=True, full_html=True)

    interpretations_file.write_text(
        build_interpretations(primary, rent_grid, colour_range),
        encoding="utf-8",
    )
    _register(primary, rent_grid)


def register_template() -> None:
    """Register and select the project's austere Plotly template.

    D12 asks the §19 figure program for deliberately austere styling, so the
    default template is a print-oriented variant of `simple_white` rather than
    a screen theme: no gridlines the eye has to climb over, one type size, and
    a white ground that survives a projector and a PDF alike.
    """
    template = pio.templates["simple_white"]
    template.layout.font.family = "Inter, Helvetica, Arial, sans-serif"
    template.layout.font.size = 13
    template.layout.font.color = "#222222"
    template.layout.colorway = (ACCENT, ACCENT_WARM, GREY, GREY_LIGHT)
    template.layout.margin = {"l": 70, "r": 40, "t": 90, "b": 70}
    template.layout.xaxis.showgrid = False
    template.layout.yaxis.showgrid = True
    template.layout.yaxis.gridcolor = "#eeeeee"
    pio.templates[_TEMPLATE_NAME] = template
    pio.templates.default = _TEMPLATE_NAME


def shared_colour_range(primary: pd.DataFrame) -> tuple[float, float]:
    """Return the one zero-centred colour range both §8.5 maps use.

    The range is set on the winsorised log difference across both mapped
    household sizes. §18 permits winsorising for graphical scaling and forbids
    deleting a genuine extreme value merely for being large, so nothing is
    dropped: the extremes are still drawn, at the end of the scale.
    """
    mapped = primary.loc[primary["household_size"].isin(MAPPED_HOUSEHOLD_SIZES)]
    clipped = winsorise_for_display(
        mapped["proxy_error_log"],
        share=COLOUR_WINSORISE_SHARE,
    )
    return symmetric_colour_range(clipped)


def build_log_map(
    primary: pd.DataFrame,
    geojson: dict[str, Any],
    *,
    household_size: int,
    colour_range: tuple[float, float],
) -> go.Figure:
    """Map the log proxy error `L` for one household size, with the D7 pair.

    One Choroplethmap trace carries the geometry; the dropdown restyles the
    values, so the with/without pair costs no second copy of 10,980 polygons.
    Gemeinden dropped by a view are drawn in the map's background colour rather
    than removed, which keeps the outline of Germany intact.
    """
    fid_by_ags = _fid_by_ags(geojson)
    cell = primary.loc[primary["household_size"] == household_size].copy()
    cell["fid"] = cell["ags"].map(fid_by_ags)
    cell = cell.dropna(subset=["fid"]).sort_values("fid")

    low, high = colour_range
    masks = linkage_groups(cell)
    views = {
        "All Gemeinden": masks[LinkageGroup.ALL],
        "Excluding WoGG-linked": masks[LinkageGroup.EXCLUDING_WOGG_LINKED],
    }
    values = {
        label: cell["proxy_error_log"].where(mask).to_numpy(dtype=float)
        for label, mask in views.items()
    }
    first = next(iter(values))

    figure = go.Figure(
        go.Choroplethmap(
            geojson=geojson,
            featureidkey="properties.fid",
            locations=cell["fid"].astype(int),
            z=values[first],
            zmin=low,
            zmax=high,
            colorscale=[list(stop) for stop in DIVERGING_SCALE],
            marker={"line": {"width": 0}},
            customdata=np.stack(
                [
                    cell["municipality_name"].astype(str),
                    cell["cap_eur"].astype(float),
                    cell["benchmark_eur"].astype(float),
                    cell["proxy_error_eur"].astype(float),
                ],
                axis=-1,
            ),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Local cap K: %{customdata[1]:.0f} €<br>"
                "Wohngeld benchmark W: %{customdata[2]:.0f} €<br>"
                "D = K − W: %{customdata[3]:+.0f} €<br>"
                "L: %{z:+.1f} log points<extra></extra>"
            ),
            colorbar={
                "title": {"text": "L (log points)", "side": "right"},
                "ticksuffix": "",
                "thickness": 14,
                "len": 0.6,
            },
        ),
    )
    figure.update_layout(
        map={"style": "white-bg", "center": {"lat": 51.2, "lon": 10.4}, "zoom": 4.6},
        margin={"l": 0, "r": 0, "t": 110, "b": 40},
        title={
            "text": (
                f"<b>Log proxy error, household size {household_size}</b><br>"
                "<sup>L = 100 (log K − log W). Blue: the local KdU cap lies "
                "above the Wohngeld Höchstbetrag; purple: below it. "
                "Both mapped household sizes share this colour scale.</sup>"
            ),
            "x": 0.02,
            "xanchor": "left",
        },
        updatemenus=[
            {
                "type": "dropdown",
                "x": 0.02,
                "y": 0.98,
                "xanchor": "left",
                "yanchor": "top",
                "bgcolor": "rgba(255,255,255,0.85)",
                "buttons": [
                    {
                        "label": label,
                        "method": "restyle",
                        "args": [{"z": [array]}],
                    }
                    for label, array in values.items()
                ],
            },
        ],
        annotations=[
            {
                "text": (
                    f"{int(masks[LinkageGroup.WOGG_LINKED_ONLY].sum()):,} of "
                    f"{len(cell):,} Gemeinden are `linked_union` and blank out "
                    "in the second view. K = 1.10 × W by construction only in "
                    "`exact_ratio`, a group broader than, and not a superset "
                    "of, this one (D7, A22)."
                ),
                "showarrow": False,
                "x": 0.02,
                "y": -0.02,
                "xref": "paper",
                "yref": "paper",
                "xanchor": "left",
                "font": {"size": 11, "color": GREY},
            },
        ],
    )
    return figure


def build_ecdf(primary: pd.DataFrame) -> go.Figure:
    """Draw the ECDF of the euro difference `D` by household size.

    Household sizes 1 and 4 carry the accent because they are the two the maps
    show; the rest are grey. Every curve is labelled at its own right-hand end,
    so the figure needs no legend.
    """
    figure = go.Figure()
    for household_size, cell in iter_household_sizes(primary):
        values = cell["proxy_error_eur"].dropna().sort_values()
        share = 100.0 * np.arange(1, len(values) + 1) / len(values)
        accent = household_size in MAPPED_HOUSEHOLD_SIZES
        figure.add_trace(
            go.Scatter(
                x=values,
                y=share,
                mode="lines",
                name=f"h = {household_size}",
                line={
                    "color": ACCENT if accent else GREY,
                    "width": 2.4 if accent else 1.2,
                },
                hovertemplate="D = %{x:.0f} €<br>%{y:.1f} % at or below<extra></extra>",
                showlegend=False,
            ),
        )
        figure.add_annotation(
            x=float(values.quantile(0.985)),
            y=98.5,
            text=f"h = {household_size}",
            showarrow=False,
            xanchor="left",
            font={"size": 11, "color": ACCENT if accent else GREY},
        )

    figure.add_vline(x=0, line={"color": "#444444", "width": 1, "dash": "dot"})
    figure.update_layout(
        title={
            "text": (
                "<b>How far the Wohngeld Höchstbetrag misses the local cap</b><br>"
                "<sup>Empirical CDF of D = K − W in euro per month, one curve "
                "per household size, unweighted Gemeinden.</sup>"
            ),
            "x": 0.02,
            "xanchor": "left",
        },
        xaxis={"title": {"text": "D = K − W (€ per month)"}, "zeroline": False},
        yaxis={
            "title": {"text": "Share of Gemeinden at or below (%)"},
            "range": [0, 100],
        },
        height=560,
    )
    return figure


def build_absolute_distribution(primary: pd.DataFrame) -> go.Figure:
    """Draw the distribution of the absolute euro difference `|D|`.

    The euro thresholds §8.3 asks for are drawn in as reference lines so the
    reader can read the shares straight off the axis instead of hunting for
    them in a table.
    """
    figure = go.Figure()
    for household_size, cell in iter_household_sizes(primary):
        accent = household_size in MAPPED_HOUSEHOLD_SIZES
        figure.add_trace(
            go.Violin(
                x=cell["proxy_error_abs"].astype(float),
                y=[f"h = {household_size}"] * len(cell),
                orientation="h",
                side="positive",
                width=1.6,
                points=False,
                meanline={"visible": True},
                line={"color": ACCENT if accent else GREY, "width": 1.4},
                fillcolor="rgba(31,111,139,0.20)"
                if accent
                else "rgba(138,138,138,0.18)",
                hoverinfo="x",
                showlegend=False,
            ),
        )
    for threshold in (25, 50, 100):
        figure.add_vline(
            x=threshold,
            line={"color": GREY_LIGHT, "width": 1},
            annotation={"text": f"{threshold} €", "font": {"size": 10, "color": GREY}},
        )
    figure.update_layout(
        title={
            "text": (
                "<b>The size of the mismeasurement, ignoring its direction</b><br>"
                "<sup>Distribution of |D| in euro per month by household size, "
                "unweighted Gemeinden. The x axis is clipped for display; no "
                "observation is dropped.</sup>"
            ),
            "x": 0.02,
            "xanchor": "left",
        },
        xaxis={
            "title": {"text": "|D| = |K − W| (€ per month)"},
            "range": [0, float(primary["proxy_error_abs"].quantile(0.99))],
        },
        yaxis={"title": {"text": ""}, "autorange": "reversed"},
        height=560,
    )
    return figure


def build_state_heatmap(primary: pd.DataFrame) -> go.Figure:
    """Draw the Bundesland by household-size heatmap of the median deviation.

    The colour scale is the same diverging, zero-centred ramp the maps use, so
    a reader moving between the two reads colour the same way.
    """
    medians = primary.pivot_table(
        index="bundesland",
        columns="household_size",
        values="proxy_error_eur",
        aggfunc="median",
    ).sort_index()
    bound = float(np.nanmax(np.abs(medians.to_numpy(dtype=float))))
    figure = go.Figure(
        go.Heatmap(
            z=medians.to_numpy(dtype=float),
            x=[f"h = {size}" for size in medians.columns],
            y=list(medians.index),
            zmid=0,
            zmin=-bound,
            zmax=bound,
            colorscale=[list(stop) for stop in DIVERGING_SCALE],
            text=medians.round(0).to_numpy(dtype=float),
            texttemplate="%{text:+.0f}",
            textfont={"size": 11},
            hovertemplate=("%{y}, %{x}<br>median D: %{z:+.0f} €<extra></extra>"),
            colorbar={"title": {"text": "Median D (€)"}, "thickness": 14, "len": 0.7},
        ),
    )
    figure.update_layout(
        title={
            "text": (
                "<b>The proxy error is regional and household-specific at once</b><br>"
                "<sup>Median D = K − W in euro per month, by Bundesland and "
                "household size, unweighted Gemeinden.</sup>"
            ),
            "x": 0.02,
            "xanchor": "left",
        },
        xaxis={"title": {"text": ""}, "side": "top"},
        yaxis={"title": {"text": ""}, "autorange": "reversed"},
        height=640,
    )
    return figure


def build_rent_figure(rent_grid: pd.DataFrame) -> go.Figure:
    """Show when the §8.4 error actually becomes benefit-relevant.

    Below the lower of the two caps both scenarios recognise the rent in full,
    so `e(m) = 0` whatever the caps are; the error appears only between the
    caps and saturates at `K − W` above the higher one. The two directions are
    drawn separately, because a cap gap that runs the other way costs the
    household rather than the budget.
    """
    grid = rent_grid.loc[rent_grid["household_size"].isin(MAPPED_HOUSEHOLD_SIZES)]
    figure = go.Figure()
    order = list(RENT_POINT_LABELS)
    for sign, colour in (("K above W", ACCENT), ("K below W", ACCENT_WARM)):
        for household_size in MAPPED_HOUSEHOLD_SIZES:
            cell = grid.loc[
                (grid["difference_sign"] == sign)
                & (grid["household_size"] == household_size)
            ]
            if cell.empty:
                continue
            summary = (
                cell.groupby("rent_point", observed=True)["benefit_relevant_error_eur"]
                .agg(["mean", lambda x: x.quantile(0.10), lambda x: x.quantile(0.90)])
                .reindex(order)
            )
            summary.columns = ["mean", "p10", "p90"]
            solid = household_size == MAPPED_HOUSEHOLD_SIZES[-1]
            figure.add_trace(
                go.Scatter(
                    x=order,
                    y=summary["mean"],
                    mode="lines+markers",
                    name=f"{sign}, h = {household_size}",
                    line={
                        "color": colour,
                        "width": 2.4 if solid else 1.4,
                        "dash": "solid" if solid else "dot",
                    },
                    marker={"size": 7 if solid else 5},
                    customdata=np.stack(
                        [summary["p10"], summary["p90"]],
                        axis=-1,
                    ),
                    hovertemplate=(
                        "%{x}<br>mean e(m): %{y:+.1f} €<br>"
                        "P10 %{customdata[0]:+.0f} €, P90 %{customdata[1]:+.0f} €"
                        "<extra>%{fullData.name}</extra>"
                    ),
                    showlegend=False,
                ),
            )
            figure.add_annotation(
                x=order[-1],
                y=float(summary["mean"].iloc[-1]),
                text=f" {sign}, h = {household_size}",
                showarrow=False,
                xanchor="left",
                font={"size": 11, "color": colour},
            )

    figure.add_hline(y=0, line={"color": "#444444", "width": 1, "dash": "dot"})
    figure.update_layout(
        title={
            "text": (
                "<b>The cap difference reaches the household only once rent "
                "clears both caps</b><br>"
                "<sup>Mean e(m) = min(m, K) − min(m, W) in euro per month, on "
                "the five rent points of §8.4.</sup>"
            ),
            "x": 0.02,
            "xanchor": "left",
        },
        xaxis={
            "title": {"text": "Actual Bruttokaltmiete m"},
            "categoryorder": "array",
            "categoryarray": order,
        },
        yaxis={"title": {"text": "e(m) = min(m, K) − min(m, W) (€ per month)"}},
        margin={"r": 200},
        height=560,
    )
    return figure


def build_interpretations(
    primary: pd.DataFrame,
    rent_grid: pd.DataFrame,
    colour_range: tuple[float, float],
) -> str:
    """Write the §21 four-part interpretation of every main figure.

    Every number in the text is computed here from the same frames the figures
    are drawn from, so the file cannot fall out of step with them and no
    placeholder can survive. The wording obeys §20: no "generosity", no
    "restrictiveness", no causal claim, no "actual KdU payment" for what is a
    cap, and no statement about housing availability.
    """
    facts = _interpretation_facts(primary, rent_grid, colour_range)
    sections = [
        _map_interpretation(facts, household_size=1),
        _map_interpretation(facts, household_size=4),
        _ecdf_interpretation(facts),
        _absolute_interpretation(facts),
        _heatmap_interpretation(facts),
        _rent_interpretation(facts),
    ]
    header = [
        "# §21 interpretations — P0.3, the descriptive proxy-error analysis",
        "",
        (
            "Each figure is read in the four parts §21 prescribes: what is "
            "measured, the central quantitative finding, why it matters for "
            "tax-transfer simulation, and what may not be concluded. Every "
            "number is computed by "
            "`src/kdu/final/task_figures_proxy_error.py` from "
            "`bld/proxy_error_gemeinde_household.parquet`."
        ),
        "",
        (
            "`K` is the local maximum recognisable Bruttokaltmiete, `W` the "
            "base Wohngeld Höchstbetrag of § 12 WoGG in force since 2025-01-01 "
            "(D6, A1). `D = K − W`, `L = 100 (log K − log W)`. All figures use "
            "the primary benchmark; the base-plus-Klimakomponente variant is in "
            "`bld/tables/proxy_error_robustness.csv`."
        ),
        "",
    ]
    return "\n".join([*header, *sections]) + "\n"


def _interpretation_facts(
    primary: pd.DataFrame,
    rent_grid: pd.DataFrame,
    colour_range: tuple[float, float],
) -> dict[Any, Any]:
    facts: dict[Any, Any] = {"colour_range": colour_range}
    for household_size, cell in iter_household_sizes(primary):
        masks = linkage_groups(cell)
        population = observation_weights(cell, WeightingScheme.GEMEINDE_POPULATION)
        entry = {
            "n": int(cell["ags"].nunique()),
            "n_flagged": int(masks[LinkageGroup.WOGG_LINKED_ONLY].sum()),
            "share_at_markup": 100.0 * float(cell["at_safety_markup"].mean()),
            "all": describe(cell),
            "excluding": describe(cell.loc[masks[LinkageGroup.EXCLUDING_WOGG_LINKED]]),
            "median_population_weighted": weighted_quantile(
                cell["proxy_error_eur"],
                population,
                0.50,
            ),
            "median_log_all": float(cell["proxy_error_log"].median()),
            "median_log_excluding": float(
                cell.loc[
                    masks[LinkageGroup.EXCLUDING_WOGG_LINKED], "proxy_error_log"
                ].median(),
            ),
        }
        facts[household_size] = entry

    medians = primary.pivot_table(
        index="bundesland",
        columns="household_size",
        values="proxy_error_eur",
        aggfunc="median",
    )
    facts["state_min"] = (medians[1].idxmin(), float(medians[1].min()))
    facts["state_max"] = (medians[1].idxmax(), float(medians[1].max()))
    facts["state_max_h4"] = (medians[4].idxmax(), float(medians[4].max()))
    facts["n_states_negative_h1"] = int((medians[1] < 0).sum())

    single = rent_grid["household_size"] == 1
    saturation = rent_grid.loc[
        single & (rent_grid["rent_point"] == RENT_POINT_LABELS[1])
    ]
    facts["share_zero_at_lower_cap"] = 100.0 * float(
        (saturation["benefit_relevant_error_eur"] == 0).mean(),
    )
    midpoint = rent_grid.loc[
        single
        & (rent_grid["rent_point"] == RENT_POINT_LABELS[2])
        & (rent_grid["difference_sign"] == "K above W")
    ]
    facts["mean_error_at_midpoint_h1"] = float(
        midpoint["benefit_relevant_error_eur"].mean(),
    )
    facts["mean_full_difference_h1"] = float(midpoint["full_difference_eur"].mean())
    lowest = rent_grid.loc[single & (rent_grid["rent_point"] == RENT_POINT_LABELS[0])]
    facts["share_k_below_w_h1"] = 100.0 * float(
        (lowest["difference_sign"] == "K below W").mean(),
    )
    return facts


def _map_interpretation(facts: dict[Any, Any], *, household_size: int) -> str:
    entry = facts[household_size]
    counterpart = next(
        size for size in MAPPED_HOUSEHOLD_SIZES if size != household_size
    )
    low, high = facts["colour_range"]
    return _four_part(
        title=(
            f"Figure {1 if household_size == 1 else 2} — Map of L, "
            f"household size {household_size}"
        ),
        measured=(
            f"For every one of the {entry['n']:,} Gemeinden with both a local "
            "Bruttokaltmiete cap and a statutory Mietenstufe, the log "
            "difference L = 100 (log K − log W) between the local cap and the "
            "Wohngeld Höchstbetrag a tax-transfer model would substitute for "
            "it. The colour scale runs from "
            f"{low:+.0f} to {high:+.0f} log points, is centred on zero, and is "
            f"shared with the household-size-{counterpart} map, so the same "
            "colour means the same log gap on both."
        ),
        finding=(
            f"The median Gemeinde sits {entry['median_log_all']:+.1f} log points "
            "above the Wohngeld benchmark across all Gemeinden, and "
            f"{entry['median_log_excluding']:+.1f} log points above it once the "
            f"{entry['n_flagged']:,} WoGG-linked Gemeinden are set aside. The "
            f"spread is wide: the tenth percentile is "
            f"{entry['all']['p10']:+.0f} € and the ninetieth "
            f"{entry['all']['p90']:+.0f} € in euro terms, and the gap is "
            f"negative in {entry['all']['share_negative']:.1f} % of Gemeinden."
        ),
        relevance=(
            "A model that substitutes W for K does not make one nationwide "
            "error but a spatially structured one. The map shows contiguous "
            "regions where the substitution runs one way and others where it "
            "runs the other, so the error does not average out across a "
            "national sample and cannot be absorbed into a constant."
        ),
        forbidden=(
            "A blue Gemeinde is not more generous and a purple one is not more "
            "restrictive: the local cap is endogenous to the local housing "
            "market, to administrative procedure, and to how a Kreis draws its "
            "Vergleichsräume. Nothing here is a causal effect of any policy, "
            "and neither K nor W is an actual KdU payment — both are caps on "
            "what may be recognised. The "
            f"{entry['n_flagged']:,} Gemeinden of `linked_union` lean on the "
            "§ 12 WoGG table; where K/W sits exactly at 1.10 — the `exact_ratio` "
            "group, broader than and not a superset of this one — the colour "
            "reports a definitional identity, K = 1.10 × W, and not an "
            "empirical finding. That is why the second view of the dropdown "
            "exists (D7, A12, A22)."
        ),
    )


def _ecdf_interpretation(facts: dict[Any, Any]) -> str:
    first = facts[1]
    fourth = facts[4]
    return _four_part(
        title="Figure 3 — ECDF of the euro difference by household size",
        measured=(
            "The empirical distribution of D = K − W in euro per month, one "
            "curve per household size, over the Gemeinden of the main sample. "
            "D is the quantity §8.1 designates for social-policy "
            "interpretation, because it is denominated in the unit a household "
            "budget is."
        ),
        finding=(
            f"The median Gemeinde shows D = {first['all']['median']:+.0f} € for "
            f"a single-person household and "
            f"{fourth['all']['median']:+.0f} € for a four-person household; "
            "excluding the WoGG-linked Gemeinden those medians move to "
            f"{first['excluding']['median']:+.0f} € and "
            f"{fourth['excluding']['median']:+.0f} €. The curves fan out with "
            f"household size: |D| exceeds 100 € in "
            f"{first['all']['share_abs_gt_100']:.1f} % of Gemeinden at "
            f"household size 1 and in "
            f"{fourth['all']['share_abs_gt_100']:.1f} % at household size 4."
        ),
        relevance=(
            "The curves cross zero at different points, so the substitution "
            "error a model makes depends on the household it is simulating. A "
            "single correction factor calibrated on one household size would "
            "carry the wrong sign or the wrong magnitude for another."
        ),
        forbidden=(
            "The distribution says nothing about what any household actually "
            "receives: both K and W are caps, and the amount recognised is the "
            "lesser of the cap and the actual Bruttokaltmiete. Nor can the "
            "spread be read as variation in housing availability — it is "
            "variation in two administrative parameters."
        ),
    )


def _absolute_interpretation(facts: dict[Any, Any]) -> str:
    first = facts[1]
    fourth = facts[4]
    return _four_part(
        title="Figure 4 — Distribution of the absolute euro difference",
        measured=(
            "The distribution of |D| = |K − W| in euro per month by household "
            "size: the size of the mismeasurement with its direction stripped "
            "out, which is the quantity a model's error budget cares about."
        ),
        finding=(
            f"The mean absolute difference is {first['all']['mean_absolute']:.0f} € "
            f"at household size 1 and {fourth['all']['mean_absolute']:.0f} € at "
            f"household size 4. It exceeds 50 € in "
            f"{first['all']['share_abs_gt_50']:.1f} % and "
            f"{fourth['all']['share_abs_gt_50']:.1f} % of Gemeinden "
            "respectively, and 100 € in "
            f"{first['all']['share_abs_gt_100']:.1f} % and "
            f"{fourth['all']['share_abs_gt_100']:.1f} %."
        ),
        relevance=(
            "An error of this size in the recognised Unterkunftsbedarf feeds "
            "one-for-one into the simulated Bedarf at zero income and therefore "
            "into every quantity derived from it. It is large next to the "
            "Regelbedarf itself, so it is not a second-order correction."
        ),
        forbidden=(
            "A large |D| is not evidence that a Kreis is doing anything wrong, "
            "and it is not a causal statement about anything. The x axis is "
            "clipped at the 99th percentile for readability only: no "
            "observation is winsorised away in any table, because a genuine "
            "extreme value may not be removed merely for being large (§18)."
        ),
    )


def _heatmap_interpretation(facts: dict[Any, Any]) -> str:
    min_state, min_value = facts["state_min"]
    max_state, max_value = facts["state_max"]
    max_state_h4, max_value_h4 = facts["state_max_h4"]
    return _four_part(
        title="Figure 5 — Bundesland by household-size heatmap of the median deviation",
        measured=(
            "The median D = K − W in euro per month within each Bundesland, "
            "for each household size, on the same diverging zero-centred scale "
            "the maps use."
        ),
        finding=(
            f"At household size 1 the Bundesland medians run from "
            f"{min_value:+.0f} € in {min_state} to {max_value:+.0f} € in "
            f"{max_state}, and "
            f"{facts['n_states_negative_h1']} of 16 Bundesländer show a "
            "negative median. The rows are not parallel: at household size 4 "
            f"the highest median is {max_value_h4:+.0f} € in {max_state_h4}, so "
            "the ranking of Bundesländer changes with the household being "
            "simulated."
        ),
        relevance=(
            "A model that regionalises the Unterkunftsbedarf at Bundesland "
            "level and applies one household-size profile on top of it will "
            "still misstate the parameter, because the deviation moves in both "
            "dimensions at once. That is Beitrag 2 of the project in one "
            "picture."
        ),
        forbidden=(
            "A Bundesland median is an average over Kreise that set their caps "
            "independently; it is not itself a policy parameter, and no "
            "Bundesland government sets it. The colour is not a measure of "
            "generosity, and the differences are descriptive — no "
            "identification strategy is claimed."
        ),
    )


def _rent_interpretation(facts: dict[Any, Any]) -> str:
    return _four_part(
        title="Figure 6 — When the proxy error becomes benefit-relevant (§8.4)",
        measured=(
            "The function e(m) = min(m, K) − min(m, W), the difference in "
            "recognised Bruttokaltmiete between a scenario using the local cap "
            "and one using the Wohngeld Höchstbetrag, evaluated on the five "
            "rent points §8.4 prescribes and shown separately for Gemeinden "
            "where K lies above W and where it lies below."
        ),
        finding=(
            "At and below the lower of the two caps e(m) is exactly zero in "
            f"{facts['share_zero_at_lower_cap']:.0f} % of observations — the "
            "two scenarios are indistinguishable there. At the midpoint "
            "0.5 (K + W) the mean error for a single-person household where K "
            f"exceeds W is {facts['mean_error_at_midpoint_h1']:.0f} €, exactly "
            "half of the mean full cap difference of "
            f"{facts['mean_full_difference_h1']:.0f} €, and it reaches that "
            "full difference only once rent clears the higher cap. In "
            f"{facts['share_k_below_w_h1']:.1f} % of Gemeinden the difference "
            "runs the other way at household size 1, and there the substitution "
            "overstates the recognised need instead of understating it."
        ),
        relevance=(
            "The cap difference is an upper bound on the simulation error, not "
            "the error itself. Whether a given Bedarfsgemeinschaft is affected "
            "depends on where its actual Bruttokaltmiete sits relative to both "
            "caps, so the population share exposed to the proxy error is "
            "smaller than the share of Gemeinden with a non-zero D — and this "
            "figure is the device that makes that visible."
        ),
        forbidden=(
            "The rent points are a normalised grid, not a rent distribution: "
            "the figure shows how much of the cap gap would bite at each rent "
            "level, not how many households sit at each. It therefore says "
            "nothing about how many households are affected, and nothing about "
            "housing availability. All of it is conditional on the cap being "
            "in force: inside the twelve-month Karenzzeit of § 22 Abs. 1 S. 2–3 "
            "SGB II the actual Unterkunftskosten are recognised in full and the "
            "proxy error is identically zero (D11)."
        ),
    )


def _four_part(
    *,
    title: str,
    measured: str,
    finding: str,
    relevance: str,
    forbidden: str,
) -> str:
    return "\n".join(
        [
            f"## {title}",
            "",
            f"**What is measured.** {measured}",
            "",
            f"**The central quantitative finding.** {finding}",
            "",
            f"**Why it matters for tax-transfer simulation.** {relevance}",
            "",
            f"**What may not be concluded.** {forbidden}",
            "",
        ],
    )


def _fid_by_ags(geojson: dict[str, Any]) -> dict[str, int]:
    mapping = {}
    for feature in geojson["features"]:
        code = str(feature["properties"]["gem_code"]).zfill(12)
        mapping[f"{code[:5]}{code[-3:]}"] = feature["properties"]["fid"]
    return mapping


def _register(primary: pd.DataFrame, rent_grid: pd.DataFrame) -> None:
    entries = _register_entries(primary, rent_grid)
    for filename, interpretation, limitation in entries:
        register_result(
            filename=filename,
            analysis_module="P0.3",
            dataset=_DATASET,
            script=_SCRIPT,
            interpretation=interpretation,
            limitation=limitation,
        )


def _register_entries(
    primary: pd.DataFrame,
    rent_grid: pd.DataFrame,
) -> list[tuple[str, str, str]]:
    smallest, largest = MAPPED_HOUSEHOLD_SIZES
    first = primary.loc[primary["household_size"] == smallest]
    fourth = primary.loc[primary["household_size"] == largest]
    first_unlinked = first.loc[
        linkage_groups(first)[LinkageGroup.EXCLUDING_WOGG_LINKED],
        "proxy_error_log",
    ].median()
    fourth_unlinked = fourth.loc[
        linkage_groups(fourth)[LinkageGroup.EXCLUDING_WOGG_LINKED],
        "proxy_error_log",
    ].median()
    definitional = (
        "The `linked_union` Gemeinden lean on the § 12 WoGG table, and in the "
        "`exact_ratio` group — broader than, and not a superset of, that one — "
        "K = 1.10 × W by construction, so the pooled figure is not an empirical "
        "regularity; the with/without pair is mandatory (D7, A22)."
    )
    at_lower_cap = rent_grid.loc[
        rent_grid["rent_point"] == RENT_POINT_LABELS[1],
        "benefit_relevant_error_eur",
    ]
    zero_share = 100.0 * float((at_lower_cap == 0).mean())
    return [
        (
            MAP_H1.name,
            (
                "The single-person local cap exceeds the Wohngeld Höchstbetrag "
                f"by a median {first['proxy_error_log'].median():.1f} log points, "
                f"and by {first_unlinked:.1f} "
                "excluding the WoGG-linked Gemeinden, with contiguous regions "
                "of both signs."
            ),
            definitional,
        ),
        (
            MAP_H4.name,
            (
                "On the same colour scale the four-person gap has a median of "
                f"{fourth['proxy_error_log'].median():.1f} log points and "
                f"{fourth_unlinked:.1f} "
                "excluding the WoGG-linked Gemeinden, so the spatial pattern is "
                "not a rescaling of the single-person one."
            ),
            definitional,
        ),
        (
            ECDF.name,
            (
                "The median euro difference rises from "
                f"{first['proxy_error_eur'].median():+.0f} € at household size 1 "
                f"to {fourth['proxy_error_eur'].median():+.0f} € at household "
                "size 4, and the curves cross zero at different points."
            ),
            (
                "D is a difference between two caps, not between two payments; "
                "what a household receives depends on its actual rent."
            ),
        ),
        (
            ABSOLUTE_DISTRIBUTION.name,
            (
                "The mean absolute difference is "
                f"{first['proxy_error_abs'].mean():.0f} € at household size 1 and "
                f"{fourth['proxy_error_abs'].mean():.0f} € at household size 4."
            ),
            (
                "The x axis is clipped at the 99th percentile for display only; "
                "no genuine extreme value is removed from any table (§18)."
            ),
        ),
        (
            STATE_HEATMAP.name,
            (
                "Bundesland medians of D run in both directions and their "
                "ranking changes with household size, so the deviation is "
                "regional and household-specific at once."
            ),
            (
                "A Bundesland median averages over Kreise that set caps "
                "independently; it is not itself a policy parameter."
            ),
        ),
        (
            RENT_FIGURE.name,
            (
                "e(m) = min(m, K) − min(m, W) is exactly zero in "
                f"{zero_share:.0f} % of observations at the lower of the two "
                "caps and reaches the full cap difference only once actual rent "
                "clears the higher one."
            ),
            (
                "The rent grid is normalised, not an observed rent "
                "distribution, so the figure shows when the error would bite "
                "and not how many households sit there."
            ),
        ),
        (
            INTERPRETATIONS.name,
            (
                "The §21 four-part reading of all six P0.3 figures — what is "
                "measured, the central number, why it matters for tax-transfer "
                "simulation, and what may not be concluded — with every figure "
                "in it recomputed from the analysis frame at build time."
            ),
            (
                "Prose, not data: it is the only place the D7 with/without pair "
                "and the D11 Karenzzeit conditionality are stated in words, so "
                "no figure of P0.3 may be circulated without it."
            ),
        ),
    ]
