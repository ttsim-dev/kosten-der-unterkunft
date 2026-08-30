"""Draw the three §14 figures and write the §21 interpretation of P1.2.

The figures are the ones §14 lists: a binscatter of market–KdU pressure against
the non-recognised cost share, the BA recognition rate by decile of `K/W`, and
the three weightings of the mechanical proxy error side by side.

Every figure carries both A12 linkage groups as separate traces, because the
group a number belongs to changes what it means: inside the WoGG-linked group
`K/W` is a constant by construction and the binscatter's horizontal axis
collapses. Showing the traces together is what makes that visible.

Styling follows D12: grey is the default ink and one accent colour marks the
contrast each panel is about.
"""

from pathlib import Path
from typing import Annotated

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pytask import Product

from kdu.analysis.ba_validation import (
    LOG_MARKET_PRESSURE_COLUMN,
    MAIN_HOUSEHOLD_SIZES_LABEL,
    NON_RECOGNISED_COLUMN,
    RECOGNITION_COLUMN,
    SPECIFICATION_HOUSEHOLD_SIZES,
    LinkageGroup,
    ValidationSample,
    binscatter,
    interpretation,
    recognition_rate_by_decile,
    select_linkage_rows,
)
from kdu.analysis.task_ba_validation import (
    BA_VALIDATION_FRAME,
    COVERAGE_TABLE,
    RELEVANCE_TABLE,
    SPECIFICATIONS_TABLE,
    VARIATION_TABLE,
    WEIGHTED_DISTRIBUTION_TABLE,
)
from kdu.config import FIGURES, TABLES
from kdu.final.manifest import register_result

BINSCATTER_FIGURE = FIGURES / "fig_ba_validation_market_pressure.html"
DECILE_FIGURE = FIGURES / "fig_ba_validation_recognition_by_decile.html"
WEIGHTING_FIGURE = FIGURES / "fig_ba_validation_weighted_proxy_error.html"
INTERPRETATION = TABLES / "ba_validation_interpretation.md"

_MODULE = "P1.2"
_DATASET = "ba_validation_jobcenter_household.parquet"
_SCRIPT = "src/kdu/final/task_figures_ba_validation.py"

_GREY = "#8c8c8c"
_DARK_GREY = "#4d4d4d"
_LIGHT_GREY = "#d4d4d4"
_ACCENT = "#c2543a"
_TEMPLATE = "simple_white"

# The three linkage groups every §14 figure draws, and the ink each carries.
_FIGURE_GROUPS: tuple[tuple[LinkageGroup, str, str], ...] = (
    (LinkageGroup.ALL, "All Jobcenter", _DARK_GREY),
    (
        LinkageGroup.EXCLUDING_EXACT_RATIO,
        "Excluding K/W = 1.100 (exact_ratio)",
        _ACCENT,
    ),
    (
        LinkageGroup.EXCLUDING_LINKED_UNION,
        "Excluding WoGG-linked (linked_union)",
        _GREY,
    ),
)

# The three §8.2 weightings the third figure contrasts.
_WEIGHTING_LABELS: tuple[tuple[str, str, str], ...] = (
    ("unweighted", "Kreis, unweighted", _LIGHT_GREY),
    ("population", "Population-weighted", _GREY),
    ("bedarfsgemeinschaft", "Bedarfsgemeinschaft-weighted", _ACCENT),
)


