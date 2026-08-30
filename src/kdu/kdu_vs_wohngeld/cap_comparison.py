"""How far a local KdU cap departs from the statutory fallback.

Where a Kreis publishes no schlüssiges Konzept, BSG case law fixes the
Angemessenheitsgrenze at the Wohngeld Höchstbetrag plus a Sicherheitszuschlag
of 10 %. That fallback is the standard every local rule is measured against
here, in two ways:

- the departure at a given household size, as a euro difference, a ratio and a
  log ratio;
- the spread of that ratio across household sizes within one Gemeinde, which
  states how far a single per-Gemeinde correction factor can carry a
  tax-transfer model that has only the fallback.

Every distribution is reported for two populations at once. Some Kreise appear
to apply the fallback unchanged, in which case their ratio is one by
construction rather than by decision — but the documents that would settle
this were not found, so the suspicion is unverified and neither population is
subordinate to the other.

The functions here are pure: they take frames and return frames or figures.
{mod}`kdu.kdu_vs_wohngeld.task_cap_comparison` owns the reading and writing.
"""

from enum import StrEnum
from typing import cast

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

from kdu.config import WeightingScheme
from kdu.joins import merge_without_duplicating
from kdu.weighting import (
    weighted_mean,
    weighted_quantile,
    weighted_share,
    weighted_standard_deviation,
)

pio.templates.default = "plotly_dark"

# Household sizes over which the ratio's spread within a Gemeinde is measured.
# Sizes above four are published by too few Träger to compare across regions.
SPREAD_HOUSEHOLD_SIZES: tuple[int, ...] = (1, 2, 3, 4)

# A spread of this many ratio points or more means no single correction factor
# per Gemeinde reproduces the local cap at every household size.
MATERIAL_SPREAD_THRESHOLD = 0.05

# The unemphasised series and the one carrying the claim.
NEUTRAL_COLOUR = "#9aa0a6"
ACCENT_COLOUR = "#e8833a"


class AnalysisPopulation(StrEnum):
    """The two populations every distribution is reported for."""

    ALL_GEMEINDEN = "all_gemeinden"
    """Every Gemeinde with both a local cap and a statutory fallback."""
    EXCLUDING_SUSPECTED_FALLBACK = "excluding_suspected_fallback"
    """Dropping the Kreise that appear to apply the fallback unchanged."""


POPULATION_LABELS: dict[AnalysisPopulation, str] = {
    AnalysisPopulation.ALL_GEMEINDEN: "All Gemeinden",
    AnalysisPopulation.EXCLUDING_SUSPECTED_FALLBACK: "Excluding suspected fallback",
}


def build_cap_comparison(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    gemeinden: pd.DataFrame,
) -> pd.DataFrame:
    """Join the local cap to its statutory fallback and measure the departure.

    Args:
        caps: The local caps, keyed `ags` by `household_size`.
        fallback: The statutory benchmark, keyed the same way.
        gemeinden: Gemeinde names, Kreis, Bundesland and population, keyed `ags`.

    Returns:
        One row per `ags` and `household_size`, carrying `cap_difference_eur`,
        `cap_ratio` and `log_cap_ratio` alongside the inputs they derive from.
        A row without a Mietenstufe has no fallback and so no comparison; the
        three measures are missing there rather than dropped.

    """
    _fail_if_columns_absent(caps, ("ags", "household_size", "kdu_cap"))
    _fail_if_columns_absent(
        fallback,
        ("ags", "household_size", "wohngeld_fallback_cap", "wohngeld_rule_suspected"),
    )
    _fail_if_columns_absent(gemeinden, ("ags", "district_ags", "state_code"))

    frame = merge_without_duplicating(
        caps,
        fallback,
        on=("ags", "household_size"),
    )
    frame = merge_without_duplicating(frame, gemeinden, on=("ags",))
    return frame.assign(
        cap_difference_eur=lambda df: df["kdu_cap"] - df["wohngeld_fallback_cap"],
        cap_ratio=lambda df: df["kdu_cap"] / df["wohngeld_fallback_cap"],
        log_cap_ratio=lambda df: _natural_log(df["cap_ratio"]),
    )


