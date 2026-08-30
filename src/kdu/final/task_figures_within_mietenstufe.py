"""Draw the P0.4 figures and write the §21 interpretation.

Three figures come out of this module. The main one is §19 figure 3, boxplots
of `K/W` by Mietenstufe and household size with the `R²` and residual
dispersion beside them. The second shows the euro cap `K` itself, whose spread
is what a simulation actually mismeasures. The third shows the three splits
that carry the institutional argument: the § 12 WoGG threshold at 10,000
inhabitants, kreisfrei against kreisangehörig, and the D7 WoGG-linked group
whose `K/W` is pinned by construction.

Styling follows D12: the §19 figure program is deliberately austere. Grey is
the default ink, one accent colour marks the contrast a panel is about, and
nothing is drawn that the reader does not need.
"""

from pathlib import Path
from typing import Annotated

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pytask import Product

from kdu.analysis.task_within_mietenstufe import (
    DECOMPOSITION_TABLE,
    TABLE_3,
    WITHIN_MIETENSTUFE_FRAME,
)
from kdu.analysis.within_mietenstufe import (
    CAP_COLUMN,
    RATIO_COLUMN,
    Sample,
    Stratum,
    interpretation,
    stratified_dispersion,
    variance_decomposition_table,
)
from kdu.config import FIGURES, TABLES
from kdu.final.manifest import register_result

MAIN_FIGURE = FIGURES / "fig_within_mietenstufe_ratio.html"
CAP_FIGURE = FIGURES / "fig_within_mietenstufe_cap.html"
STRATA_FIGURE = FIGURES / "fig_within_mietenstufe_strata.html"
INTERPRETATION = TABLES / "within_mietenstufe_interpretation.md"

_MODULE = "P0.4"
_DATASET = "analysis_sample_main.parquet"
_SCRIPT = "src/kdu/final/task_figures_within_mietenstufe.py"

# The single caveat every P0.4 output has to be read with (D7).
_WOGG_LIMITATION = (
    "Gemeinden whose Kreis leans on the § 12 WoGG table plus the 10 % "
    "Sicherheitszuschlag have K/W compressed towards 1.10 — exactly fixed in "
    "`exact_ratio`, nearly so in the wider `linked_union` split used here — so "
    "every statistic is shown with and without them (A22)."
)

# Austere ink: grey for everything, one accent for the contrast in question.
_GREY = "#8c8c8c"
_DARK_GREY = "#4d4d4d"
_ACCENT = "#c2543a"
_TEMPLATE = "simple_white"

# Grey-to-accent ramp over the four household sizes of the main sample.
_HOUSEHOLD_COLOURS: tuple[str, ...] = ("#d4d4d4", "#a6a6a6", "#737373", _ACCENT)

_SAMPLE_LABELS: dict[str, str] = {
    Sample.ALL.value: "All Gemeinden",
    Sample.EXCLUDING_WOGG_LINKED.value: "Excluding WoGG-linked Gemeinden",
}


def task_figures_within_mietenstufe(
    frame_file: Path = WITHIN_MIETENSTUFE_FRAME,
    table_3_file: Path = TABLE_3,
    decomposition_file: Path = DECOMPOSITION_TABLE,
    main_figure_file: Annotated[Path, Product] = MAIN_FIGURE,
    cap_figure_file: Annotated[Path, Product] = CAP_FIGURE,
    strata_figure_file: Annotated[Path, Product] = STRATA_FIGURE,
    interpretation_file: Annotated[Path, Product] = INTERPRETATION,
) -> None:
    """Read the P0.4 outputs, draw the three figures, and register everything."""
    frame = pd.read_parquet(frame_file)
    table = pd.read_csv(table_3_file)
    decomposition = pd.read_csv(decomposition_file)
    main_figure_file.parent.mkdir(parents=True, exist_ok=True)

    build_ratio_figure(frame, table).write_html(main_figure_file)
    build_cap_figure(frame).write_html(cap_figure_file)
    build_strata_figure(frame).write_html(strata_figure_file)
    interpretation_file.write_text(
        _write_interpretation(frame, table, decomposition),
        encoding="utf-8",
    )

    _register_outputs(table)


