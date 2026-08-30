"""How much local KdU variation the statutory Mietenstufe leaves unaccounted for.

Under § 12 WoGG the Mietenstufe is assigned kreisweise for Gemeinden below
10,000 inhabitants and individually only for larger ones, so the statutory
classification is coarse by construction. A tax-transfer model without the
local caps reaches for that classification as its regional housing parameter.
This module states what the classification does and does not carry:

- the dispersion of the local cap that survives inside a single Mietenstufe;
- the share of the variance in the log local cap accounted for by the
  Mietenstufe, by the Bundesland, by the two together, and by the Kreis.

The exercise is descriptive. The variance shares are the between-group share
of the total sum of squares under a classification, not an estimate of a
parameter, so no standard error, p-value or significance statement appears
here and nothing is described as an effect.

The functions here are pure: they take frames and return frames or figures.
{mod}`kdu.kdu_vs_wohngeld.task_mietenstufe_dispersion` owns the reading and
writing.
"""

from collections.abc import Sequence
from typing import cast

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from kdu.weighting import weighted_quantile, weighted_standard_deviation

pio.templates.default = "plotly_dark"

# The household size the headline dispersion and variance shares are read at.
# Single-person households are the size every Träger publishes.
REFERENCE_HOUSEHOLD_SIZE = 1

# The classifications whose accounted-for variance shares are compared. Each
# entry names the columns a Gemeinde is grouped by.
CLASSIFICATIONS: dict[str, tuple[str, ...]] = {
    "mietenstufe": ("mietenstufe",),
    "bundesland": ("state_code",),
    "mietenstufe_and_bundesland": ("mietenstufe", "state_code"),
    "kreis": ("district_ags",),
}

CLASSIFICATION_LABELS: dict[str, str] = {
    "mietenstufe": "Mietenstufe",
    "bundesland": "Bundesland",
    "mietenstufe_and_bundesland": "Mietenstufe × Bundesland",
    "kreis": "Kreis",
}

NEUTRAL_COLOUR = "#9aa0a6"
ACCENT_COLOUR = "#e8833a"


def dispersion_within_mietenstufe(
    frame: pd.DataFrame,
    household_size: int = REFERENCE_HOUSEHOLD_SIZE,
) -> pd.DataFrame:
    """Describe the local caps that share one Mietenstufe.

    Args:
        frame: The output of {func}`kdu.kdu_vs_wohngeld.cap_comparison.
            build_cap_comparison`.
        household_size: The size at which the caps are read.

    Returns:
        One row per Mietenstufe, with the number of Gemeinden, the median cap,
        the standard deviation, and the interdecile range — the width of the
        band the middle 80 % of Gemeinden in that statutory class occupy.

    """
    observed = _observations_at(frame, household_size)
    rows = [
        {
            "household_size": household_size,
            "mietenstufe": cast("int", mietenstufe),
            "n_gemeinden": int(part["kdu_cap"].notna().sum()),
            "median_kdu_cap": _quantile(part["kdu_cap"], 0.5),
            "standard_deviation_kdu_cap": weighted_standard_deviation(
                part["kdu_cap"],
                pd.Series(1.0, index=part.index),
            ),
            "interdecile_range_kdu_cap": (
                _quantile(part["kdu_cap"], 0.9) - _quantile(part["kdu_cap"], 0.1)
            ),
        }
        for mietenstufe, part in observed.groupby("mietenstufe", observed=True)
    ]
    return pd.DataFrame(rows).sort_values("mietenstufe", ignore_index=True)


def variance_shares(
    frame: pd.DataFrame,
    household_size: int = REFERENCE_HOUSEHOLD_SIZE,
) -> pd.DataFrame:
    """Report how much of the variation in the local cap each classification carries.

    Args:
        frame: The output of {func}`kdu.kdu_vs_wohngeld.cap_comparison.
            build_cap_comparison`.
        household_size: The size at which the caps are read.

    Returns:
        One row per entry of {data}`CLASSIFICATIONS`, with the number of groups
        it distinguishes and the share of the variance in the log local cap
        that lies between those groups.

    """
    observed = _observations_at(frame, household_size)
    log_cap = np.log(observed["kdu_cap"].to_numpy(dtype="float64"))
    rows = [
        {
            "household_size": household_size,
            "classification": name,
            "n_groups": int(observed.groupby(list(columns), observed=True).ngroups),
            "n_gemeinden": len(observed),
            "variance_share": variance_share_between_groups(
                log_cap,
                [observed[column].to_numpy() for column in columns],
            ),
        }
        for name, columns in CLASSIFICATIONS.items()
    ]
    return pd.DataFrame(rows)


