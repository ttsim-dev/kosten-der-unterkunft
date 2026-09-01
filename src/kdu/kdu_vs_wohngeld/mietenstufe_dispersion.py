"""How much local KdU variation the statutory Mietenstufe leaves unaccounted for.

Under § 12 WoGG the Mietenstufe is assigned kreisweise for Gemeinden below
10,000 inhabitants and individually only for larger ones, so the statutory
classification is coarse by construction. A tax-transfer model without the
local caps reaches for that classification as its regional housing parameter.
This module states what the classification does and does not carry:

- the dispersion of the local cap that survives inside a single Mietenstufe,
  against the one Angemessenheitsgrenze ohne schlüssiges Konzept that class
  carries;
- the share of the variance in the log local cap accounted for by the
  Mietenstufe, by the Bundesland, by the two together, and by the Kreis.

The classifications distinguish different numbers of groups, and a
between-group share rises with the number of groups whatever the grouping
carries. Each share is therefore reported twice: as the raw between-group
share, and adjusted for the degrees of freedom the classification spends.

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

from kdu.weighting import weighted_quantile, weighted_standard_deviation

pio.templates.default = "plotly_white"

# The household size the reported dispersion and variance shares are read at.
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

NEUTRAL_COLOUR = "#5f6368"
ACCENT_COLOUR = "#c25e12"

# The figure is projected in a lecture room, where the default sizes are
# unreadable from the back rows. The rendered image is 1600 by 900 pixels.
BASE_FONT_SIZE = 20
AXIS_TITLE_FONT_SIZE = 24

# The overlaid Grenze marker, large enough to read against a box behind it.
FALLBACK_MARKER_SIZE = 14

# The label the overlaid Grenze ohne schlüssiges Konzept carries in the legend.
# It stays German because it is the statutory construction it names.
FALLBACK_LEGEND_LABEL = "Angemessenheitsgrenze ohne schlüssiges Konzept"

# The Grenze is a single euro amount per Mietenstufe at a given household size,
# so a class holding two of them means the frame was built at more than one
# size or from more than one Rechtsstand. Coincidence is read to half a cent,
# the resolution the Wohngeld table is published at, because the Grenze is a
# floating-point product and carries a residue far below that.
FALLBACK_IDENTITY_TOLERANCE_EUR = 0.005


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
        it distinguishes, the share of the variance in the log local cap that
        lies between those groups, and that share adjusted for the degrees of
        freedom the classification spends.

    """
    observed = _observations_at(frame, household_size)
    log_cap = np.log(observed["kdu_cap"].to_numpy(dtype="float64"))
    rows = []
    for name, columns in CLASSIFICATIONS.items():
        n_groups = int(observed.groupby(list(columns), observed=True).ngroups)
        share = variance_share_between_groups(
            log_cap,
            [observed[column].to_numpy() for column in columns],
        )
        rows.append(
            {
                "household_size": household_size,
                "classification": name,
                "n_groups": n_groups,
                "n_gemeinden": len(observed),
                "variance_share": share,
                "variance_share_adjusted": degrees_of_freedom_adjusted_share(
                    share,
                    n_observations=len(observed),
                    n_groups=n_groups,
                ),
            },
        )
    return pd.DataFrame(rows)