def build_ratio_figure(frame: pd.DataFrame, table: pd.DataFrame) -> go.Figure:
    """Draw §19 figure 3: `K/W` by Mietenstufe and household size, with Table 3.

    The upper panel holds every Gemeinde and the lower one drops the WoGG-linked
    group, so the compression D7 warns about is visible as the difference
    between two panels drawn on one shared axis rather than as a footnote.

    Args:
        frame: Prepared analysis frame.
        table: The `table_3` output, rendered as the compact side table.

    Returns:
        The figure.

    """
    figure = make_subplots(
        rows=2,
        cols=2,
        column_widths=[0.7, 0.3],
        row_heights=[0.5, 0.5],
        vertical_spacing=0.11,
        horizontal_spacing=0.06,
        specs=[
            [{"type": "box"}, {"type": "table", "rowspan": 2}],
            [{"type": "box"}, None],
        ],
        subplot_titles=(
            _SAMPLE_LABELS[Sample.ALL.value],
            "R² and residual dispersion of log K",
            _SAMPLE_LABELS[Sample.EXCLUDING_WOGG_LINKED.value],
        ),
    )
    for row, sample in enumerate(Sample, start=1):
        subset = _subset(frame, sample)
        for trace in _household_boxes(subset, RATIO_COLUMN, show_legend=row == 1):
            figure.add_trace(trace, row=row, col=1)
        figure.add_hline(
            y=1.0,
            line_color=_DARK_GREY,
            line_width=1,
            line_dash="dot",
            row=row,
            col=1,
        )
    figure.add_trace(_table_trace(table), row=1, col=2)
    figure.update_yaxes(title_text="K / W", row=1, col=1)
    figure.update_yaxes(title_text="K / W", row=2, col=1)
    figure.update_xaxes(title_text="Mietenstufe", row=2, col=1)
    return _finalise(
        figure,
        title=(
            "Local KdU caps relative to the Wohngeld Höchstbetrag, within Mietenstufen"
        ),
        height=760,
    )


def build_cap_figure(frame: pd.DataFrame) -> go.Figure:
    """Draw the euro cap `K` by Mietenstufe, one panel per household size.

    Args:
        frame: Prepared analysis frame.

    Returns:
        The figure.

    """
    household_sizes = sorted(frame["household_size"].unique())
    figure = make_subplots(
        rows=2,
        cols=2,
        shared_xaxes=True,
        vertical_spacing=0.10,
        horizontal_spacing=0.07,
        subplot_titles=tuple(f"{size}-person household" for size in household_sizes),
    )
    for index, size in enumerate(household_sizes):
        row, column = divmod(index, 2)
        panel = frame.loc[frame["household_size"] == size]
        for sample in Sample:
            figure.add_trace(
                _box(
                    _subset(panel, sample),
                    CAP_COLUMN,
                    name=_SAMPLE_LABELS[sample.value],
                    colour=(_GREY if sample is Sample.ALL else _ACCENT),
                    show_legend=index == 0,
                ),
                row=row + 1,
                col=column + 1,
            )
    figure.update_yaxes(title_text="K in €/month", col=1)
    figure.update_xaxes(title_text="Mietenstufe", row=2)
    figure.update_layout(boxmode="group")
    return _finalise(
        figure,
        title="Local KdU caps within Mietenstufen, by household size",
        height=780,
    )


def build_strata_figure(frame: pd.DataFrame) -> go.Figure:
    """Draw the three splits that carry the institutional argument, for `h = 1`.

    Args:
        frame: Prepared analysis frame.

    Returns:
        The figure.

    """
    contrasts = (
        (
            "§ 12 WoGG classification",
            Stratum.POPULATION_BELOW_THRESHOLD,
            Stratum.POPULATION_AT_OR_ABOVE_THRESHOLD,
        ),
        ("Träger", Stratum.KREISFREI, Stratum.KREISANGEHOERIG),
        (
            "WoGG-linked Kreise (D7)",
            Stratum.WOGG_LINKED,
            Stratum.EXCLUDING_WOGG_LINKED,
        ),
    )
    figure = make_subplots(
        rows=1,
        cols=len(contrasts),
        shared_yaxes=True,
        horizontal_spacing=0.04,
        subplot_titles=tuple(title for title, _, _ in contrasts),
    )
    single = frame.loc[frame["household_size"] == 1]
    for column, (_, first, second) in enumerate(contrasts, start=1):
        for colour, stratum in ((_GREY, first), (_ACCENT, second)):
            figure.add_trace(
                _box(
                    single.loc[_stratum_mask(single, stratum)],
                    RATIO_COLUMN,
                    name=_label(stratum),
                    colour=colour,
                    show_legend=True,
                ),
                row=1,
                col=column,
            )
    figure.update_yaxes(title_text="K / W", col=1)
    figure.update_xaxes(title_text="Mietenstufe")
    figure.update_layout(boxmode="group")
    return _finalise(
        figure,
        title=(
            "Where the within-Mietenstufe spread of K/W comes from, "
            "single-person households"
        ),
        height=520,
    )


