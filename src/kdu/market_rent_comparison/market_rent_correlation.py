"""Whether each cap tracks the local rent level of the Gemeinde it applies to.

The Mietenstufe of § 12 WoGG exists to place a Gemeinde on a national rent
gradient, and the statutory fallback inherits that placement. The local KdU
cap is set by the Kreis without reference to the Mietenstufe. This module
measures how closely each of the two follows the mean Nettokaltmiete per
square metre that the 2022 Zensus records for the same Gemeinde.

The comparison is deliberately asymmetric, and the asymmetry is the result:

- **Across the whole country** the two caps are close, and the statutory
  fallback follows market rents marginally more closely than the local cap
  does. The Mietenstufe performs the task it was designed for.
- **Within a single Mietenstufe** the fallback cannot vary at all at a given
  household size: it is a step function of the Mietenstufe, so its
  correlation with market rents there is zero by construction. The local cap
  is unconstrained in that space and still follows the local rent level.

The second row is therefore not a failing of the fallback measured against
something it could have done. It states that the local caps carry variation
within a Mietenstufe which the fallback cannot carry at all, and that this
variation corresponds to something measured in the housing stock rather than
to administrative noise.

Every function here is a pure function of the frames handed to it; the pytask
wrapper in {mod}`kdu.market_rent_comparison.task_market_rent_correlation`
owns the I/O.
"""

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from kdu.joins import merge_without_duplicating

pio.templates.default = "plotly_dark"

# Grey carries the statutory fallback, the accent colour the local cap.
FALLBACK_COLOUR = "#8c8c8c"
LOCAL_CAP_COLOUR = "#4c9be8"


class CapKind(StrEnum):
    """The two housing-cost ceilings the correlation is computed for."""

    LOCAL = "local_kdu_cap"
    """The maximum rent the responsible Kreis recognises."""
    FALLBACK = "wohngeld_fallback_cap"
    """Höchstbetrag and Klimakomponente, raised by the Sicherheitszuschlag."""

    @property
    def column(self) -> str:
        """Name of the column holding this cap in the analysis frame."""
        return "kdu_cap" if self is CapKind.LOCAL else "wohngeld_fallback_cap"

    @property
    def label(self) -> str:
        """English label for figures and tables."""
        return "Local KdU cap" if self is CapKind.LOCAL else "Statutory fallback"


class Comparison(StrEnum):
    """The two spaces in which the correlation is measured."""

    OVERALL = "overall"
    """All Gemeinden together, so the national rent gradient is included."""
    WITHIN_MIETENSTUFE = "within_mietenstufe"
    """Both series taken as deviations from their own Mietenstufe mean."""

    @property
    def label(self) -> str:
        """English label for figures and tables."""
        return (
            "Across all Gemeinden"
            if self is Comparison.OVERALL
            else "Within a Mietenstufe"
        )


@dataclass(frozen=True)
class CorrelationRow:
    """One correlation between a cap and the local market rent."""

    household_size: int
    """Number of household members the cap is read at."""
    cap: CapKind
    """Which of the two ceilings this row describes."""
    comparison: Comparison
    """Whether the national rent gradient is included or removed."""
    correlation: float
    """Pearson correlation of the two series in logarithms."""
    n_gemeinden: int
    """Gemeinden entering this correlation."""
    mechanically_zero: bool
    """Whether the cap is constant in this space, forcing the correlation to zero.

    True for the statutory fallback within a Mietenstufe: at a fixed household
    size the fallback is a function of the Mietenstufe alone, so removing the
    Mietenstufe mean removes all of its variation.
    """


def build_analysis_frame(
    kdu_caps: pd.DataFrame,
    wohngeld_fallback: pd.DataFrame,
    zensus_rents: pd.DataFrame,
) -> pd.DataFrame:
    """Join the caps, the fallback and the Zensus rents into one frame.

    Args:
        kdu_caps: The local caps, keyed `ags` by `household_size`.
        wohngeld_fallback: The statutory fallback, keyed the same way.
        zensus_rents: The Zensus rents, keyed `ags`.

    Returns:
        One row per Gemeinde and household size for which a local cap, a
        fallback and a positive market rent are all observed.

    """
    caps = kdu_caps.loc[:, ["ags", "household_size", "kdu_cap", "max_area_sqm"]]
    fallback = wohngeld_fallback.loc[
        :,
        [
            "ags",
            "household_size",
            "mietenstufe",
            "wohngeld_fallback_cap",
        ],
    ]
    rents = zensus_rents.loc[:, ["ags", "nettokaltmiete_eur_per_sqm_mean"]]

    frame = merge_without_duplicating(
        caps,
        fallback,
        on=["ags", "household_size"],
    )
    frame = merge_without_duplicating(frame, rents, on=["ags"])
    frame = frame.astype(
        {
            "household_size": "int64",
            "kdu_cap": "float64",
            "wohngeld_fallback_cap": "float64",
            "nettokaltmiete_eur_per_sqm_mean": "float64",
            "mietenstufe": "Int64",
        },
    )
    complete = frame.dropna(
        subset=[
            "kdu_cap",
            "wohngeld_fallback_cap",
            "nettokaltmiete_eur_per_sqm_mean",
            "mietenstufe",
        ],
    )
    return complete.loc[complete["nettokaltmiete_eur_per_sqm_mean"] > 0].reset_index(
        drop=True,
    )


