"""Do the collected caps agree with what Jobcenter actually recognise?

The caps in this project are read off roughly four hundred municipal
Richtlinien. Nothing internal to that collection can establish that the reading
was correct. The Bundesagentur für Arbeit publishes, per Jobcenter and
household size, the mean Bruttokaltmiete that Bedarfsgemeinschaften pay and the
mean amount their Jobcenter recognises, and the difference between the two is
the only administrative record of a local cap binding. This module tests one
implication of the caps being right: where a cap is tight relative to the local
rental market, a larger share of reported housing costs should go unrecognised.

The claim is about data quality. It says the extraction corresponds to
administrative reality; it says nothing about whether local caps are adequate,
which the other analysis packages address.

Three properties govern how the resulting number may be read.

- **The published shares are shares of euro, not of households.** Both
  Bundesagentur figures are means over all Bedarfsgemeinschaften, including the
  majority whose costs are recognised in full, and the source publishes no
  count of Bedarfsgemeinschaften with any shortfall at all. A mean
  non-recognised share of four percent is equally consistent with ninety
  percent of households losing nothing while ten percent lose a great deal. No
  statement about a share of affected households may be derived from it.
- **The correlation is attenuated by construction.** A constraint that binds
  for a small part of the reported costs has a correspondingly weak correlate.
  A correlation near a quarter confirms that the caps point in the right
  direction; it is not evidence that caps account for non-recognition.
- **Market pressure is measured independently of the Bundesagentur figures.**
  `non_recognised_share` is one minus recognised over actual Bruttokaltmiete,
  so the actual Bruttokaltmiete already appears in it. Correlating it against a
  ratio built from that same actual Bruttokaltmiete would put one variable on
  both sides and inflate the result. Local market pressure is therefore taken
  from the Zensus 2022 Nettokaltmiete, which the Bundesagentur figures do not
  enter, evaluated at the Wohnfläche the local rule admits.

The Bundesagentur reports by Jobcenter while caps are set per Gemeinde, and 209
of 357 Kreise publish Gemeinde-specific caps rather than one Kreis-wide figure.
Aggregating to the Jobcenter therefore requires a choice, and this module takes
the population-weighted mean over the Gemeinden of the Kreis: the cap faced by
the average resident, which is the closest available match to the population
the Bundesagentur reports on.

Everything here is a pure function of frames handed in; the pytask task in
{mod}`kdu.validation.task_validate_against_wohnkostenstatistik` owns the I/O.
"""

import numpy as np
import pandas as pd

from kdu.joins import fail_if_key_not_unique, merge_without_duplicating

# Columns of the table this module returns, in order.
VALIDATION_COLUMNS: tuple[str, ...] = (
    "household_size",
    "jobcenter",
    "jobcenter_with_market_rent",
    "correlation_market_pressure_non_recognised",
    "mean_kdu_cap_eur",
    "mean_market_rent_eur",
    "mean_actual_bruttokaltmiete_eur",
    "mean_recognised_bruttokaltmiete_eur",
    "mean_shortfall_eur",
    "mean_non_recognised_share",
    "bedarfsgemeinschaft_weighted_non_recognised_share",
)

# Columns holding counts of Jobcenter rather than euro amounts or shares.
_COUNT_COLUMNS: tuple[str, ...] = ("jobcenter", "jobcenter_with_market_rent")

# Fewer Jobcenter than this leave a correlation undefined.
MIN_JOBCENTER_FOR_CORRELATION = 2


