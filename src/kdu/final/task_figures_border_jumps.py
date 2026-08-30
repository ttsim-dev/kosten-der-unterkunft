"""Draw the P1.1 figures and write the §21 interpretation.

Three figures, the §13 figure program: the distribution of border jumps as a
histogram beside its ECDF, boxplots by border type and household size, and
detail maps of the ten largest plausible jumps.

**None of these figures is a regression-discontinuity plot.** There is no
running variable, no bandwidth and no fitted discontinuity anywhere in this
module. A detail map shows two adjacent Gemeinden whose administrations
recognise different maximum Bruttokaltmieten; it says nothing about what the
border does to rents, to housing or to anyone's behaviour, and §20's ban on
"causal effect" governs every caption here.

Styling follows D12: the §19 figure program is deliberately austere. Grey is
the default ink and one accent colour marks the contrast a panel is about.
"""

from pathlib import Path
from typing import Annotated

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pytask import Product

from kdu.analysis.border_jumps import (
    SHORT_BOUNDARY_THRESHOLD_M,
    BorderType,
    GeometryFitness,
    PairLinkage,
    interpretation,
)
from kdu.analysis.task_border_jumps import (
    BORDER_JUMPS,
    BORDER_TYPE_TABLE,
    COMPARISON_GROUP_TABLE,
    DETAIL_GEOMETRY,
    DISTRIBUTION_TABLE,
    GEOMETRY_FITNESS_TABLE,
    TOP_TABLE,
)
from kdu.config import FIGURES, TABLES
from kdu.final.manifest import register_result

DISTRIBUTION_FIGURE = FIGURES / "fig_border_jumps_distribution.html"
BORDER_TYPE_FIGURE = FIGURES / "fig_border_jumps_by_type.html"
DETAIL_MAP_FIGURE = FIGURES / "fig_border_jumps_detail_maps.html"
INTERPRETATION = TABLES / "border_jumps_interpretation.md"

_MODULE = "P1.1"
_DATASET = "border_jumps.parquet"
_SCRIPT = "src/kdu/final/task_figures_border_jumps.py"

# The single caveat every P1.1 output has to be read with (§13, §20).
_RD_LIMITATION = (
    "Descriptive only: a jump documents an administrative discontinuity and is "
    "not a regression-discontinuity estimate of any effect of the border."
)

# Austere ink: grey for the within-region baseline, accent for the steps.
_GREY = "#8c8c8c"
_LIGHT_GREY = "#d4d4d4"
_DARK_GREY = "#4d4d4d"
_ACCENT = "#c2543a"
_TEMPLATE = "simple_white"

_BORDER_TYPE_LABELS: dict[str, str] = {
    BorderType.WITHIN_POLICY_REGION.value: "Within one policy region",
    BorderType.BETWEEN_POLICY_REGIONS.value: "Between Kreise, one Bundesland",
    BorderType.BETWEEN_BUNDESLAENDER.value: "Between Bundesländer",
}
_BORDER_TYPE_COLOURS: dict[str, str] = {
    BorderType.WITHIN_POLICY_REGION.value: _LIGHT_GREY,
    BorderType.BETWEEN_POLICY_REGIONS.value: _GREY,
    BorderType.BETWEEN_BUNDESLAENDER.value: _ACCENT,
}

# The linkage group every figure is drawn on: pairs touching a Gemeinde
# flagged by either D7 detector are dropped, because there the cap is the § 12
# WoGG table times 1.10 and a step would only restate the Mietenstufe (A12).
_FIGURE_LINKAGE = PairLinkage.EXCLUDING_LINKED_UNION

# Household size the two distribution figures headline; the others are in the
# tables and in the boxplot panel.
_HEADLINE_HOUSEHOLD_SIZE = 4
# Euro axis limit for the histogram. Winsorised for graphical scaling only
# (§18): no observation is dropped from any statistic.
_JUMP_AXIS_LIMIT_EUR = 400.0


