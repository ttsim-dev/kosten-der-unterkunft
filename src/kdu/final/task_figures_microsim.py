"""The §12.8 and §11 figure program for P0.6 and P0.7.

Five simulation figures and the administrative-need figure, in the austere
styling D12 reserves for the §19 program: one template, no gridline clutter, the
household as the facet so nothing turns into a spaghetti chart.

Every figure carries the D7 pair, split on `wogg_linked_flag` — the
`linked_union` group of A12, the union of the notes-regex and `K/W` detectors,
1,752 of the 9,323 comparable Gemeinden. Showing only the pooled distribution
would present as an empirical regularity what is, for the Gemeinden that read
their KdU-Obergrenze off the § 12 WoGG table plus a 10 % Sicherheitszuschlag,
a definitional identity.

Those Gemeinden are `exact_ratio`, the narrower group whose `K/W` is 1.100
within 5e-4, and `linked_union` is neither identical to it nor a superset of it.
Every legend and manifest entry here therefore names `linked_union`, and the
+10 % identity is attributed to `exact_ratio` alone.
"""

from pathlib import Path
from typing import Annotated, Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from pytask import Product

from kdu.config import BLD, FIGURES, MODEL_HOUSEHOLDS, catalog_path
from kdu.final.manifest import register_result
from kdu.geodata import load_geojson, simplify_feature_collection
from kdu.simulation.needs_level import NEEDS_MEASURE_LABEL

# Plotly template for the §19 program. Deliberately plain: this is print output,
# not the interactive QC map of D12.
FIGURE_TEMPLATE = "simple_white"

# Grid decimals the boundary geometry is snapped to, matching the QC map.
GEOMETRY_DECIMALS = 2

# The household whose exit-threshold shift the §12.8 map shows.
MAP_HOUSEHOLD_KEY = "single_35"

# Diverging colour scale for signed differences, and a sequential one for levels.
DIVERGING_SCALE = "RdBu"
SEQUENTIAL_SCALE = "Viridis"

# Legend wording for the D7 split, used identically on every figure. The split
# is `wogg_linked_flag`, the `linked_union` group of A12, so the label names
# that group rather than claiming the K = 1.10 × W identity for all of it.
FLAG_LABELS: dict[bool, str] = {
    False: "independent schlüssiges Konzept",
    True: "WoGG-linked (linked_union, A12)",
}

_MODULE = "src/kdu/final/task_figures_microsim.py"


def task_figures_microsim(
    gemeinde_results: Path = BLD / "microsim_gemeinde.parquet",
    budget_curves: Path = BLD / "microsim_budget_curves.parquet",
    needs_level: Path = BLD / "needs_level_gemeinde.parquet",
    geojson_path: Path = catalog_path("gemeinden_geojson"),
    exit_threshold_figure: Annotated[Path, Product] = (
        FIGURES / "fig_microsim_delta_exit_threshold.html"
    ),
    hours_figure: Annotated[Path, Product] = (
        FIGURES / "fig_microsim_hours_equivalent.html"
    ),
    budget_curve_figure: Annotated[Path, Product] = (
        FIGURES / "fig_microsim_budget_curves.html"
    ),
    map_figure: Annotated[Path, Product] = (
        FIGURES / "fig_microsim_exit_threshold_map.html"
    ),
    scatter_figure: Annotated[Path, Product] = (
        FIGURES / "fig_microsim_proxy_error_vs_delta_exit.html"
    ),
    needs_figure: Annotated[Path, Product] = (
        FIGURES / "fig_needs_level_distribution.html"
    ),
) -> None:
    """Write the five §12.8 figures and the §11 main figure, and register them."""
    pio.templates.default = FIGURE_TEMPLATE
    results = _prepare(pd.read_parquet(gemeinde_results))
    curves = pd.read_parquet(budget_curves)
    need = pd.read_parquet(needs_level)

    _write(build_exit_threshold_figure(results), exit_threshold_figure)
    _write(build_hours_figure(results), hours_figure)
    _write(build_budget_curve_figure(curves), budget_curve_figure)
    _write(
        build_exit_threshold_map(results, _load_boundaries(geojson_path)),
        map_figure,
    )
    _write(build_proxy_error_scatter(results), scatter_figure)
    _write(build_needs_level_figure(need), needs_figure)
    _register(results, need)


def build_exit_threshold_figure(results: pd.DataFrame) -> go.Figure:
    """§12.8 figure 1: the distribution of `Δy*` by Modellhaushalt."""
    figure = px.box(
        results,
        x="household_label",
        y="delta_exit_threshold_m",
        color="wogg_link_label",
        points=False,
        labels={
            "household_label": "",
            "delta_exit_threshold_m": "Δy* (euro per month)",
            "wogg_link_label": "",
        },
        title=(
            "Shift in the Transfer-Ausstiegsschwelle when the local KdU-Obergrenze "
            "replaces the Wohngeld-Höchstbetrag"
        ),
    )
    figure.add_hline(y=0, line_width=1, line_color="#888888")
    return _tidy(figure)