def task_figures_ba_validation(
    frame_file: Path = BA_VALIDATION_FRAME,
    specifications_file: Path = SPECIFICATIONS_TABLE,
    relevance_file: Path = RELEVANCE_TABLE,
    variation_file: Path = VARIATION_TABLE,
    coverage_file: Path = COVERAGE_TABLE,
    weighted_distribution_file: Path = WEIGHTED_DISTRIBUTION_TABLE,
    binscatter_figure_file: Annotated[Path, Product] = BINSCATTER_FIGURE,
    decile_figure_file: Annotated[Path, Product] = DECILE_FIGURE,
    weighting_figure_file: Annotated[Path, Product] = WEIGHTING_FIGURE,
    interpretation_file: Annotated[Path, Product] = INTERPRETATION,
) -> None:
    """Read the P1.2 outputs, draw the three figures, and register everything."""
    frame = pd.read_parquet(frame_file)
    specifications = pd.read_csv(specifications_file)
    relevance = pd.read_csv(relevance_file)
    variation = pd.read_csv(variation_file)
    coverage = pd.read_csv(coverage_file, dtype=str)
    distributions = pd.read_csv(weighted_distribution_file)

    binscatter_figure_file.parent.mkdir(parents=True, exist_ok=True)
    interpretation_file.parent.mkdir(parents=True, exist_ok=True)

    build_market_pressure_figure(frame).write_html(binscatter_figure_file)
    build_decile_figure(frame).write_html(decile_figure_file)
    build_weighting_figure(distributions).write_html(weighting_figure_file)
    interpretation_file.write_text(
        interpretation(frame, specifications, relevance, variation, coverage),
        encoding="utf-8",
    )

    _register_outputs(specifications, variation)


def build_market_pressure_figure(frame: pd.DataFrame) -> go.Figure:
    """Draw §14 figure 1: market–KdU pressure against the non-recognised share.

    The horizontal axis is `log(M^market/K)`, the Zensus Bestandsmiete for the
    locally admissible Wohnfläche divided by the local cap. It is a market-stress
    indicator, never a statement about how many dwellings a searching household
    could find (§15.2, §20).

    Args:
        frame: The P1.2 validation frame.

    Returns:
        The figure.

    """
    figure = go.Figure()
    raw = _rows(frame, LinkageGroup.ALL)
    figure.add_trace(
        go.Scattergl(
            x=raw[LOG_MARKET_PRESSURE_COLUMN],
            y=raw[NON_RECOGNISED_COLUMN] * 100.0,
            mode="markers",
            marker={"size": 3, "color": _LIGHT_GREY, "opacity": 0.5},
            name="Jobcenter × household size",
            hoverinfo="skip",
            showlegend=True,
        ),
    )
    for group, label, colour in _FIGURE_GROUPS:
        binned = binscatter(
            _rows(frame, group),
            x_column=LOG_MARKET_PRESSURE_COLUMN,
            y_column=NON_RECOGNISED_COLUMN,
        )
        if binned.empty:
            continue
        figure.add_trace(
            go.Scatter(
                x=binned[LOG_MARKET_PRESSURE_COLUMN],
                y=binned[NON_RECOGNISED_COLUMN] * 100.0,
                mode="lines+markers",
                line={"color": colour, "width": 2},
                marker={"size": 7, "color": colour},
                name=label,
                hovertemplate=(
                    "log(M/K) %{x:.3f}<br>non-recognised %{y:.2f} %"
                    "<br>%{customdata} observations<extra></extra>"
                ),
                customdata=binned["n_obs"],
            ),
        )
    figure.update_layout(
        template=_TEMPLATE,
        title=(
            "Market–KdU pressure and the non-recognised share of the "
            "Bruttokaltmiete<br><sub>Jobcenter × household size, §14.3 main "
            "sample; equal-count bins</sub>"
        ),
        xaxis_title="log(Zensus Bestandsmiete for A<sup>max</sup> / KdU cap K)",
        yaxis_title="Non-recognised share N<sup>BA</sup> (%)",
        legend={"orientation": "h", "y": -0.2},
        margin={"l": 70, "r": 30, "t": 90, "b": 90},
    )
    return figure


