"""Where a local KdU cap sits relative to the mean rent of its own Gemeinde.

The share of the rented stock a cap prices above itself answers what a cap
means for a household searching for a dwelling. This module asks the narrower
question behind it: how the cap compares with the rent per square metre the
Gemeinde's sitting tenants actually pay, so that the local cap is read against
a local rent rather than against the statutory construction. The quantity is
one ratio per Gemeinde,

```
cap_over_bestandsmiete = threshold_local_kdu_cap_eur_per_sqm
                         / nettokaltmiete_eur_per_sqm_mean
```

with both terms in euro per square metre and month, and both net of kalte
Betriebskosten. A value of one means the cap admits exactly the mean rent of
the Gemeinde.

Four properties of the measurement bound what it can be asked to support.

- **The ratio is not a share of dwellings within reach.** The denominator is a
  mean over a distribution whose shape it does not carry, and per the rule
  stated in {mod}`kdu.data_management.clean_zensus_rents` no quantity derived
  from that mean may be named after, or read as, the fraction of dwellings a
  household could rent. That question is answered by
  {mod}`kdu.market_rent_comparison.share_of_stock_above_cap` and only there.
- **The two sides carry different dates.** The Zensus recorded Bestandsmieten
  on 2022-05-15, while the caps are those in force in 2025 and 2026. Rents rose
  in between, so the headroom this ratio shows is wider than the headroom a
  household faces today, and wider still against an Angebotsmiete, which
  exceeds the Bestandsmiete of the same dwelling.
- **The numerator is a converted figure, not a published one.** A cap is
  published as a monthly Bruttokaltmiete for an admissible Wohnfläche; turning
  it into a rent per square metre divides by that Wohnfläche and subtracts the
  kalte Betriebskosten the Bundesagentur reports for the Kreis. Both steps are
  described in {mod}`kdu.market_rent_comparison.share_of_stock_above_cap`, and
  the Betriebskosten are constant within a Kreis because that is the finest
  resolution published.
- **A Gemeinde whose mean rent the Zensus suppresses is excluded.** Such a
  Gemeinde carries a mean of exactly zero rather than a missing value, so it is
  removed by an explicit positivity requirement; see
  {func}`build_cap_over_bestandsmiete`.

Every function here is a pure function of the frames handed to it; the pytask
wrapper in {mod}`kdu.market_rent_comparison.task_cap_over_bestandsmiete` owns
the I/O.
"""

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from kdu.joins import merge_without_duplicating

pio.templates.default = "plotly_white"

# The column this module produces and every other function here reads.
RATIO_COLUMN = "cap_over_bestandsmiete"

# The ratio at which the cap admits exactly the mean Bestandsmiete.
REFERENCE_RATIO = 1.0

# Axis titles. Both stay German where the German word carries a caveat no
# English rendering keeps: "Bestandsmiete" says these are the rents of sitting
# tenants rather than rents asked of a mover, and "Zensus 2022" says when they
# were recorded.
X_AXIS_TITLE = "Angemessene KdU ÷ mittlere Bestandsmiete (Zensus 2022)"
Y_AXIS_TITLE = "# Gemeinden (unweighted)"

# Font sizes of a figure, chosen so that the smallest text stays readable when
# the PNG is projected at 1600 by 900 logical pixels.
PRESENTATION_BASE_FONT_SIZE = 20
AXIS_TITLE_FONT_SIZE = 24

# The accent colour carries the bars, the neutral one the reference rule.
LOCAL_CAP_COLOUR = "#1f6fb2"
REFERENCE_LINE_COLOUR = "#5f6368"

# Gridlines separate the bars without competing with them.
GRID_COLOUR = "#d9d9d9"

# Width of a histogram bin, in units of the ratio. Plotly treats `nbins` as a
# hint and rounds to a width of its own over the whole data span, which here
# yields bars wide enough to hide the mass sitting just either side of one, so
# the bin edges are stated outright instead.
BIN_WIDTH = 0.05