def validate_against_wohnkostenstatistik(
    wohnkostenstatistik: pd.DataFrame,
    district_market_pressure: pd.DataFrame,
) -> pd.DataFrame:
    """Compare the collected caps with the Bundesagentur record, by household size.

    Args:
        wohnkostenstatistik: One row per Jobcenter and household size, as
            written by {mod}`kdu.data_management.clean_wohnkostenstatistik`.
        district_market_pressure: One row per Kreis and household size, as
            returned by {func}`build_district_market_pressure`.

    Returns:
        One row per household size, with `VALIDATION_COLUMNS`. `jobcenter`
        counts the Jobcenter contributing to the level statistics and
        `jobcenter_with_market_rent` the smaller number that also carry a
        Zensus market rent, which is the number the correlation rests on.

    """
    _fail_if_columns_missing(
        wohnkostenstatistik,
        ("jobcenter_id", "district_ags", "household_size"),
    )
    fail_if_key_not_unique(district_market_pressure, ["district_ags", "household_size"])

    joined = merge_without_duplicating(
        wohnkostenstatistik.dropna(subset=["district_ags"]),
        district_market_pressure,
        on=["district_ags", "household_size"],
    )
    joined = joined.assign(
        shortfall_eur=joined["actual_bruttokaltmiete"]
        - joined["recognised_bruttokaltmiete"],
        log_market_rent_over_cap=_log_ratio(
            joined["market_rent_eur"],
            joined["kdu_cap"],
        ),
    )

    summarised = joined.groupby("household_size", as_index=False).apply(
        _summarise_household_size,
        include_groups=False,
    )
    counts = dict.fromkeys(_COUNT_COLUMNS, "int64")
    return (
        summarised.loc[:, list(VALIDATION_COLUMNS)]
        .astype({"household_size": "int64", **counts})
        .sort_values("household_size")
        .reset_index(drop=True)
    )