def degrees_of_freedom_adjusted_share(
    share: float,
    n_observations: int,
    n_groups: int,
) -> float:
    r"""Charge a between-group variance share for the groups it distinguishes.

    A between-group share rises with the number of groups whether or not the
    grouping carries anything, because each additional group takes one more
    degree of freedom out of the within-group sum of squares. The adjustment
    compares the within-group and total sums of squares per remaining degree
    of freedom rather than in level:

    $$1 - (1 - \text{share}) \frac{n - 1}{n - k}$$

    Args:
        share: The between-group share of the total sum of squares, or `nan`
            where the decomposed quantity does not vary.
        n_observations: The number of observations entering the decomposition.
        n_groups: The number of groups the classification distinguishes.

    Returns:
        The adjusted share, never above `share`, or `nan` if `share` is `nan`.

    """
    _fail_if_groups_exhaust_the_observations(n_observations, n_groups)
    return float(
        1.0 - (1.0 - share) * (n_observations - 1) / (n_observations - n_groups),
    )


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
    household_size: int = REFERENCE_HOUSEHOLD_SIZE,
) -> go.Figure:
    """Draw the local caps that share one Mietenstufe, one box per Mietenstufe.

    Each box carries the one Angemessenheitsgrenze ohne schlüssiges Konzept its
    class is measured against, drawn as a single marker. The Grenze takes
    exactly one value per Mietenstufe at a given household size, so the marker
    is that value rather than a summary of several.

    Args:
        frame: The output of {func}`kdu.kdu_vs_wohngeld.cap_comparison.
            build_cap_comparison`.
        household_size: The size at which the caps and the Grenze are read.

    Returns:
        A one-panel figure: the distribution of the local cap inside each
        statutory class, with the number of Gemeinden on each tick label and
        the Grenze of that class marked in the box.

    Raises:
        ValueError: If a Mietenstufe carries more than one Grenze.

    """
    _fail_if_fallback_absent(frame)
    observed = _observations_at(frame, household_size)
    figure = go.Figure()
    tick_labels: list[str] = []
    fallbacks: list[float] = []
    for mietenstufe, part in observed.groupby("mietenstufe", observed=True):
        label = _tick_label(cast("int", mietenstufe), len(part))
        tick_labels.append(label)
        fallbacks.append(_single_fallback(part, cast("int", mietenstufe)))
        figure.add_trace(
            go.Box(
                y=part["kdu_cap"].to_numpy(dtype="float64"),
                name=label,
                fillcolor=NEUTRAL_COLOUR,
                line_color=ACCENT_COLOUR,
                opacity=0.6,
                boxpoints=False,
                showlegend=False,
            ),
        )
    figure.add_trace(
        go.Scatter(
            x=tick_labels,
            y=fallbacks,
            mode="markers",
            name=FALLBACK_LEGEND_LABEL,
            marker={
                "color": NEUTRAL_COLOUR,
                "symbol": "diamond",
                "size": FALLBACK_MARKER_SIZE,
            },
        ),
    )
    figure.update_layout(
        font_size=BASE_FONT_SIZE,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.0,
            "xanchor": "left",
            "x": 0.0,
            "font_size": BASE_FONT_SIZE,
        },
    )
    figure.update_xaxes(
        title_text="Mietstufe",
        tickfont_size=BASE_FONT_SIZE,
        title_font_size=AXIS_TITLE_FONT_SIZE,
    )
    figure.update_yaxes(
        title_text="KdU cap, Euro per month",
        tickfont_size=BASE_FONT_SIZE,
        title_font_size=AXIS_TITLE_FONT_SIZE,
    )
    return figure


def _fail_if_fallback_absent(frame: pd.DataFrame) -> None:
    """Reject a frame without the Grenze the boxes are measured against."""
    if "wohngeld_fallback_cap" not in frame.columns:
        msg = "frame is missing required column 'wohngeld_fallback_cap'"
        raise ValueError(msg)


def _single_fallback(part: pd.DataFrame, mietenstufe: int) -> float:
    """Return the one Grenze ohne schlüssiges Konzept the Mietenstufe carries."""
    values = part["wohngeld_fallback_cap"].to_numpy(dtype="float64")
    if not bool(
        np.isclose(
            values, values[0], rtol=0.0, atol=FALLBACK_IDENTITY_TOLERANCE_EUR
        ).all(),
    ):
        msg = (
            f"Mietenstufe {mietenstufe} carries "
            f"{len(np.unique(values))} distinct Angemessenheitsgrenzen ohne "
            f"schlüssiges Konzept; it takes exactly one value per Mietenstufe "
            f"at a given household size"
        )
        raise ValueError(msg)
    return float(values[0])


def _tick_label(mietenstufe: int, n_gemeinden: int) -> str:
    """Label a box with its Mietenstufe and the Gemeinden it covers."""
    return f"{mietenstufe}<br>n = {n_gemeinden:,}"


def _fail_if_groups_exhaust_the_observations(
    n_observations: int,
    n_groups: int,
) -> None:
    """Reject a classification that leaves no residual degrees of freedom."""
    if n_groups >= n_observations:
        msg = (
            f"a classification of {n_observations} observations into "
            f"{n_groups} groups leaves no degrees of freedom to adjust for"
        )
        raise ValueError(msg)


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