def cap_ratio_spread_across_household_sizes(frame: pd.DataFrame) -> pd.DataFrame:
    """Measure how far a Gemeinde's departure moves with household size.

    For each Gemeinde the ratio of local cap to fallback is read at household
    sizes one to four and the spread is the largest minus the smallest. A
    Gemeinde whose rule is a constant multiple of the fallback has a spread of
    zero; a large spread means the local rule and the statutory table rise with
    household size at different rates.

    The measure is taken on the ratio itself rather than its logarithm, so it
    reads directly as ratio points of the fallback.

    Args:
        frame: The output of {func}`build_cap_comparison`.

    Returns:
        One row per Gemeinde observed at every size in
        {data}`SPREAD_HOUSEHOLD_SIZES`, with `cap_ratio_spread` and the
        `wohngeld_rule_suspected` marker carried through. Gemeinden missing any
        of those sizes are absent, because a spread over a subset is not
        comparable with one over all four.

    """
    _fail_if_columns_absent(frame, ("ags", "household_size", "cap_ratio"))
    observed = frame.loc[
        frame["household_size"].isin(SPREAD_HOUSEHOLD_SIZES),
        ["ags", "household_size", "cap_ratio"],
    ].dropna(subset=["cap_ratio"])

    by_size = observed.pivot_table(
        index="ags",
        columns="household_size",
        values="cap_ratio",
        aggfunc="mean",
    ).reindex(columns=list(SPREAD_HOUSEHOLD_SIZES))
    complete = by_size.dropna()
    spread = (complete.max(axis=1) - complete.min(axis=1)).rename("cap_ratio_spread")

    markers = (
        frame.loc[
            frame["household_size"] == SPREAD_HOUSEHOLD_SIZES[0],
            ["ags", "wohngeld_rule_suspected"],
        ]
        .drop_duplicates(subset="ags")
        .set_index("ags")
    )
    return spread.to_frame().join(markers, how="left").reset_index()


def bedarfsgemeinschaft_weights(wohnkostenstatistik: pd.DataFrame) -> pd.DataFrame:
    """Return SGB II Bedarfsgemeinschaften per Kreis and household size.

    Several Jobcenter can serve one Kreis, so their stocks are added together.

    Args:
        wohnkostenstatistik: The cleaned Bundesagentur table.

    Returns:
        One row per `district_ags` and `household_size`, with
        `bedarfsgemeinschaften`.

    """
    _fail_if_columns_absent(
        wohnkostenstatistik,
        ("district_ags", "household_size", "bedarfsgemeinschaften"),
    )
    return (
        wohnkostenstatistik.groupby(["district_ags", "household_size"], as_index=False)[
            "bedarfsgemeinschaften"
        ]
        .sum()
        .astype({"household_size": "int64"})
    )


def attach_weights(frame: pd.DataFrame, weights: pd.DataFrame) -> pd.DataFrame:
    """Attach both weighting schemes as columns named after them.

    Args:
        frame: The output of {func}`build_cap_comparison`.
        weights: The output of {func}`bedarfsgemeinschaft_weights`.

    Returns:
        `frame` with one column per member of
        {class}`kdu.config.WeightingScheme`. A Gemeinde in a Kreis the
        Bundesagentur does not report carries a Bedarfsgemeinschaft weight of
        zero, so it drops out of that scheme without dropping out of the other.

    """
    attached = merge_without_duplicating(
        frame,
        weights,
        on=("district_ags", "household_size"),
    )
    return attached.assign(
        **{
            WeightingScheme.GEMEINDE_UNWEIGHTED.value: 1.0,
            WeightingScheme.BEDARFSGEMEINSCHAFT.value: lambda df: df[
                "bedarfsgemeinschaften"
            ].fillna(0.0),
        },
    ).drop(columns="bedarfsgemeinschaften")


def stack_populations(frame: pd.DataFrame) -> pd.DataFrame:
    """Repeat the rows once per population, labelled by which they belong to.

    Args:
        frame: Any frame carrying `wohngeld_rule_suspected`.

    Returns:
        The rows of `frame` labelled `all_gemeinden`, followed by those without
        a suspected fallback rule labelled `excluding_suspected_fallback`.

    """
    _fail_if_columns_absent(frame, ("wohngeld_rule_suspected",))
    retained = frame.loc[~frame["wohngeld_rule_suspected"].astype(bool)]
    return pd.concat(
        [
            frame.assign(population=AnalysisPopulation.ALL_GEMEINDEN.value),
            retained.assign(
                population=AnalysisPopulation.EXCLUDING_SUSPECTED_FALLBACK.value,
            ),
        ],
        ignore_index=True,
    )


def summarise_cap_ratio(frame: pd.DataFrame) -> pd.DataFrame:
    """Describe the ratio of local cap to fallback by household size.

    Args:
        frame: The output of {func}`attach_weights`, already stacked by
            {func}`stack_populations`.

    Returns:
        A long table with one row per measure, population, weighting scheme,
        household size and statistic.

    """
    _fail_if_columns_absent(frame, ("population", "household_size", "cap_ratio"))
    rows: list[dict[str, object]] = []
    for scheme in WeightingScheme:
        grouped = frame.groupby(["population", "household_size"], dropna=False)
        for key, part in grouped:
            population, household_size = cast("tuple[str, int]", key)
            values = part["cap_ratio"]
            weight = part[scheme.value]
            rows.extend(
                {
                    "measure": "cap_ratio",
                    "population": population,
                    "weighting_scheme": scheme.value,
                    "household_size": household_size,
                    "statistic": statistic,
                    "value": value,
                }
                for statistic, value in _cap_ratio_statistics(values, weight).items()
            )
    return pd.DataFrame(rows)