def build_decile_figure(frame: pd.DataFrame) -> go.Figure:
    """Draw §14 figure 2: the BA recognition rate by decile of `K/W`.

    The right panel shows how much identifying variation each decile carries,
    because in the WoGG-linked groups `K/W` is pinned at 1.100 and the deciles
    are then a partition of a constant.

    Args:
        frame: The P1.2 validation frame.

    Returns:
        The figure.

    """
    figure = make_subplots(
        rows=1,
        cols=2,
        column_widths=[0.62, 0.38],
        horizontal_spacing=0.11,
        subplot_titles=(
            "Recognition rate R<sup>BA</sup> by decile of K/W",
            "Mean K/W inside each decile",
        ),
    )
    for group, label, colour in _FIGURE_GROUPS:
        deciles = recognition_rate_by_decile(frame, linkage_group=group)
        if deciles.empty:
            continue
        figure.add_trace(
            go.Scatter(
                x=deciles["decile"],
                y=deciles[RECOGNITION_COLUMN] * 100.0,
                mode="lines+markers",
                line={"color": colour, "width": 2},
                marker={"size": 7, "color": colour},
                name=label,
                hovertemplate=(
                    "decile %{x}<br>R<sup>BA</sup> %{y:.2f} %<extra></extra>"
                ),
            ),
            row=1,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=deciles["decile"],
                y=deciles["cap_over_benchmark"],
                mode="lines+markers",
                line={"color": colour, "width": 2, "dash": "dot"},
                marker={"size": 6, "color": colour},
                name=label,
                showlegend=False,
                hovertemplate="decile %{x}<br>K/W %{y:.3f}<extra></extra>",
            ),
            row=1,
            col=2,
        )
    figure.add_hline(
        y=1.10,
        line={"color": _GREY, "width": 1, "dash": "dash"},
        annotation_text="§ 12 WoGG table + 10 %",
        annotation_position="bottom right",
        row=1,
        col=2,
    )
    figure.update_xaxes(title_text="Decile of K/W", row=1, col=1, dtick=1)
    figure.update_xaxes(title_text="Decile of K/W", row=1, col=2, dtick=1)
    figure.update_yaxes(title_text="R<sup>BA</sup> (%)", row=1, col=1)
    figure.update_yaxes(title_text="K/W", row=1, col=2)
    figure.update_layout(
        template=_TEMPLATE,
        title=(
            "Recognition of the actual Bruttokaltmiete along the local cap "
            "ratio<br><sub>Jobcenter × household size h = 1…4, §14.3 main "
            "sample</sub>"
        ),
        legend={"orientation": "h", "y": -0.25},
        margin={"l": 70, "r": 30, "t": 110, "b": 100},
    )
    return figure


def build_weighting_figure(distributions: pd.DataFrame) -> go.Figure:
    """Draw §14 figure 3: the proxy error under the three weightings.

    Each household size shows the P10–P90 band and the median of the mechanical
    proxy error `K − W` across Kreise, unweighted, weighted by population and
    weighted by the BA stock of Bedarfsgemeinschaften. The three do not
    coincide, and §8.2 is explicit that they answer different questions.

    Args:
        distributions: `ba_validation_weighted_distributions.csv`.

    Returns:
        The figure.

    """
    figure = go.Figure()
    wide = distributions.pivot_table(
        index=["household_size", "weighting"],
        columns="quantile",
        values="value",
    ).reset_index()
    offsets = {"unweighted": -0.22, "population": 0.0, "bedarfsgemeinschaft": 0.22}
    for weighting, label, colour in _WEIGHTING_LABELS:
        rows = wide.loc[wide["weighting"] == weighting].sort_values("household_size")
        position = rows["household_size"].astype(float) + offsets[weighting]
        figure.add_trace(
            go.Scatter(
                x=position,
                y=rows[0.5],
                mode="markers",
                marker={"size": 10, "color": colour, "symbol": "diamond"},
                name=label,
                error_y={
                    "type": "data",
                    "symmetric": False,
                    "array": rows[0.9] - rows[0.5],
                    "arrayminus": rows[0.5] - rows[0.1],
                    "color": colour,
                    "width": 5,
                },
                hovertemplate=("median %{y:.1f} €<extra></extra>"),
            ),
        )
    figure.add_hline(y=0.0, line={"color": _GREY, "width": 1})
    figure.update_layout(
        template=_TEMPLATE,
        title=(
            "Mechanical proxy error K − W under three weightings<br><sub>Kreis "
            "means; marker is the median, whiskers span P10 to P90</sub>"
        ),
        xaxis={"title": "Household size h", "dtick": 1},
        yaxis_title="K − W (€ per month)",
        legend={"orientation": "h", "y": -0.2},
        margin={"l": 70, "r": 30, "t": 90, "b": 90},
    )
    return figure