def build_hours_figure(results: pd.DataFrame) -> go.Figure:
    """§12.8 figure 2: the weekly Mindestlohn-hours equivalent of `Δy*`."""
    figure = px.box(
        results,
        x="household_label",
        y="delta_hours_per_week",
        color="wogg_link_label",
        points=False,
        labels={
            "household_label": "",
            "delta_hours_per_week": "ΔH (weekly hours at 13.90 €/h)",
            "wogg_link_label": "",
        },
        title=(
            "Weekly working hours at the Mindestlohn equivalent to the shift in the "
            "exit threshold"
        ),
    )
    figure.add_hline(y=0, line_width=1, line_color="#888888")
    return _tidy(figure)


def build_budget_curve_figure(curves: pd.DataFrame) -> go.Figure:
    """§12.8 figure 3: budget curves at the P10, median and P90 proxy error."""
    frame = curves.assign(
        scenario_label=lambda data: data["scenario"].map(
            {"K": "K: local KdU-Obergrenze", "W": "W: Wohngeld-Höchstbetrag"},
        ),
        household_label=lambda data: data["household_key"].map(
            {key: household.label for key, household in MODEL_HOUSEHOLDS.items()},
        ),
    )
    figure = px.line(
        frame.sort_values("gross_income_m"),
        x="gross_income_m",
        y="disposable_income_m",
        color="quantile_label",
        line_dash="scenario_label",
        facet_col="household_label",
        facet_col_wrap=2,
        labels={
            "gross_income_m": "gross monthly income (euro)",
            "disposable_income_m": "disposable income (euro per month)",
            "quantile_label": "proxy-error quantile",
            "scenario_label": "",
        },
        title="Budget curves under the two housing-cost parameters",
    )
    figure.for_each_annotation(lambda note: note.update(text=note.text.split("=")[-1]))
    return _tidy(figure, height=760)


def build_exit_threshold_map(
    results: pd.DataFrame,
    geojson: dict[str, Any],
) -> go.Figure:
    """§12.8 figure 4: where the exit threshold moves, for the single-person household."""
    features = pd.DataFrame(
        {
            "fid": [feature["properties"]["fid"] for feature in geojson["features"]],
            "ags": [
                _ags_8(feature["properties"]["gem_code"])
                for feature in geojson["features"]
            ],
        },
    )
    map_household_key = MAP_HOUSEHOLD_KEY
    values = results.query("household_key == @map_household_key").loc[
        :,
        ["ags", "delta_exit_threshold_m", "gemeinde", "kreis"],
    ]
    frame = features.merge(values, on="ags", how="left", validate="one_to_one")
    limit = float(frame["delta_exit_threshold_m"].abs().quantile(0.99))
    figure = px.choropleth(
        frame,
        geojson=geojson,
        locations="fid",
        featureidkey="properties.fid",
        color="delta_exit_threshold_m",
        color_continuous_scale=DIVERGING_SCALE,
        range_color=(-limit, limit),
        hover_data=["gemeinde", "kreis"],
        labels={"delta_exit_threshold_m": "Δy* (€/month)"},
        title=(
            "Shift in the Transfer-Ausstiegsschwelle, single adult aged 35, "
            "colour scale winsorised at the 99th percentile for legibility"
        ),
    )
    figure.update_geos(fitbounds="locations", visible=False)
    figure.update_traces(marker_line_width=0)
    return _tidy(figure, height=820)


def build_proxy_error_scatter(results: pd.DataFrame) -> go.Figure:
    """§12.8 figure 5: `K − W` against `Δy*`."""
    figure = px.scatter(
        results,
        x="proxy_error_m",
        y="delta_exit_threshold_m",
        color="wogg_link_label",
        facet_col="household_label",
        facet_col_wrap=2,
        opacity=0.35,
        render_mode="webgl",
        labels={
            "proxy_error_m": "K − W (euro per month)",
            "delta_exit_threshold_m": "Δy* (euro per month)",
            "wogg_link_label": "",
        },
        title="The proxy error and the shift in the exit threshold it produces",
    )
    figure.for_each_annotation(lambda note: note.update(text=note.text.split("=")[-1]))
    return _tidy(figure, height=760)


def build_needs_level_figure(need: pd.DataFrame) -> go.Figure:
    """§11 main figure: the regional distribution of `B^K` and `B^W`."""
    long = pd.concat(
        [
            need.assign(basis="B^K: local KdU-Obergrenze", value=need["need_kdu_m"]),
            need.assign(basis="B^W: Wohngeld-Höchstbetrag", value=need["need_wogg_m"]),
        ],
        ignore_index=True,
    ).dropna(subset=["value"])
    labels = {key: household.label for key, household in MODEL_HOUSEHOLDS.items()}
    figure = px.box(
        long.assign(household_label=long["household_key"].map(labels)),
        x="household_label",
        y="value",
        color="basis",
        points=False,
        labels={
            "household_label": "",
            "value": f"{NEEDS_MEASURE_LABEL} (euro per month)",
            "basis": "",
        },
        title=(
            f"Regional distribution of the {NEEDS_MEASURE_LABEL}; "
            "heating is not included"
        ),
    )
    return _tidy(figure)