def _household_boxes(
    frame: pd.DataFrame,
    value_column: str,
    show_legend: bool,
) -> list[go.Box]:
    return [
        _box(
            frame.loc[frame["household_size"] == size],
            value_column,
            name=f"{size} person" if size == 1 else f"{size} persons",
            colour=_HOUSEHOLD_COLOURS[index % len(_HOUSEHOLD_COLOURS)],
            show_legend=show_legend,
        )
        for index, size in enumerate(sorted(frame["household_size"].unique()))
    ]


def _box(
    frame: pd.DataFrame,
    value_column: str,
    name: str,
    colour: str,
    show_legend: bool,
) -> go.Box:
    conditioned = frame.loc[frame["wogg_rent_level"].notna()]
    return go.Box(
        x=conditioned["wogg_rent_level"].astype("Int64").astype(str),
        y=conditioned[value_column],
        name=name,
        legendgroup=name,
        showlegend=show_legend,
        marker_color=colour,
        line_width=1,
        boxpoints=False,
        whiskerwidth=0.5,
    )


def _table_trace(table: pd.DataFrame) -> go.Table:
    rendered = pd.DataFrame(
        {
            "h": table["household_size"].astype(int),
            "Sample": table["sample"].map(
                {Sample.ALL.value: "all", Sample.EXCLUDING_WOGG_LINKED.value: "excl."},
            ),
            "R²": table["r_squared"].map("{:.3f}".format),
            "Resid. sd": table["residual_sd"].map("{:.3f}".format),
            "P90−P10 (€)": table["cap_p90_minus_p10_eur"].map("{:.0f}".format),
            "N": table["n_gemeinden"].map("{:,}".format),
        },
    ).sort_values(["h", "Sample"])
    return go.Table(
        header={
            "values": list(rendered.columns),
            "align": "right",
            "fill_color": "#f2f2f2",
            "line_color": _GREY,
            "font": {"size": 11, "color": _DARK_GREY},
        },
        cells={
            "values": [rendered[column] for column in rendered.columns],
            "align": "right",
            "fill_color": "white",
            "line_color": "#e6e6e6",
            "font": {"size": 11, "color": _DARK_GREY},
            "height": 22,
        },
        columnwidth=[0.5, 0.9, 0.8, 0.9, 1.1, 0.9],
    )


def _finalise(figure: go.Figure, title: str, height: int) -> go.Figure:
    figure.update_layout(
        template=_TEMPLATE,
        title={"text": title, "x": 0.0, "xanchor": "left"},
        boxmode="group",
        height=height,
        margin={"l": 70, "r": 30, "t": 90, "b": 60},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": -0.16,
            "x": 0.0,
            "title_text": "",
        },
        font={"color": _DARK_GREY, "size": 12},
    )
    figure.update_xaxes(showgrid=False)
    figure.update_yaxes(showgrid=True, gridcolor="#ededed", zeroline=False)
    for annotation in figure.layout.annotations:
        annotation.update(font={"size": 12, "color": _DARK_GREY}, x=annotation.x)
    return figure


def _subset(frame: pd.DataFrame, sample: Sample) -> pd.DataFrame:
    if sample is Sample.ALL:
        return frame
    return frame.loc[~frame["wogg_linked_flag"].astype(bool)]


