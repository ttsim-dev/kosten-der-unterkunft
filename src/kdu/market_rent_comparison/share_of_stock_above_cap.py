"""How much of a Gemeinde's rented housing stock each cap prices above itself.

A cap on the recognisable Bruttokaltmiete divides the local rental stock in
two: dwellings a claimant may rent while having the rent recognised in full,
and dwellings priced above the ceiling. The share on the far side of that
line is what the cap means for someone looking for somewhere to live, and it
does not depend on the cap binding on anybody's current rent.

The share is computed for the local KdU cap and for the statutory fallback
separately. The quantity that matters is the difference between the two: it
is the error a tax-transfer simulation makes about the housing stock
available to a household when it substitutes the fallback for the local rule.

The 2022 Zensus reports, for each Gemeinde, how many rented dwellings fall
into each Nettokaltmiete band of two euro per square metre. A cap is stated
as a monthly Bruttokaltmiete for an admissible Wohnfläche, so it is converted
to a Nettokaltmiete per square metre before the two can be compared:

```
threshold = kdu_cap / max_area_sqm - kalte_betriebskosten_per_sqm
```

Three properties of the measurement bound what it can be asked to support.

- The Zensus records **Bestandsmieten**, the rents sitting tenants pay. Rents
  asked of a new tenant are higher, so a household actually looking for a
  dwelling faces a tighter market than these shares describe, and every share
  reported here is a lower bound for a mover.
- The conversion from Bruttokaltmiete to Nettokaltmiete uses the kalte
  Betriebskosten the Bundesagentur reports for the **Kreis**, weighted by
  Bedarfsgemeinschaften across household sizes. That is the finest resolution
  published; within a Kreis every Gemeinde receives the same figure. Where a
  Kreis reports none, the Bedarfsgemeinschaft-weighted national mean stands in.
- The count covers the **whole rented stock**, not only dwellings within the
  admissible Wohnfläche for the household size in question. A single person
  may not rent a 120 square metre dwelling at any price, so the share of
  dwellings both priced within the cap and within the admissible Wohnfläche is
  smaller than the reported share below the cap.

Every function here is a pure function of the frames handed to it; the pytask
wrapper in {mod}`kdu.market_rent_comparison.task_share_of_stock_above_cap`
owns the I/O.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from kdu.joins import merge_without_duplicating

pio.templates.default = "plotly_dark"

# Grey carries the statutory fallback, the accent colour the local cap.
FALLBACK_COLOUR = "#8c8c8c"
LOCAL_CAP_COLOUR = "#4c9be8"
DIFFERENCE_COLOUR = "#e8a34c"

# Column carrying the kalte Betriebskosten a Gemeinde is charged, in euro per
# square metre and month.
KALTE_BETRIEBSKOSTEN_COLUMN = "kalte_betriebskosten_per_sqm"

# Upper edge assumed for the open-ended top band of the Zensus distribution.
#
# The Zensus reports dwellings at 20 euro per square metre and above without
# an upper limit. Any finite edge is an assumption; 30 is far enough above the
# highest cap in the data that no threshold falls inside this band, so the
# choice does not affect a single share.
TOP_BAND_UPPER_EDGE_EUR_PER_SQM = 30.0

# Dwelling counts arrive as one row per Gemeinde and one column per rent band.
BAND_COUNT_DIMENSIONS = 2


@dataclass(frozen=True)
class RentBand:
    """One Nettokaltmiete band of the Zensus rented-stock distribution."""

    column: str
    """Column of `zensus_rents` holding the dwelling count for this band."""
    lower_edge: float
    """Lowest rent per square metre counted in the band, in euro."""
    upper_edge: float
    """Rent per square metre at which the band ends, in euro."""


# The eleven Zensus bands, ascending and contiguous.
RENT_BANDS: tuple[RentBand, ...] = (
    RentBand("dwellings_nettokaltmiete_eur_per_sqm_under_4", 0.0, 4.0),
    RentBand("dwellings_nettokaltmiete_eur_per_sqm_4_to_6", 4.0, 6.0),
    RentBand("dwellings_nettokaltmiete_eur_per_sqm_6_to_8", 6.0, 8.0),
    RentBand("dwellings_nettokaltmiete_eur_per_sqm_8_to_10", 8.0, 10.0),
    RentBand("dwellings_nettokaltmiete_eur_per_sqm_10_to_12", 10.0, 12.0),
    RentBand("dwellings_nettokaltmiete_eur_per_sqm_12_to_14", 12.0, 14.0),
    RentBand("dwellings_nettokaltmiete_eur_per_sqm_14_to_16", 14.0, 16.0),
    RentBand("dwellings_nettokaltmiete_eur_per_sqm_16_to_18", 16.0, 18.0),
    RentBand("dwellings_nettokaltmiete_eur_per_sqm_18_to_20", 18.0, 20.0),
    RentBand(
        "dwellings_nettokaltmiete_eur_per_sqm_20_and_more",
        20.0,
        TOP_BAND_UPPER_EDGE_EUR_PER_SQM,
    ),
)


def build_gemeinde_shares(
    kdu_caps: pd.DataFrame,
    wohngeld_fallback: pd.DataFrame,
    zensus_rents: pd.DataFrame,
    gemeinden: pd.DataFrame,
    wohnkostenstatistik: pd.DataFrame,
) -> pd.DataFrame:
    """Return the share of the local rented stock above each cap per Gemeinde.

    Args:
        kdu_caps: The local caps, keyed `ags` by `household_size`.
        wohngeld_fallback: The statutory fallback, keyed the same way.
        zensus_rents: The Zensus rents and band counts, keyed `ags`.
        gemeinden: Gemeinde metadata, keyed `ags`, supplying `district_ags`.
        wohnkostenstatistik: The Bundesagentur record, supplying the kalte
            Betriebskosten charged in each Kreis.

    Returns:
        One row per `ags` and `household_size`, carrying the two thresholds in
        euro per square metre, the share of dwellings priced above each, and
        the absolute difference between the two shares.

    """
    frame = _join_caps_to_rent_bands(kdu_caps, wohngeld_fallback, zensus_rents)
    betriebskosten = _kalte_betriebskosten_per_gemeinde(
        frame["ags"],
        gemeinden,
        wohnkostenstatistik,
    ).to_numpy(dtype=float)
    band_counts = frame.loc[:, [band.column for band in RENT_BANDS]].to_numpy(
        dtype=float,
    )

    result = frame.loc[
        :,
        ["ags", "household_size", "mietenstufe", "wohngeld_rule_suspected"],
    ].copy()
    for name, cap_column in (
        ("local_kdu_cap", "kdu_cap"),
        ("wohngeld_fallback_cap", "wohngeld_fallback_cap"),
    ):
        threshold = nettokaltmiete_threshold(
            frame[cap_column].to_numpy(dtype=float),
            frame["max_area_sqm"].to_numpy(dtype=float),
            betriebskosten,
        )
        result[f"threshold_{name}_eur_per_sqm"] = threshold
        result[f"share_above_{name}"] = share_above_threshold(band_counts, threshold)

    result["share_difference"] = (
        result["share_above_local_kdu_cap"]
        - result["share_above_wohngeld_fallback_cap"]
    )
    result["absolute_share_difference"] = result["share_difference"].abs()
    return result.dropna(
        subset=["share_above_local_kdu_cap", "share_above_wohngeld_fallback_cap"],
    ).reset_index(drop=True)


def nettokaltmiete_threshold(
    cap_eur_per_month: np.ndarray,
    max_area_sqm: np.ndarray,
    kalte_betriebskosten_per_sqm: np.ndarray,
) -> np.ndarray:
    """Convert a monthly Bruttokaltmiete cap to a Nettokaltmiete per square metre.

    Args:
        cap_eur_per_month: The recognisable Bruttokaltmiete, in euro per month.
        max_area_sqm: The admissible Wohnfläche the cap is stated for.
        kalte_betriebskosten_per_sqm: Kalte Betriebskosten charged locally, in
            euro per square metre and month, one value per row.

    Returns:
        The rent per square metre a dwelling may cost net of kalte
        Betriebskosten before it exceeds the cap.

    """
    with np.errstate(divide="ignore", invalid="ignore"):
        per_sqm = np.divide(
            cap_eur_per_month,
            max_area_sqm,
            out=np.full_like(cap_eur_per_month, np.nan, dtype=float),
            where=max_area_sqm > 0,
        )
    return per_sqm - kalte_betriebskosten_per_sqm


def share_above_threshold(
    band_counts: np.ndarray,
    threshold_eur_per_sqm: np.ndarray,
) -> np.ndarray:
    """Return the share of dwellings priced above `threshold_eur_per_sqm`.

    Dwellings are counted band by band. A band lying entirely above the
    threshold contributes in full and one lying entirely below contributes
    nothing. The band containing the threshold contributes the fraction of its
    width above it, which assumes rents are distributed uniformly inside a
    band.

    Args:
        band_counts: Dwelling counts, one row per Gemeinde and one column per
            entry of `RENT_BANDS`, in the same order.
        threshold_eur_per_sqm: One threshold per row of `band_counts`.

    Returns:
        The share of each row's dwellings priced above its threshold, as a
        proportion. Rows with no dwellings or no threshold yield `nan`.

    """
    _fail_if_band_counts_misshaped(band_counts)
    lower = np.array([band.lower_edge for band in RENT_BANDS])
    upper = np.array([band.upper_edge for band in RENT_BANDS])

    threshold = threshold_eur_per_sqm[:, np.newaxis]
    fraction_above = np.clip((upper - threshold) / (upper - lower), 0.0, 1.0)

    dwellings_above = np.nansum(band_counts * fraction_above, axis=1)
    dwellings_total = np.nansum(band_counts, axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        share = np.divide(
            dwellings_above,
            dwellings_total,
            out=np.full_like(dwellings_total, np.nan, dtype=float),
            where=dwellings_total > 0,
        )
    return np.where(np.isnan(threshold_eur_per_sqm), np.nan, share)


def summarise_shares(gemeinde_shares: pd.DataFrame) -> pd.DataFrame:
    """Summarise the two shares priced above the cap, and their difference, by size.

    Args:
        gemeinde_shares: The output of {func}`build_gemeinde_shares`.

    Returns:
        One row per household size and cap, plus one row per household size
        for the absolute difference between the two, each with the median and
        the tenth and ninetieth percentiles across Gemeinden.

    """
    quantities = {
        "Local KdU cap": "share_above_local_kdu_cap",
        "Statutory fallback": "share_above_wohngeld_fallback_cap",
        "Absolute difference": "absolute_share_difference",
    }
    household_sizes = sorted(
        int(size) for size in gemeinde_shares["household_size"].unique()
    )
    rows = [
        _summary_row(
            gemeinde_shares.loc[gemeinde_shares["household_size"] == household_size],
            household_size,
            label,
            column,
        )
        for household_size in household_sizes
        for label, column in quantities.items()
    ]
    return pd.DataFrame(rows)


def share_of_stock_above_cap_figure(gemeinde_shares: pd.DataFrame) -> go.Figure:
    """Plot the distribution of the two shares and of their difference.

    Args:
        gemeinde_shares: The output of {func}`build_gemeinde_shares`.

    Returns:
        A figure with the two priced-above-the-cap distributions above and the
        per-Gemeinde difference between them below, at household size one.

    """
    single = gemeinde_shares.query("household_size == 1")
    figure = go.Figure()
    for label, column, colour in (
        ("Statutory fallback", "share_above_wohngeld_fallback_cap", FALLBACK_COLOUR),
        ("Local KdU cap", "share_above_local_kdu_cap", LOCAL_CAP_COLOUR),
    ):
        figure.add_histogram(
            x=single[column] * 100,
            name=label,
            marker_color=colour,
            opacity=0.6,
            xbins={"start": 0, "end": 100, "size": 2},
        )
    median_difference = float(single["absolute_share_difference"].median()) * 100
    figure.add_annotation(
        xref="paper",
        yref="paper",
        x=0.98,
        y=0.95,
        xanchor="right",
        text=(
            "Median absolute difference between the two<br>"
            f"in a single Gemeinde: <b>{median_difference:.1f}</b> percentage points"
        ),
        showarrow=False,
        align="right",
        font={"size": 12, "color": DIFFERENCE_COLOUR},
    )
    figure.update_layout(
        title=(
            "Share of the local rented stock priced above the cap "
            "(single-person household)"
        ),
        xaxis_title="Share of rented dwellings above the cap, per cent",
        yaxis_title="Gemeinden",
        barmode="overlay",
        legend={"orientation": "h", "y": -0.18},
    )
    figure.update_xaxes(showgrid=False)
    figure.update_yaxes(showgrid=True, gridcolor="#333333")
    return figure


def _summary_row(
    group: pd.DataFrame,
    household_size: int,
    label: str,
    column: str,
) -> dict[str, object]:
    """Return the median and decile bounds of one quantity at one household size."""
    return {
        "household_size": household_size,
        "quantity": label,
        "n_gemeinden": int(group[column].notna().sum()),
        "median": float(group[column].median()),
        "percentile_10": float(group[column].quantile(0.10)),
        "percentile_90": float(group[column].quantile(0.90)),
    }


def _join_caps_to_rent_bands(
    kdu_caps: pd.DataFrame,
    wohngeld_fallback: pd.DataFrame,
    zensus_rents: pd.DataFrame,
) -> pd.DataFrame:
    """Join the caps, the fallback and the Zensus band counts into one frame."""
    caps = kdu_caps.loc[:, ["ags", "household_size", "kdu_cap", "max_area_sqm"]]
    fallback = wohngeld_fallback.loc[
        :,
        [
            "ags",
            "household_size",
            "mietenstufe",
            "wohngeld_fallback_cap",
            "wohngeld_rule_suspected",
        ],
    ]
    rents = zensus_rents.loc[:, ["ags", *(band.column for band in RENT_BANDS)]]

    frame = merge_without_duplicating(caps, fallback, on=["ags", "household_size"])
    frame = merge_without_duplicating(frame, rents, on=["ags"])
    return frame.astype(
        {
            "household_size": "int64",
            "kdu_cap": "float64",
            "max_area_sqm": "float64",
            "wohngeld_fallback_cap": "float64",
            "mietenstufe": "Int64",
        }
        | {band.column: "float64" for band in RENT_BANDS},
    )


def _fail_if_band_counts_misshaped(band_counts: np.ndarray) -> None:
    """Raise if the dwelling counts do not carry one column per rent band."""
    if band_counts.ndim != BAND_COUNT_DIMENSIONS or band_counts.shape[1] != len(
        RENT_BANDS
    ):
        msg = (
            f"band_counts must have one column per rent band, so shape "
            f"(n_gemeinden, {len(RENT_BANDS)}), not {band_counts.shape}"
        )
        raise ValueError(msg)


def _kalte_betriebskosten_per_gemeinde(
    ags: pd.Series,
    gemeinden: pd.DataFrame,
    wohnkostenstatistik: pd.DataFrame,
) -> pd.Series:
    """Return the kalte Betriebskosten each Gemeinde is charged.

    The unit is euro per square metre and month.

    The Bundesagentur publishes the figure per Jobcenter and household size.
    It is averaged over household sizes weighted by Bedarfsgemeinschaften,
    which gives the amount the Kreis's claimants actually face, and then
    carried to every Gemeinde of that Kreis. Kreise reporting nothing take the
    national mean on the same weighting.
    """
    reported = wohnkostenstatistik.dropna(
        subset=[KALTE_BETRIEBSKOSTEN_COLUMN, "bedarfsgemeinschaften", "district_ags"],
    )
    weight = reported["bedarfsgemeinschaften"]
    weighted = reported[KALTE_BETRIEBSKOSTEN_COLUMN] * weight
    per_kreis = (
        weighted.groupby(reported["district_ags"]).sum()
        / weight.groupby(
            reported["district_ags"],
        ).sum()
    )
    national = weighted.sum() / weight.sum()

    district = ags.map(gemeinden.set_index("ags")["district_ags"])
    return district.map(per_kreis).astype(float).fillna(national)