def build_district_market_pressure(
    kdu_caps: pd.DataFrame,
    gemeinden: pd.DataFrame,
    zensus_rents: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate caps and market rents from Gemeinden to the Kreis they sit in.

    Each quantity is a population-weighted mean over the Gemeinden of the Kreis,
    so it describes what the average resident faces rather than what the average
    Gemeinde publishes. `market_rent_eur` evaluates the local Zensus
    Nettokaltmiete at the Wohnfläche the local rule admits, which puts it on the
    same scale as the monthly cap.

    Args:
        kdu_caps: One row per Gemeinde and household size, with `kdu_cap` and
            `max_area_sqm`.
        gemeinden: One row per Gemeinde, with `district_ags` and `population`.
        zensus_rents: One row per Gemeinde, with
            `nettokaltmiete_eur_per_sqm_mean`.

    Returns:
        One row per Kreis and household size, with `district_ags`,
        `household_size`, `kdu_cap`, `max_area_sqm`,
        `nettokaltmiete_eur_per_sqm` and `market_rent_eur`.

    """
    _fail_if_columns_missing(kdu_caps, ("ags", "household_size", "kdu_cap"))
    fail_if_key_not_unique(gemeinden, ["ags"])
    fail_if_key_not_unique(zensus_rents, ["ags"])

    with_district = merge_without_duplicating(
        kdu_caps,
        gemeinden.loc[:, ["ags", "district_ags", "population"]],
        on=["ags"],
    )
    with_rents = merge_without_duplicating(
        with_district,
        zensus_rents.loc[:, ["ags", "nettokaltmiete_eur_per_sqm_mean"]],
        on=["ags"],
    )

    by_district = ["district_ags", "household_size"]
    aggregated = pd.DataFrame(
        {
            "kdu_cap": grouped_weighted_mean(
                with_rents,
                "kdu_cap",
                "population",
                by_district,
            ),
            "max_area_sqm": grouped_weighted_mean(
                with_rents,
                "max_area_sqm",
                "population",
                by_district,
            ),
            "nettokaltmiete_eur_per_sqm": grouped_weighted_mean(
                with_rents,
                "nettokaltmiete_eur_per_sqm_mean",
                "population",
                by_district,
            ),
        },
    ).reset_index()
    return aggregated.assign(
        market_rent_eur=aggregated["nettokaltmiete_eur_per_sqm"]
        * aggregated["max_area_sqm"],
    )


def grouped_weighted_mean(
    frame: pd.DataFrame,
    value_column: str,
    weight_column: str,
    by: list[str],
) -> pd.Series:
    """Return the weighted mean of `value_column` within each group of `by`.

    Rows with a missing value or a missing weight contribute to neither the
    numerator nor the denominator, so a Gemeinde that publishes no cap does not
    pull its Kreis towards zero. A group in which no row carries both returns
    `nan`.

    Args:
        frame: The rows to aggregate.
        value_column: The quantity to average.
        weight_column: Non-negative weights.
        by: Grouping columns.

    Returns:
        The weighted means, indexed by `by`.

    """
    values = pd.to_numeric(frame[value_column], errors="coerce")
    weights = pd.to_numeric(frame[weight_column], errors="coerce")
    usable = values.notna() & weights.notna()

    weighted = pd.DataFrame(
        {
            "weighted_value": (values * weights).where(usable, other=np.nan),
            "weight": weights.where(usable, other=np.nan),
        },
    )
    totals = weighted.join(frame.loc[:, by]).groupby(by, dropna=False).sum(min_count=1)
    return (totals["weighted_value"] / totals["weight"]).rename(value_column)


def _summarise_household_size(group: pd.DataFrame) -> pd.Series:
    """Return the correlation and the levels for one household size."""
    comparable = group.dropna(
        subset=["log_market_rent_over_cap", "non_recognised_share"],
    )
    return pd.Series(
        {
            "jobcenter": len(group),
            "jobcenter_with_market_rent": len(comparable),
            "correlation_market_pressure_non_recognised": _correlation(
                comparable["log_market_rent_over_cap"],
                comparable["non_recognised_share"],
            ),
            "mean_kdu_cap_eur": _mean(group["kdu_cap"]),
            "mean_market_rent_eur": _mean(group["market_rent_eur"]),
            "mean_actual_bruttokaltmiete_eur": _mean(group["actual_bruttokaltmiete"]),
            "mean_recognised_bruttokaltmiete_eur": _mean(
                group["recognised_bruttokaltmiete"],
            ),
            "mean_shortfall_eur": _mean(group["shortfall_eur"]),
            "mean_non_recognised_share": _mean(group["non_recognised_share"]),
            "bedarfsgemeinschaft_weighted_non_recognised_share": _weighted_mean(
                group["non_recognised_share"],
                group["bedarfsgemeinschaften"],
            ),
        },
    )


def _correlation(first: pd.Series, second: pd.Series) -> float:
    """Return the Pearson correlation, or `nan` if too few observations remain."""
    if len(first) < MIN_JOBCENTER_FOR_CORRELATION:
        return float("nan")
    return float(first.astype(float).corr(second.astype(float)))


def _mean(values: pd.Series) -> float:
    """Return the unweighted mean, ignoring missing values."""
    return float(pd.to_numeric(values, errors="coerce").mean())


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    """Return the mean of `values` weighted by `weights`, ignoring missing rows."""
    numeric_values = pd.to_numeric(values, errors="coerce")
    numeric_weights = pd.to_numeric(weights, errors="coerce")
    usable = numeric_values.notna() & numeric_weights.notna()
    if not usable.any() or numeric_weights[usable].sum() == 0:
        return float("nan")
    return float(
        np.average(numeric_values[usable], weights=numeric_weights[usable]),
    )


def _log_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Return `log(numerator / denominator)`, missing where either is not positive."""
    top = pd.to_numeric(numerator, errors="coerce")
    bottom = pd.to_numeric(denominator, errors="coerce")
    ratio = (top / bottom).where((top > 0) & (bottom > 0))
    return np.log(ratio.astype(float))


def _fail_if_columns_missing(frame: pd.DataFrame, required: tuple[str, ...]) -> None:
    """Raise if `frame` lacks a column the comparison needs."""
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        msg = f"the frame is missing required column(s) {missing}"
        raise ValueError(msg)