def correlation_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Return every cap-by-comparison correlation, for every household size.

    Args:
        frame: The output of {func}`build_analysis_frame`.

    Returns:
        One row per household size, cap and comparison, with the correlation,
        the number of Gemeinden, and whether the correlation is zero by
        construction.

    """
    household_sizes = sorted(int(size) for size in frame["household_size"].unique())
    rows = [
        _correlation_row(
            frame.loc[frame["household_size"] == household_size],
            household_size,
            cap,
            comparison,
        )
        for household_size in household_sizes
        for cap in CapKind
        for comparison in Comparison
    ]
    return pd.DataFrame([vars(row) for row in rows])


def market_rent_correlation_figure(table: pd.DataFrame) -> go.Figure:
    """Plot the four correlations at household size one as grouped bars.

    Args:
        table: The output of {func}`correlation_table`.

    Returns:
        A figure contrasting the two caps in both comparison spaces, with the
        fallback's within-Mietenstufe bar marked as zero by construction.

    """
    single = table.query("household_size == 1")
    figure = go.Figure()
    for cap in CapKind:
        rows = single.loc[single["cap"] == cap].sort_values("comparison")
        figure.add_bar(
            x=[Comparison(value).label for value in rows["comparison"]],
            y=rows["correlation"],
            name=cap.label,
            marker_color=(
                LOCAL_CAP_COLOUR if cap is CapKind.LOCAL else FALLBACK_COLOUR
            ),
            text=[f"{value:.2f}" for value in rows["correlation"]],
            textposition="outside",
        )
    figure.add_annotation(
        x=Comparison.WITHIN_MIETENSTUFE.label,
        y=0.05,
        text=(
            "The fallback is a step function of the Mietenstufe,<br>"
            "so it cannot vary in this space at all."
        ),
        showarrow=False,
        align="left",
        font={"size": 11, "color": FALLBACK_COLOUR},
        yanchor="bottom",
    )
    figure.update_layout(
        title=(
            "Correlation with the mean Nettokaltmiete per square metre "
            "(Zensus 2022, single-person household)"
        ),
        yaxis_title="Correlation in logarithms",
        barmode="group",
        bargap=0.35,
        showlegend=True,
        legend={"orientation": "h", "y": -0.15},
    )
    figure.update_yaxes(range=[0, 0.8], showgrid=True, gridcolor="#333333")
    figure.update_xaxes(showgrid=False, title=None)
    return figure


def _correlation_row(
    group: pd.DataFrame,
    household_size: int,
    cap: CapKind,
    comparison: Comparison,
) -> CorrelationRow:
    """Compute one correlation between a cap and the local market rent."""
    log_cap = np.log(group[cap.column].to_numpy(dtype=float))
    log_rent = np.log(group["nettokaltmiete_eur_per_sqm_mean"].to_numpy(dtype=float))
    if comparison is Comparison.WITHIN_MIETENSTUFE:
        mietenstufe = group["mietenstufe"].to_numpy()
        log_cap = _deviation_from_group_mean(log_cap, mietenstufe)
        log_rent = _deviation_from_group_mean(log_rent, mietenstufe)
    return CorrelationRow(
        household_size=int(household_size),
        cap=cap,
        comparison=comparison,
        correlation=_pearson_correlation(log_cap, log_rent),
        n_gemeinden=len(group),
        mechanically_zero=(
            cap is CapKind.FALLBACK and comparison is Comparison.WITHIN_MIETENSTUFE
        ),
    )


def _deviation_from_group_mean(
    values: np.ndarray,
    groups: np.ndarray,
) -> np.ndarray:
    """Return `values` with the mean of their own group subtracted."""
    means = pd.Series(values).groupby(groups).transform("mean").to_numpy()
    return values - means


def _pearson_correlation(first: np.ndarray, second: np.ndarray) -> float:
    """Return the Pearson correlation, or zero where one series is constant."""
    if np.std(first) == 0 or np.std(second) == 0:
        return 0.0
    return float(np.corrcoef(first, second)[0, 1])