def variance_share_between_groups(
    values: np.ndarray,
    grouping: Sequence[np.ndarray],
) -> float:
    """Return the share of the variance in `values` that lies between groups.

    This is one minus the ratio of the within-group sum of squares to the total
    sum of squares: the fraction of the variation a reader recovers by knowing
    only which group an observation falls in.

    Args:
        values: The quantity whose variation is decomposed.
        grouping: One array per column that jointly defines the groups.

    Returns:
        A number in `[0, 1]`, or `nan` if `values` does not vary.

    """
    total = ((values - values.mean()) ** 2).sum()
    if total == 0:
        return float("nan")
    group_mean = pd.Series(values).groupby(list(grouping)).transform("mean").to_numpy()
    within = ((values - group_mean) ** 2).sum()
    return float(1.0 - within / total)


def plot_mietenstufe_dispersion(
    frame: pd.DataFrame,
    shares: pd.DataFrame,
    household_size: int = REFERENCE_HOUSEHOLD_SIZE,
) -> go.Figure:
    """Draw the dispersion inside each Mietenstufe beside the variance shares.

    Args:
        frame: The output of {func}`kdu.kdu_vs_wohngeld.cap_comparison.
            build_cap_comparison`.
        shares: The output of {func}`variance_shares`.
        household_size: The size at which the caps are read.

    Returns:
        A two-panel figure: the distribution of the local cap within each
        statutory class on the left, and how much of the variation each
        classification accounts for on the right.

    """
    observed = _observations_at(frame, household_size)
    figure = make_subplots(
        rows=1,
        cols=2,
        column_widths=[0.62, 0.38],
        horizontal_spacing=0.12,
        subplot_titles=(
            "Local caps sharing one Mietenstufe",
            "Share of variation in the local cap accounted for",
        ),
    )
    for mietenstufe, part in observed.groupby("mietenstufe", observed=True):
        figure.add_trace(
            go.Box(
                y=part["kdu_cap"].to_numpy(dtype="float64"),
                name=str(mietenstufe),
                marker_color=NEUTRAL_COLOUR,
                boxpoints=False,
                showlegend=False,
            ),
            row=1,
            col=1,
        )

    ordered = shares.set_index("classification").reindex(CLASSIFICATIONS)
    labels = [CLASSIFICATION_LABELS[name] for name in ordered.index]
    values = ordered["variance_share"].to_numpy(dtype="float64")
    figure.add_trace(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker_color=[
                ACCENT_COLOUR if name == "mietenstufe" else NEUTRAL_COLOUR
                for name in ordered.index
            ],
            text=[f"{value:.2f}" for value in values],
            textposition="outside",
            showlegend=False,
        ),
        row=1,
        col=2,
    )
    figure.update_layout(
        title=(
            "The Mietenstufe accounts for less of the local cap than the "
            "Bundesland does"
        ),
        bargap=0.35,
    )
    figure.update_xaxes(title_text="Mietenstufe", row=1, col=1)
    figure.update_yaxes(title_text="Local cap, € per month", row=1, col=1)
    figure.update_xaxes(title_text="", range=[0, 1.05], row=1, col=2)
    return figure


def _observations_at(frame: pd.DataFrame, household_size: int) -> pd.DataFrame:
    """Return the Gemeinden with a cap and a Mietenstufe at `household_size`."""
    required = (
        "household_size",
        "kdu_cap",
        "mietenstufe",
        "state_code",
        "district_ags",
    )
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        msg = f"frame is missing required column(s) {missing}"
        raise ValueError(msg)
    observed = frame.loc[frame["household_size"] == household_size]
    observed = observed.dropna(subset=["kdu_cap", "mietenstufe"])
    return observed.assign(
        kdu_cap=lambda df: df["kdu_cap"].astype("float64"),
        mietenstufe=lambda df: df["mietenstufe"].astype("int64"),
    )


def _quantile(values: pd.Series, quantile: float) -> float:
    """Return an unweighted quantile through the shared weighted routine."""
    return weighted_quantile(values, pd.Series(1.0, index=values.index), quantile)