def task_figures_border_jumps(
    jumps_file: Path = BORDER_JUMPS,
    detail_geometry_file: Path = DETAIL_GEOMETRY,
    distribution_table_file: Path = DISTRIBUTION_TABLE,
    border_type_table_file: Path = BORDER_TYPE_TABLE,
    comparison_group_file: Path = COMPARISON_GROUP_TABLE,
    top_table_file: Path = TOP_TABLE,
    fitness_file: Path = GEOMETRY_FITNESS_TABLE,
    distribution_figure: Annotated[Path, Product] = DISTRIBUTION_FIGURE,
    border_type_figure: Annotated[Path, Product] = BORDER_TYPE_FIGURE,
    detail_map_figure: Annotated[Path, Product] = DETAIL_MAP_FIGURE,
    interpretation_file: Annotated[Path, Product] = INTERPRETATION,
) -> None:
    """Read the P1.1 artefacts, draw the §13 figures, and register them all."""
    for path in (distribution_figure, interpretation_file):
        path.parent.mkdir(parents=True, exist_ok=True)

    jumps = pd.read_parquet(jumps_file)
    plausible = jumps.loc[
        ~jumps["possible_geometry_artefact"] & ~jumps["either_wogg_linked"]
    ]

    draw_distribution(plausible).write_html(distribution_figure)
    register_result(
        filename=distribution_figure.name,
        analysis_module=_MODULE,
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            "Neighbouring Gemeinden inside one Kreis almost always carry the "
            "same cap, while the cap steps by tens to hundreds of euro across a "
            "policy-region border."
        ),
        limitation=_RD_LIMITATION,
    )

    draw_border_type_boxplots(plausible).write_html(border_type_figure)
    register_result(
        filename=border_type_figure.name,
        analysis_module=_MODULE,
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            "The border-type gradient widens with household size: the larger "
            "the household, the larger the euro step across a Kreis boundary."
        ),
        limitation=_RD_LIMITATION,
    )

    draw_detail_maps(pd.read_parquet(detail_geometry_file)).write_html(
        detail_map_figure,
    )
    register_result(
        filename=detail_map_figure.name,
        analysis_module=_MODULE,
        dataset="border_jump_detail_geometry.parquet",
        script=_SCRIPT,
        interpretation=(
            "The ten largest plausible steps sit on long, unambiguous shared "
            "borders, most of them around Berlin and on the Saarland border."
        ),
        limitation=(
            "Selected on the largest euro jump, so these ten are the tail of "
            "the distribution and not a typical border. " + _RD_LIMITATION
        ),
    )

    interpretation_file.write_text(
        interpretation(
            pd.read_csv(distribution_table_file),
            pd.read_csv(border_type_table_file),
            pd.read_csv(comparison_group_file),
            pd.read_csv(top_table_file),
            _read_fitness(fitness_file),
            household_size=_HEADLINE_HOUSEHOLD_SIZE,
        ),
        encoding="utf-8",
    )
    register_result(
        filename=interpretation_file.name,
        analysis_module=_MODULE,
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            "The §21 four-part reading of the border-jump figure, with every "
            "number taken from the computed tables."
        ),
        limitation=_RD_LIMITATION,
    )


def draw_distribution(jumps: pd.DataFrame) -> go.Figure:
    """Histogram and ECDF of the euro jump, split by border type (§13 figures).

    Both panels answer the same question — how far does the cap step between
    two Gemeinden that share a border — and neither of them estimates
    anything. The histogram is clipped for readability only; the ECDF uses
    every observation.
    """
    headline = jumps.loc[jumps["household_size"] == _HEADLINE_HOUSEHOLD_SIZE]
    figure = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=(
            f"Distribution of |K_i − K_j|, h = {_HEADLINE_HOUSEHOLD_SIZE}",
            "Cumulative share of pairs at or below",
        ),
        horizontal_spacing=0.09,
    )
    for border_type, label in _BORDER_TYPE_LABELS.items():
        subset = headline.loc[headline["border_type"] == border_type]
        colour = _BORDER_TYPE_COLOURS[border_type]
        figure.add_trace(
            go.Histogram(
                x=subset["jump_eur"].clip(upper=_JUMP_AXIS_LIMIT_EUR),
                name=label,
                marker_color=colour,
                opacity=0.75,
                histnorm="probability",
                xbins={"start": 0.0, "end": _JUMP_AXIS_LIMIT_EUR, "size": 20.0},
                legendgroup=border_type,
            ),
            row=1,
            col=1,
        )
        ordered = subset["jump_eur"].sort_values().to_numpy()
        figure.add_trace(
            go.Scatter(
                x=ordered,
                y=(pd.RangeIndex(len(ordered)) + 1) / len(ordered),
                mode="lines",
                name=label,
                line={"color": colour, "width": 2},
                legendgroup=border_type,
                showlegend=False,
            ),
            row=1,
            col=2,
        )
    figure.update_layout(
        template=_TEMPLATE,
        barmode="overlay",
        title=(
            "Administrative border jumps in the maximum recognisable "
            "Bruttokaltmiete<br>"
            "<sup>Directly adjacent Gemeinde pairs sharing a boundary line of "
            f"at least {int(SHORT_BOUNDARY_THRESHOLD_M)} m, excluding pairs "
            f"touching a WoGG-linked Gemeinde ({_FIGURE_LINKAGE.value}, A12). "
            "Descriptive; not a regression-discontinuity design.</sup>"
        ),
        legend={"orientation": "h", "y": -0.18, "x": 0.0},
        font={"color": _DARK_GREY},
        margin={"t": 90, "b": 90},
    )
    figure.update_xaxes(
        title_text=f"|K_i − K_j| in €, clipped at {int(_JUMP_AXIS_LIMIT_EUR)}",
        row=1,
        col=1,
    )
    figure.update_xaxes(
        title_text="|K_i − K_j| in €",
        range=[0.0, _JUMP_AXIS_LIMIT_EUR],
        row=1,
        col=2,
    )
    figure.update_yaxes(title_text="Share of pairs", row=1, col=1)
    figure.update_yaxes(title_text="Cumulative share", range=[0.0, 1.0], row=1, col=2)
    return figure