def _prepare(results: pd.DataFrame) -> pd.DataFrame:
    labels = {key: household.label for key, household in MODEL_HOUSEHOLDS.items()}
    return results.assign(
        household_label=results["household_key"].map(labels),
        wogg_link_label=results["wogg_linked_flag"]
        .fillna(value=False)
        .map(FLAG_LABELS),
    ).dropna(subset=["delta_exit_threshold_m"])


def _load_boundaries(path: Path) -> dict[str, Any]:
    return simplify_feature_collection(
        load_geojson(path),
        decimals=GEOMETRY_DECIMALS,
    )


def _ags_8(value: object) -> str:
    code = value[0] if isinstance(value, list) else value
    text = str(code)
    if len(text) <= 8:
        return text.zfill(8)
    text = text.zfill(12)
    return f"{text[:5]}{text[-3:]}"


def _tidy(figure: go.Figure, height: int = 600) -> go.Figure:
    figure.update_layout(
        height=height,
        template=FIGURE_TEMPLATE,
        legend={"orientation": "h", "y": -0.15},
        margin={"l": 60, "r": 30, "t": 90, "b": 80},
        title={"font": {"size": 15}},
    )
    return figure


def _write(figure: go.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(path, include_plotlyjs="cdn")


def _register(results: pd.DataFrame, need: pd.DataFrame) -> None:
    """Record every figure with a §21-style interpretation built from real numbers."""
    map_household_key = MAP_HOUSEHOLD_KEY
    single = results.query("household_key == @map_household_key")
    unflagged = single.query("not wogg_linked_flag.fillna(False)")
    median_all = single["delta_exit_threshold_m"].median()
    median_unflagged = unflagged["delta_exit_threshold_m"].median()
    median_hours = single["delta_hours_per_week"].median()
    flagged_share = 100.0 * float(single["wogg_linked_flag"].fillna(value=False).mean())
    need_single = need.query("household_key == @map_household_key")
    need_range = float(
        need_single["need_kdu_m"].max() - need_single["need_kdu_m"].min(),
    )
    d7_limitation = (
        f"{flagged_share:.1f} % of Gemeinden are in the `linked_union` group of "
        f"A12 (`wogg_linked_flag`), which is broader than and not a superset of "
        f"the `exact_ratio` Gemeinden whose difference is a definitional +10 % "
        f"of W; excluding it moves the median Δy* from {median_all:,.0f} € to "
        f"{median_unflagged:,.0f} €."
    )
    karenzzeit_limitation = (
        "All Δ are conditional on the cap being in force: inside the § 22 Abs. 1 "
        "Karenzzeit actual Unterkunftskosten are recognised in full and the proxy "
        "error is identically zero."
    )
    entries = [
        (
            "fig_microsim_delta_exit_threshold.html",
            f"Substituting the Wohngeld-Höchstbetrag for the local KdU-Obergrenze "
            f"moves the simulated Transfer-Ausstiegsschwelle of a single adult by a "
            f"median of {median_all:,.0f} € per month.",
            d7_limitation,
        ),
        (
            "fig_microsim_hours_equivalent.html",
            f"The median shift is worth {median_hours:,.1f} weekly hours at the 2026 "
            f"Mindestlohn of 13.90 €/h.",
            karenzzeit_limitation,
        ),
        (
            "fig_microsim_budget_curves.html",
            "At the P10, median and P90 of the proxy error the two parameter "
            "choices trace visibly different budget curves, and the gap persists "
            "until the higher of the two exit thresholds.",
            "Rent is set to max(K, W), a construction scenario that isolates the "
            "maximum mechanical difference, not a typical market rent.",
        ),
        (
            "fig_microsim_exit_threshold_map.html",
            "The shift in the exit threshold is regionally patterned rather than "
            "noise, and changes sign across Kreis borders.",
            "The colour scale is winsorised at the 99th percentile for legibility; "
            "no observation is excluded from any statistic.",
        ),
        (
            "fig_microsim_proxy_error_vs_delta_exit.html",
            "The shift in the exit threshold is close to linear in the proxy error, "
            "so a model's error in the housing parameter carries through to its "
            "simulated benefit range almost one for one.",
            d7_limitation,
        ),
        (
            "fig_needs_level_distribution.html",
            f"Nationally uniform Regelbedarfe imply no uniform administrative need: "
            f"the {NEEDS_MEASURE_LABEL} of a single adult spans "
            f"{need_range:,.0f} € across Gemeinden.",
            "Heating is excluded, so this is not a full Existenzminimum.",
        ),
    ]
    for filename, interpretation, limitation in entries:
        from_needs_level = filename.startswith("fig_needs")
        register_result(
            filename=filename,
            analysis_module="P0.6" if from_needs_level else "P0.7",
            dataset=(
                "needs_level_gemeinde.parquet"
                if from_needs_level
                else "microsim_gemeinde.parquet"
            ),
            script=_MODULE,
            interpretation=interpretation,
            limitation=limitation,
        )