def _rows(frame: pd.DataFrame, group: LinkageGroup) -> pd.DataFrame:
    selected = select_linkage_rows(
        frame,
        group,
        ValidationSample.MAIN,
        SPECIFICATION_HOUSEHOLD_SIZES,
    )
    return selected.replace([np.inf, -np.inf], np.nan)


def _register_outputs(specifications: pd.DataFrame, variation: pd.DataFrame) -> None:
    beta = _coefficient(specifications, "market_vs_cap", "all")
    beta_cap = _coefficient(specifications, "cap_vs_benchmark", "all")
    degenerate_sd = float(
        variation.loc[
            (variation["linkage_group"] == LinkageGroup.EXACT_RATIO_ONLY.value)
            & (variation["regressor"] == "log_cap_over_benchmark"),
            "sd",
        ].iloc[0],
    )
    register_result(
        filename=INTERPRETATION.name,
        analysis_module=_MODULE,
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"The §21 four-part reading of the §14 figures, with every number "
            f"taken from the computed tables: the headline is "
            f"β = {beta_cap:+.4f} on log(K/W), conditional on Bundesland and "
            f"household-size fixed effects."
        ),
        limitation=(
            "The conditional nature belongs in the sentence, not a footnote: "
            "the unconditional decile gradient is far flatter than β implies, "
            "and the two must never be shown apart. Nothing here is a causal "
            "effect (A20)."
        ),
    )
    register_result(
        filename=BINSCATTER_FIGURE.name,
        analysis_module=_MODULE,
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"Where the Zensus Bestandsmiete stands high relative to the local "
            f"KdU cap, a larger share of the actual Bruttokaltmiete goes "
            f"unrecognised: β = {beta:+.4f} on log(M/K) with a "
            f"Jobcenter-clustered standard error."
        ),
        limitation=(
            "The Zensus figure is a Nettokaltmiete Bestandsmiete set against a "
            "Bruttokaltmiete cap, so M/K understates market pressure by the "
            "kalte Betriebskosten and is an indicator, not a level."
        ),
    )
    register_result(
        filename=DECILE_FIGURE.name,
        analysis_module=_MODULE,
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"The raw recognition rate barely moves across deciles of K/W; the "
            f"association appears once the Bundesland and household size are "
            f"held fixed, at β = {beta_cap:+.4f} on log(K/W)."
        ),
        limitation=(
            f"Inside the exact_ratio group K/W is 1.100 by construction — the "
            f"standard deviation of log(K/W) there is {degenerate_sd:.4f} — so "
            f"its deciles partition a constant and carry no information."
        ),
    )
    register_result(
        filename=WEIGHTING_FIGURE.name,
        analysis_module=_MODULE,
        dataset="proxy_error_gemeinde_household.parquet",
        script=_SCRIPT,
        interpretation=(
            "Weighting Kreise by their BA stock of Bedarfsgemeinschaften moves "
            "the median proxy error well away from the unweighted Kreis median, "
            "so which weighting a paper reports changes the headline number."
        ),
        limitation=(
            "BA publishes no Gemeinde-level BG stock, so the Kreis stock is the "
            "finest weight available and the within-Kreis split of P0.3 is an "
            "assumption."
        ),
    )


def _coefficient(specifications: pd.DataFrame, specification: str, group: str) -> float:
    rows = specifications.loc[
        (specifications["specification"] == specification)
        & (specifications["linkage_group"] == group)
        & (specifications["validation_sample"] == ValidationSample.MAIN.value)
        & (specifications["household_sizes"] == MAIN_HOUSEHOLD_SIZES_LABEL)
    ]
    return float(rows["estimate"].iloc[0]) if len(rows) else float("nan")