def build_cap_over_bestandsmiete(
    gemeinde_shares: pd.DataFrame,
    zensus_rents: pd.DataFrame,
) -> pd.DataFrame:
    """Return the local cap over its own Gemeinde's mean Bestandsmiete.

    Two exclusions are made, and they are not the same exclusion:

    - A Gemeinde with no cap in euro per square metre — because its
      Richtlinie states no admissible Wohnfläche — has no numerator.
    - A Gemeinde whose mean Nettokaltmiete is zero has no usable denominator.
      The Zensus suppresses the mean of a Gemeinde with a very small rented
      stock by publishing zero rather than a missing value, so dropping missing
      values leaves these rows in place and the division returns an infinity.
      They are removed by requiring a strictly positive mean.

    Args:
        gemeinde_shares: The per-Gemeinde output of
            {func}`kdu.market_rent_comparison.share_of_stock_above_cap.build_gemeinde_shares`,
            supplying `threshold_local_kdu_cap_eur_per_sqm`.
        zensus_rents: The Zensus rents keyed `ags`, supplying
            `nettokaltmiete_eur_per_sqm_mean`.

    Returns:
        One row per `ags` and `household_size` that has both terms, carrying
        the two terms and their ratio in `RATIO_COLUMN`.

    """
    caps = gemeinde_shares.loc[
        :,
        ["ags", "household_size", "threshold_local_kdu_cap_eur_per_sqm"],
    ]
    rents = zensus_rents.loc[:, ["ags", "nettokaltmiete_eur_per_sqm_mean"]]
    frame = merge_without_duplicating(caps, rents, on=["ags"])

    frame = frame.dropna(
        subset=[
            "threshold_local_kdu_cap_eur_per_sqm",
            "nettokaltmiete_eur_per_sqm_mean",
        ],
    )
    frame = frame.loc[frame["nettokaltmiete_eur_per_sqm_mean"] > 0]

    result = frame.reset_index(drop=True)
    result[RATIO_COLUMN] = result["threshold_local_kdu_cap_eur_per_sqm"].astype(
        float
    ) / result["nettokaltmiete_eur_per_sqm_mean"].astype(float)
    _fail_if_ratio_is_not_finite(result[RATIO_COLUMN])
    return result


def summarise_cap_over_bestandsmiete(frame: pd.DataFrame) -> pd.DataFrame:
    """Summarise the ratio across Gemeinden at every household size.

    Every Gemeinde counts once, whatever its population or caseload, because
    the question is what the administrative landscape looks like.

    Args:
        frame: The output of {func}`build_cap_over_bestandsmiete`.

    Returns:
        One row per household size, carrying the number of Gemeinden, the
        tenth percentile, median and ninetieth percentile of the ratio, and the
        share of Gemeinden whose cap falls below their own mean Bestandsmiete.

    """
    household_sizes = sorted(int(size) for size in frame["household_size"].unique())
    rows = [
        _summary_row(
            frame.loc[frame["household_size"] == household_size, RATIO_COLUMN],
            household_size,
        )
        for household_size in household_sizes
    ]
    return pd.DataFrame(rows)


def cap_over_bestandsmiete_figure(frame: pd.DataFrame) -> go.Figure:
    """Plot the distribution of the ratio at household size one.

    The figure carries no title, because whatever embeds it supplies the
    heading, and its fonts are sized for projection at 1600 by 900 pixels. The
    bins span every observed ratio, so the picture drops no Gemeinde.

    Args:
        frame: The output of {func}`build_cap_over_bestandsmiete`.

    Returns:
        A histogram of the ratio over Gemeinden, one Gemeinde one weight, with
        a dashed rule at the ratio of one.

    """
    ratio = frame.loc[frame["household_size"] == 1, RATIO_COLUMN]
    start, end = _bin_edges(ratio)

    figure = go.Figure()
    figure.add_histogram(
        x=ratio,
        marker_color=LOCAL_CAP_COLOUR,
        xbins={"start": start, "end": end, "size": BIN_WIDTH},
        showlegend=False,
    )
    figure.add_vline(
        x=REFERENCE_RATIO,
        line_width=3,
        line_dash="dash",
        line_color=REFERENCE_LINE_COLOUR,
    )
    figure.update_layout(
        font={"size": PRESENTATION_BASE_FONT_SIZE},
        xaxis_title=X_AXIS_TITLE,
        yaxis_title=Y_AXIS_TITLE,
        bargap=0.05,
    )
    figure.update_xaxes(showgrid=False, title_font={"size": AXIS_TITLE_FONT_SIZE})
    figure.update_yaxes(
        showgrid=True,
        gridcolor=GRID_COLOUR,
        title_font={"size": AXIS_TITLE_FONT_SIZE},
    )
    return figure


def _bin_edges(ratio: pd.Series) -> tuple[float, float]:
    """Return bin edges of width `BIN_WIDTH` enclosing every value of `ratio`."""
    lowest = float(ratio.min())
    highest = float(ratio.max())
    return (
        math.floor(lowest / BIN_WIDTH) * BIN_WIDTH,
        math.ceil(highest / BIN_WIDTH) * BIN_WIDTH,
    )


def _summary_row(ratio: pd.Series, household_size: int) -> dict[str, object]:
    """Return the spread of the ratio across Gemeinden at one household size."""
    return {
        "household_size": household_size,
        "n_gemeinden": int(ratio.notna().sum()),
        "percentile_10": float(ratio.quantile(0.10)),
        "median": float(ratio.median()),
        "percentile_90": float(ratio.quantile(0.90)),
        "share_below_one": float((ratio < REFERENCE_RATIO).mean()),
    }


def _fail_if_ratio_is_not_finite(ratio: pd.Series) -> None:
    """Raise if any ratio survived the exclusions as an infinity or a missing value."""
    offending = ratio.loc[~np.isfinite(ratio)]
    if not offending.empty:
        msg = (
            f"{len(offending)} Gemeinden carry a non-finite ratio of cap to mean "
            f"Bestandsmiete, first value {offending.iloc[0]}; a mean rent of zero "
            f"must be excluded before the division"
        )
        raise ValueError(msg)