def _stratum_mask(frame: pd.DataFrame, stratum: Stratum) -> pd.Series:
    masks = {
        Stratum.POPULATION_BELOW_THRESHOLD: frame["is_small_gemeinde"].astype(bool),
        Stratum.POPULATION_AT_OR_ABOVE_THRESHOLD: ~frame["is_small_gemeinde"].astype(
            bool,
        ),
        Stratum.KREISFREI: frame["is_kreisfrei"].astype(bool),
        Stratum.KREISANGEHOERIG: ~frame["is_kreisfrei"].astype(bool),
        Stratum.WOGG_LINKED: frame["wogg_linked_flag"].astype(bool),
        Stratum.EXCLUDING_WOGG_LINKED: ~frame["wogg_linked_flag"].astype(bool),
    }
    return masks[stratum]


def _label(stratum: Stratum) -> str:
    labels = {
        Stratum.POPULATION_BELOW_THRESHOLD: "under 10,000 inhabitants",
        Stratum.POPULATION_AT_OR_ABOVE_THRESHOLD: "10,000 and over",
        Stratum.KREISFREI: "kreisfrei",
        Stratum.KREISANGEHOERIG: "kreisangehörig",
        Stratum.WOGG_LINKED: "WoGG-linked",
        Stratum.EXCLUDING_WOGG_LINKED: "not WoGG-linked",
    }
    return labels[stratum]


def _write_interpretation(
    frame: pd.DataFrame,
    table: pd.DataFrame,
    decomposition: pd.DataFrame,
) -> str:
    return interpretation(
        table=table,
        cap_dispersion=stratified_dispersion(frame, value_column=CAP_COLUMN),
        ratio_dispersion=stratified_dispersion(
            frame,
            value_column=RATIO_COLUMN,
            deviation_thresholds=(),
        ),
        decomposition=(
            decomposition
            if not decomposition.empty
            else variance_decomposition_table(frame)
        ),
    )


def _register_outputs(table: pd.DataFrame) -> None:
    def read(sample: Sample, household_size: int, column: str) -> float:
        selected = table.loc[
            (table["sample"] == sample.value)
            & (table["household_size"] == household_size),
            column,
        ]
        return float(selected.to_numpy()[0])

    r_squared = read(Sample.ALL, 1, "r_squared")
    r_squared_excluding = read(Sample.EXCLUDING_WOGG_LINKED, 1, "r_squared")
    spread = read(Sample.ALL, 1, "cap_p90_minus_p10_eur")

    register_result(
        filename=MAIN_FIGURE.name,
        analysis_module=_MODULE,
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"Within one Mietenstufe the single-person KdU cap still spans "
            f"{spread:.0f} € between P10 and P90, and the Mietenstufe accounts "
            f"for only {r_squared:.0%} of the variation in log K "
            f"({r_squared_excluding:.0%} once WoGG-linked Gemeinden are dropped)."
        ),
        limitation=_WOGG_LIMITATION,
    )
    register_result(
        filename=CAP_FIGURE.name,
        analysis_module=_MODULE,
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            "The euro spread of the cap inside a Mietenstufe widens with "
            "household size, so a Mietenstufe-based proxy mismeasures larger "
            "Bedarfsgemeinschaften by the largest absolute amounts."
        ),
        limitation=_WOGG_LIMITATION,
    )
    register_result(
        filename=STRATA_FIGURE.name,
        analysis_module=_MODULE,
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            "The within-Mietenstufe spread of K/W is present for Gemeinden the "
            "WoGV classifies kreisweise and for those it classifies "
            "individually, and nearly vanishes only in the WoGG-linked group."
        ),
        limitation=_WOGG_LIMITATION,
    )
    register_result(
        filename=TABLE_3.name,
        analysis_module=_MODULE,
        dataset=_DATASET,
        script="src/kdu/analysis/task_within_mietenstufe.py",
        interpretation=(
            "Table 3 pairs R², the residual standard deviation and the "
            "within-Mietenstufe P90−P10 spread for every household size, with "
            "and without the WoGG-linked Gemeinden."
        ),
        limitation=_WOGG_LIMITATION,
    )
    register_result(
        filename=INTERPRETATION.name,
        analysis_module=_MODULE,
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            "The §21 four-part reading of the within-Mietenstufe heterogeneity, "
            "with every number computed from the sample."
        ),
        limitation=_WOGG_LIMITATION,
    )