def draw_border_type_boxplots(jumps: pd.DataFrame) -> go.Figure:
    """Boxplots of the euro jump by border type and household size (§13)."""
    figure = go.Figure()
    for border_type, label in _BORDER_TYPE_LABELS.items():
        subset = jumps.loc[jumps["border_type"] == border_type]
        figure.add_trace(
            go.Box(
                x=subset["household_size"],
                y=subset["jump_eur"],
                name=label,
                marker_color=_BORDER_TYPE_COLOURS[border_type],
                line={"width": 1},
                boxpoints=False,
            ),
        )
    figure.update_layout(
        template=_TEMPLATE,
        boxmode="group",
        title=(
            "Border jump by border type and household size<br>"
            "<sup>Whiskers at 1.5 × IQR; outliers hidden for legibility, not "
            "dropped from any statistic (§18).</sup>"
        ),
        xaxis_title="Household size h",
        yaxis_title="|K_i − K_j| in €",
        yaxis_range=[0.0, _JUMP_AXIS_LIMIT_EUR],
        legend={"orientation": "h", "y": -0.2, "x": 0.0},
        font={"color": _DARK_GREY},
        margin={"t": 90, "b": 90},
    )
    return figure


def draw_detail_maps(detail: pd.DataFrame) -> go.Figure:
    """Draw the ten largest plausible jumps as small equal-area detail maps.

    Each panel shows the two Gemeinden of one pair, the accent marking the
    higher cap. The panels are the tail of the distribution, chosen on the size
    of the step; they illustrate the discontinuity, they do not identify it.
    """
    ranks = sorted(detail["pair_rank"].unique())
    columns = 5
    rows = max(1, -(-len(ranks) // columns))
    figure = make_subplots(
        rows=rows,
        cols=columns,
        subplot_titles=[_panel_title(detail, rank) for rank in ranks],
        horizontal_spacing=0.02,
        vertical_spacing=0.10,
    )
    for position, rank in enumerate(ranks):
        row = position // columns + 1
        column = position % columns + 1
        panel = detail.loc[detail["pair_rank"] == rank]
        higher = "i" if panel["cap_i"].iloc[0] >= panel["cap_j"].iloc[0] else "j"
        for (side, _part), ring in panel.groupby(["side", "part"], sort=True):
            figure.add_trace(
                go.Scatter(
                    x=ring["x"],
                    y=ring["y"],
                    fill="toself",
                    mode="lines",
                    fillcolor=_ACCENT if side == higher else _LIGHT_GREY,
                    line={"color": _DARK_GREY, "width": 0.8},
                    hoverinfo="skip",
                    showlegend=False,
                ),
                row=row,
                col=column,
            )
        figure.update_xaxes(
            visible=False,
            row=row,
            col=column,
            scaleanchor=_axis_name("y", position),
            scaleratio=1.0,
        )
        figure.update_yaxes(visible=False, row=row, col=column)
    figure.update_layout(
        template=_TEMPLATE,
        height=340 * rows,
        title=(
            "The ten largest plausible border jumps<br>"
            "<sup>Accent marks the higher cap. Equal-area projection "
            "(EPSG:3035); each panel has its own extent. Descriptive, not an "
            "identification strategy.</sup>"
        ),
        font={"color": _DARK_GREY},
        margin={"t": 110},
    )
    for annotation in figure.layout.annotations:
        annotation.font.size = 10
    return figure


def _panel_title(detail: pd.DataFrame, rank: int) -> str:
    row = detail.loc[detail["pair_rank"] == rank].iloc[0]
    return (
        f"{row['gemeinde_i']} {row['cap_i']:.0f} € vs "
        f"{row['gemeinde_j']} {row['cap_j']:.0f} €<br>"
        f"<sub>h = {int(row['household_size'])}, step {row['jump_eur']:.0f} €, "
        f"{row['shared_boundary_m'] / 1000:.1f} km shared border</sub>"
    )


def _axis_name(prefix: str, position: int) -> str:
    return prefix if position == 0 else f"{prefix}{position + 1}"


def _read_fitness(path: Path) -> GeometryFitness:
    row = pd.read_csv(path).iloc[0]
    return GeometryFitness(
        n_features_reference=int(row["n_features_reference"]),
        n_features_candidate=int(row["n_features_candidate"]),
        n_pairs_reference=int(row["n_pairs_reference"]),
        n_pairs_candidate=int(row["n_pairs_candidate"]),
        n_destroyed=int(row["n_destroyed"]),
        n_fabricated=int(row["n_fabricated"]),
        n_overlapping_edges=int(row["n_overlapping_edges"]),
        n_lost_features=int(row["n_lost_features"]),
    )