def summarise_cap_ratio_spread(spread: pd.DataFrame) -> pd.DataFrame:
    """Describe the spread of the ratio across household sizes.

    Args:
        spread: The output of {func}`cap_ratio_spread_across_household_sizes`,
            already stacked by {func}`stack_populations`.

    Returns:
        A long table shaped like {func}`summarise_cap_ratio`, with the
        household size left missing because the measure spans sizes one to
        four.

    """
    _fail_if_columns_absent(spread, ("population", "cap_ratio_spread"))
    rows: list[dict[str, object]] = []
    for population, part in spread.groupby("population"):
        values = part["cap_ratio_spread"]
        weight = pd.Series(1.0, index=part.index)
        statistics = {
            "n": float(values.notna().sum()),
            "median": weighted_quantile(values, weight, 0.5),
            "p10": weighted_quantile(values, weight, 0.10),
            "p90": weighted_quantile(values, weight, 0.90),
            "share_above_material_threshold": weighted_share(
                values > MATERIAL_SPREAD_THRESHOLD,
                weight,
            ),
        }
        rows.extend(
            {
                "measure": "cap_ratio_spread_across_household_sizes",
                "population": population,
                "weighting_scheme": WeightingScheme.GEMEINDE_UNWEIGHTED.value,
                "household_size": pd.NA,
                "statistic": statistic,
                "value": value,
            }
            for statistic, value in statistics.items()
        )
    return pd.DataFrame(rows)


def plot_cap_ratio_distribution(frame: pd.DataFrame) -> go.Figure:
    """Draw the ratio of local cap to fallback by household size.

    Args:
        frame: The output of {func}`stack_populations` applied to
            {func}`build_cap_comparison`.

    Returns:
        A box plot per household size and population, with the fallback drawn
        as a reference line at one.

    """
    plotted = frame.dropna(subset=["cap_ratio"]).assign(
        population_label=lambda df: df["population"].map(
            {member.value: POPULATION_LABELS[member] for member in AnalysisPopulation},
        ),
    )
    figure = px.box(
        plotted,
        x="household_size",
        y="cap_ratio",
        color="population_label",
        color_discrete_sequence=[NEUTRAL_COLOUR, ACCENT_COLOUR],
        points=False,
        labels={
            "household_size": "Household size",
            "cap_ratio": "Local cap ÷ statutory fallback",
            "population_label": "",
        },
    )
    figure.add_hline(
        y=1.0,
        line_dash="dot",
        line_color=NEUTRAL_COLOUR,
        annotation_text="statutory fallback",
        annotation_position="top left",
    )
    figure.update_layout(
        title="Local KdU caps depart from the statutory fallback in both directions",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        boxgap=0.4,
    )
    figure.update_yaxes(tickformat=".2f")
    return figure


def plot_cap_ratio_spread_distribution(spread: pd.DataFrame) -> go.Figure:
    """Draw how far the ratio moves across household sizes within a Gemeinde.

    Args:
        spread: The output of {func}`stack_populations` applied to
            {func}`cap_ratio_spread_across_household_sizes`.

    Returns:
        An empirical cumulative distribution per population, with the material
        threshold marked.

    """
    plotted = spread.dropna(subset=["cap_ratio_spread"]).assign(
        population_label=lambda df: df["population"].map(
            {member.value: POPULATION_LABELS[member] for member in AnalysisPopulation},
        ),
    )
    figure = px.ecdf(
        plotted,
        x="cap_ratio_spread",
        color="population_label",
        color_discrete_sequence=[NEUTRAL_COLOUR, ACCENT_COLOUR],
        labels={
            "cap_ratio_spread": (
                "Largest minus smallest cap ratio over household sizes 1 to 4"
            ),
            "population_label": "",
        },
    )
    figure.add_vline(
        x=MATERIAL_SPREAD_THRESHOLD,
        line_dash="dot",
        line_color=NEUTRAL_COLOUR,
        annotation_text=f"{MATERIAL_SPREAD_THRESHOLD:.2f} ratio points",
        annotation_position="top right",
    )
    figure.update_layout(
        title=(
            "Within one Gemeinde the departure from the fallback moves with "
            "household size"
        ),
        yaxis_title="Share of Gemeinden at or below",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
    )
    figure.update_xaxes(range=[0, 0.3])
    return figure


def _cap_ratio_statistics(
    values: pd.Series,
    weight: pd.Series,
) -> dict[str, float]:
    """Return the statistics reported for one household size and population."""
    return {
        "n": float(values.notna().sum()),
        "mean": weighted_mean(values, weight),
        "median": weighted_quantile(values, weight, 0.5),
        "p10": weighted_quantile(values, weight, 0.10),
        "p90": weighted_quantile(values, weight, 0.90),
        "standard_deviation": weighted_standard_deviation(values, weight),
        "share_below_fallback": weighted_share(values < 1.0, weight),
    }


def _natural_log(values: pd.Series) -> pd.Series:
    """Return the natural logarithm, missing where the argument is not positive."""
    numeric = pd.to_numeric(values, errors="coerce").astype("Float64")
    positive = numeric.where(numeric > 0)
    return pd.Series(
        np.log(positive.to_numpy(dtype="float64")),
        index=values.index,
        dtype="Float64",
    )


def _fail_if_columns_absent(frame: pd.DataFrame, required: tuple[str, ...]) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        msg = f"frame is missing required column(s) {missing}"
        raise ValueError(msg)
