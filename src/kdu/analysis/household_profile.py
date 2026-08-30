"""The household-size profile of local KdU caps and the Familien-Tilt (§10, P0.5).

The question this module answers is whether local KdU regimes differ in *how*
the recognised Bruttokaltmiete rises with household size, and not merely in its
level. Three objects carry that:

- the marginal amounts `ΔK(g,h)` and `ΔW(g,h)` per additional person, their
  ratio `Q(g,h)`, and the per-capita caps `K/h` and `W/h` (§10.1);
- the Familien-Tilt `F_g = log(K_g4/W_g4) - log(K_g1/W_g1)`, positive where the
  local cap sits relatively higher for a four-person household than for a
  single (§10.2);
- the rank stability of Gemeinden between household sizes (§10.3).

Two data facts shape every function here.

- `ΔW` can be missing, because 119 main-sample Gemeinden are gemeindefreie
  Gebiete with no statutory Mietenstufe and therefore no Wohngeld benchmark at
  all (A2). It can in principle also be zero. In both cases `Q` is reported as
  missing with a `MarginalRatioStatus` naming the reason; no infinity is ever
  produced. The same applies to the tilt, which needs `K/W` at both h.
- `wogg_linked_flag` Gemeinden apply the § 12 WoGG table plus a fixed
  Sicherheitszuschlag (D7). Where K is a fixed multiple of W at every h the
  tilt is zero by construction, so every tilt distribution is reported with and
  without them and `check_wogg_linked_tilt` measures how exactly that holds.

Everything in this module is a pure function of a long frame keyed
`ags x household_size`; the pytask task in `task_household_profile.py` owns all
I/O and the choice of sample, benchmark and weights.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import pandas as pd

from kdu.analysis.proxy_error import observation_weights
from kdu.config import BLD, TABLES, WeightingScheme

# Column holding the local KdU Bruttokaltmiete cap `K(g,h)`.
KDU_COLUMN = "kdu_bkc_cap"
# Primary Wohngeld benchmark `W(g,h)`: the Anlage 1 Höchstbetrag times the
# BSG Sicherheitszuschlag (D15). The Familien-Tilt is a difference of log gaps
# across household sizes, so the constant markup cancels and the tilt is
# numerically identical to the bare-table one; the euro levels are not.
WOGG_PRIMARY_COLUMN = "wogg_primary_cap"
# Robustness benchmark: Höchstbetrag plus Klimakomponente (D6, §18).
WOGG_KLIMA_COLUMN = "wogg_bkc_cap"
# Household size the Familien-Tilt is measured against.
TILT_REFERENCE_SIZE = 1
# Household sizes for which a Familien-Tilt is reported.
TILT_SIZES: tuple[int, ...] = (3, 4, 5)
# Headline tilt: four-person household against a single.
HEADLINE_TILT_SIZE = 4
# A step whose absolute value is below this counts as no step at all.
ZERO_STEP_TOLERANCE = 1e-9
# A tilt whose absolute value is below this counts as exactly zero.
ZERO_TILT_TOLERANCE = 1e-9
# Number of quantile groups used throughout the rank-stability analysis.
N_DECILES = 10
# A Gemeinde counts as having moved when its decile changes by at least this.
DECILE_MOVE_THRESHOLD = 2
# Fewest complete pairs a rank correlation can be formed from.
MIN_PAIRS_FOR_CORRELATION = 2
# Tolerance under which a flagged Gemeinde counts as effectively flat, which
# is the rounding of caps published in whole euro.
NEAR_ZERO_TILT_TOLERANCE = 1e-3
# Quantiles reported for every distribution.
REPORTED_QUANTILES: tuple[float, ...] = (0.10, 0.25, 0.50, 0.75, 0.90)

# Per-Gemeinde tilts, relative levels and metadata, on the h=1…4 main sample.
HOUSEHOLD_PROFILE_GEMEINDE = BLD / "household_profile_gemeinde.parquet"
# The same, on the h=1…5 balanced subsample (D3), never mixed with the above.
HOUSEHOLD_PROFILE_GEMEINDE_H5 = BLD / "household_profile_gemeinde_h5.parquet"
# Marginal amounts keyed `ags x household_size`.
HOUSEHOLD_PROFILE_MARGINAL = BLD / "household_profile_marginal.parquet"
# §10.1 summary of the marginal amounts per additional person.
TABLE_MARGINAL = TABLES / "table_household_profile_marginal.csv"
# §10.2 tilt distribution, with and without the WoGG-linked Gemeinden.
TABLE_TILT = TABLES / "table_household_profile_tilt.csv"
# §10.3 Spearman correlations and decile-movement shares.
TABLE_RANK_STABILITY = TABLES / "table_household_profile_rank_stability.csv"
# §10.3 decile transition matrix, h=1 against h=4.
TABLE_TRANSITION = TABLES / "table_household_profile_decile_transition.csv"
# §18 robustness grid for the headline tilt.
TABLE_ROBUSTNESS = TABLES / "table_household_profile_robustness.csv"
# The D7 verification: is the flagged group's tilt zero?
TABLE_WOGG_LINKED_CHECK = TABLES / "table_household_profile_wogg_linked_check.csv"
# The §21 four-part interpretation of the four §10.4 figures.
INTERPRETATION_TEXT = TABLES / "household_profile_interpretation.md"


class MarginalRatioStatus(StrEnum):
    """Why `Q(g,h) = ΔK/ΔW` is or is not defined for one Gemeinde and size."""

    DEFINED = "defined"
    """Both steps exist and the Wohngeld step is non-zero."""
    NO_PREVIOUS_SIZE = "no_previous_size"
    """The smallest household size in the frame has no predecessor."""
    KDU_STEP_MISSING = "kdu_step_missing"
    """No local cap at this size or the one below it."""
    WOGG_STEP_MISSING = "wogg_step_missing"
    """No statutory Mietenstufe, so no Wohngeld benchmark exists (A2)."""
    WOGG_STEP_ZERO = "wogg_step_zero"
    """The Höchstbetrag does not change with this additional person."""


def build_marginal_amounts(
    long: pd.DataFrame,
    *,
    kdu_column: str = KDU_COLUMN,
    wogg_column: str = WOGG_PRIMARY_COLUMN,
) -> pd.DataFrame:
    """Compute the §10.1 marginal and per-capita amounts.

    Args:
        long: Frame keyed `ags x household_size` carrying the two cap columns.
            The household sizes present must be contiguous within each Gemeinde.
        kdu_column: Column holding `K(g,h)`.
        wogg_column: Column holding `W(g,h)`.

    Returns:
        One row per `ags x household_size` with `kdu_cap`, `wogg_cap`,
        `kdu_step`, `wogg_step`, `marginal_ratio`, `marginal_ratio_status`,
        `kdu_per_capita` and `wogg_per_capita`. `marginal_ratio` is never
        infinite: where the Wohngeld step is missing or zero it is missing, and
        `marginal_ratio_status` names which.

    Raises:
        ValueError: If a Gemeinde's household sizes are not contiguous.

    """
    _fail_if_household_sizes_are_not_contiguous(long)
    ordered = long.sort_values(["ags", "household_size"]).reset_index(drop=True)

    frame = pd.DataFrame(index=ordered.index)
    frame["ags"] = ordered["ags"].astype("string")
    frame["household_size"] = ordered["household_size"].astype("int64")
    frame["kdu_cap"] = _as_float(ordered[kdu_column])
    frame["wogg_cap"] = _as_float(ordered[wogg_column])
    frame["kdu_step"] = frame.groupby("ags")["kdu_cap"].diff()
    frame["wogg_step"] = frame.groupby("ags")["wogg_cap"].diff()
    frame["marginal_ratio_status"] = _classify_marginal_ratio(frame)
    frame["marginal_ratio"] = _safe_ratio(
        frame["kdu_step"],
        frame["wogg_step"],
        defined=frame["marginal_ratio_status"] == MarginalRatioStatus.DEFINED,
    )
    frame["kdu_per_capita"] = frame["kdu_cap"] / frame["household_size"]
    frame["wogg_per_capita"] = frame["wogg_cap"] / frame["household_size"]
    return frame


def build_familien_tilt(
    long: pd.DataFrame,
    *,
    sizes: Sequence[int] = TILT_SIZES,
    reference_size: int = TILT_REFERENCE_SIZE,
    kdu_column: str = KDU_COLUMN,
    wogg_column: str = WOGG_PRIMARY_COLUMN,
) -> pd.DataFrame:
    """Compute the §10.2 Familien-Tilt and the average relative KdU level.

    `F_g(h) = log(K_gh / W_gh) - log(K_g1 / W_g1)`. A positive value means the
    local cap sits relatively higher for a household of size `h` than for a
    single; a negative value the reverse. Where K is a fixed multiple of W at
    both sizes the tilt is exactly zero, which is the D7 case.

    Args:
        long: Frame keyed `ags x household_size` carrying the two cap columns.
        sizes: Household sizes to report a tilt for. Sizes absent from `long`
            are skipped rather than filled with missing values.
        reference_size: The size the tilt is measured against, normally the
            single-person household.
        kdu_column: Column holding `K(g,h)`.
        wogg_column: Column holding `W(g,h)`.

    Returns:
        One row per Gemeinde, indexed by `ags`, with
        `log_relative_level_h{h}` for every size present,
        `mean_log_relative_level` averaged over those sizes, and `tilt_h{h}`
        for every requested size. Any tilt whose two ingredients are not both
        available is missing.

    Raises:
        ValueError: If `reference_size` is absent from `long`.

    """
    ratio = _log_relative_level(long, kdu_column=kdu_column, wogg_column=wogg_column)
    if reference_size not in ratio.columns:
        msg = (
            f"reference household size {reference_size} is absent from the frame; "
            f"sizes present are {sorted(ratio.columns)}"
        )
        raise ValueError(msg)

    frame = pd.DataFrame(index=ratio.index)
    for size in sorted(ratio.columns):
        frame[f"log_relative_level_h{size}"] = ratio[size]
    frame["mean_log_relative_level"] = ratio.mean(axis=1)
    frame["n_relative_levels"] = ratio.notna().sum(axis=1).astype("int64")
    for size in sizes:
        if size in ratio.columns:
            frame[f"tilt_h{size}"] = ratio[size] - ratio[reference_size]
    return frame


def spearman_correlation(first: pd.Series, second: pd.Series) -> float:
    """Return the Spearman rank correlation over the pairwise-complete rows.

    The coefficient is the Pearson correlation of the average ranks, so ties
    are handled the standard way and no SciPy dependency is needed.

    Args:
        first: One series.
        second: The other, aligned by position.

    Returns:
        The coefficient, or `nan` if fewer than two complete pairs remain or
        either ranking is constant.

    """
    left = pd.Series(np.asarray(first, dtype="float64"))
    right = pd.Series(np.asarray(second, dtype="float64"))
    complete = left.notna() & right.notna()
    if int(complete.sum()) < MIN_PAIRS_FOR_CORRELATION:
        return float("nan")
    left_ranks = left[complete].rank().to_numpy()
    right_ranks = right[complete].rank().to_numpy()
    if left_ranks.std() == 0 or right_ranks.std() == 0:
        return float("nan")
    return float(np.corrcoef(left_ranks, right_ranks)[0, 1])


def decile_group(values: pd.Series, *, n_quantiles: int = N_DECILES) -> pd.Series:
    """Assign each observation to an equally sized quantile group, 1 to `n`.

    Ties are broken by position so that the groups are exactly equal in size;
    the alternative, cutting on the values themselves, collapses whenever a cap
    value repeats often enough to span a bin edge, which German KdU caps do.

    Args:
        values: The values to rank.
        n_quantiles: Number of groups; ten for deciles.

    Returns:
        A nullable-integer series of group numbers, missing where `values` is.

    Raises:
        ValueError: If there are fewer non-missing values than groups.

    """
    present = values.notna()
    if int(present.sum()) < n_quantiles:
        msg = (
            f"decile assignment needs at least {n_quantiles} non-missing values, "
            f"got {int(present.sum())}"
        )
        raise ValueError(msg)
    groups = pd.Series(pd.NA, index=values.index, dtype="Int64")
    ordered = values[present].rank(method="first")
    groups.loc[present] = (
        pd.qcut(ordered, n_quantiles, labels=range(1, n_quantiles + 1))
        .astype("int64")
        .to_numpy()
    )
    return groups


def decile_transition_matrix(
    first: pd.Series,
    second: pd.Series,
    *,
    n_quantiles: int = N_DECILES,
) -> pd.DataFrame:
    """Return the row-normalised decile transition matrix between two rankings.

    Args:
        first: Values defining the row deciles, for example `K(g,1)`.
        second: Values defining the column deciles, for example `K(g,4)`.
        n_quantiles: Number of groups; ten for deciles.

    Returns:
        A `n x n` frame whose rows are conditional distributions summing to
        one, indexed and columned `1 … n`.

    Raises:
        ValueError: If fewer than `n_quantiles` Gemeinden have both values.

    """
    complete = first.notna() & second.notna()
    rows = decile_group(first[complete], n_quantiles=n_quantiles)
    columns = decile_group(second[complete], n_quantiles=n_quantiles)
    counts = pd.crosstab(rows, columns).reindex(
        index=range(1, n_quantiles + 1),
        columns=range(1, n_quantiles + 1),
        fill_value=0,
    )
    matrix = counts.astype("float64").div(counts.sum(axis=1).astype("float64"), axis=0)
    matrix.index.name = "decile_first"
    matrix.columns.name = "decile_second"
    return matrix


def share_moving_at_least_deciles(
    first: pd.Series,
    second: pd.Series,
    *,
    threshold: int = DECILE_MOVE_THRESHOLD,
    n_quantiles: int = N_DECILES,
) -> float:
    """Return the share of Gemeinden whose decile changes by at least `threshold`.

    Args:
        first: Values defining the starting decile.
        second: Values defining the ending decile.
        threshold: Inclusive number of deciles a Gemeinde must move to count.
        n_quantiles: Number of groups; ten for deciles.

    Returns:
        The share among Gemeinden with both values present.

    """
    complete = first.notna() & second.notna()
    rows = decile_group(first[complete], n_quantiles=n_quantiles).astype("int64")
    columns = decile_group(second[complete], n_quantiles=n_quantiles).astype("int64")
    return float((rows - columns).abs().ge(threshold).mean())


def weighted_quantile(
    values: pd.Series,
    weights: pd.Series,
    quantiles: Sequence[float],
) -> np.ndarray:
    """Return the weighted quantiles of `values`, dropping missing rows.

    The estimator is the left-continuous inverse of the weighted empirical
    distribution function: the smallest value whose cumulative weight share
    reaches the requested quantile. Under equal weights it reproduces the
    plain lower-median convention on an odd number of observations.

    Args:
        values: The values to summarise.
        weights: Non-negative weights aligned to `values`.
        quantiles: Quantiles in `[0, 1]`.

    Returns:
        One value per requested quantile, `nan` where no weight remains.

    """
    frame = pd.DataFrame({"value": values, "weight": weights}).dropna()
    frame = frame.loc[frame["weight"] > 0].sort_values("value")
    if frame.empty:
        return np.full(len(quantiles), np.nan)
    cumulative = frame["weight"].cumsum().to_numpy() / frame["weight"].sum()
    positions = np.searchsorted(cumulative, np.asarray(quantiles), side="left")
    positions = np.clip(positions, 0, len(frame) - 1)
    return frame["value"].to_numpy()[positions]


def summarise_distribution(
    values: pd.Series,
    weights: pd.Series | None = None,
) -> pd.Series:
    """Summarise one distribution the way every §10 table reports it.

    Args:
        values: The values to summarise.
        weights: Optional weights; all-ones when omitted.

    Returns:
        A series with `n`, `n_weighted`, `mean`, the `REPORTED_QUANTILES` as
        `p10` … `p90`, `share_positive`, `share_negative` and
        `share_exact_zero`. Shares are weighted whenever `weights` is given, so
        that the population-weighted pile-up at zero stays visible. `n` counts
        every observation with a value, `n_weighted` only those carrying
        positive weight — the two differ because 117 gemeindefreie Gebiete in
        the main sample have zero inhabitants.

    """
    effective = pd.Series(1.0, index=values.index) if weights is None else weights
    complete = pd.DataFrame({"value": values, "weight": effective}).dropna()
    frame = complete.loc[complete["weight"] > 0]
    if frame.empty:
        return pd.Series(dtype="float64")

    total = float(frame["weight"].sum())
    quantile_values = weighted_quantile(
        frame["value"],
        frame["weight"],
        REPORTED_QUANTILES,
    )
    summary = {
        "n": float(len(complete)),
        "n_weighted": float(len(frame)),
        "mean": float(np.average(frame["value"], weights=frame["weight"])),
    }
    for quantile, value in zip(REPORTED_QUANTILES, quantile_values, strict=True):
        summary[f"p{round(quantile * 100)}"] = float(value)
    summary["share_positive"] = _weighted_share(frame, frame["value"] > 0, total)
    summary["share_negative"] = _weighted_share(frame, frame["value"] < 0, total)
    summary["share_exact_zero"] = _weighted_share(
        frame,
        frame["value"].abs() <= ZERO_TILT_TOLERANCE,
        total,
    )
    return pd.Series(summary)


def bedarfsgemeinschaft_weights(
    gemeinde: pd.DataFrame,
    stocks: pd.DataFrame,
    *,
    household_size: int,
) -> pd.Series:
    """Weight every Gemeinde by its Bedarfsgemeinschaft stock (§8.2 scheme 4).

    The weight is the one P0.3 defines and builds: BA publishes the stock per
    Kreis and household size, and `observation_weights` spreads it over the
    Kreis's Gemeinden in proportion to population, because no Gemeinde-level
    stock is published. Calling P0.3's function rather than restating the rule
    keeps that assumption in one place, so the two modules cannot drift apart.

    A tilt measured at size `h` against a single is weighted by the stock at
    `h`, which is the group of Bedarfsgemeinschaften the tilt describes.

    Args:
        gemeinde: One row per Gemeinde, indexed by `ags`, carrying
            `policy_region_id` and `population`.
        stocks: `policy_region_id × household_size × bg_stock`, as
            `kdu.analysis.proxy_error.load_bedarfsgemeinschaft_stocks` returns.
        household_size: The household size whose stock does the weighting.

    Returns:
        The weight of every Gemeinde, indexed like `gemeinde`; zero where the
        Kreis reports no stock at this household size.

    """
    frame = pd.DataFrame(
        {
            "policy_region_id": gemeinde["policy_region_id"].astype("string"),
            "population": gemeinde["population"].astype("float64"),
            "household_size": household_size,
        },
        index=gemeinde.index,
    )
    weights = observation_weights(
        frame,
        WeightingScheme.BEDARFSGEMEINSCHAFT,
        stocks,
    )
    return weights.rename(WeightingScheme.BEDARFSGEMEINSCHAFT.value)


def build_tilt_summary(
    tilt: pd.Series,
    *,
    wogg_linked: pd.Series,
    weights: Mapping[str, pd.Series],
) -> pd.DataFrame:
    """Report a tilt distribution by WoGG-link status and weighting scheme (D7).

    Args:
        tilt: The Familien-Tilt, indexed by `ags`.
        wogg_linked: `wogg_linked_flag`, indexed the same way.
        weights: Weighting schemes to report, keyed by their §8.2 name.

    Returns:
        One row per `(group, weighting_scheme)` with the columns
        `summarise_distribution` produces.

    """
    groups = {
        "all": pd.Series(data=True, index=tilt.index),
        "excluding_wogg_linked": ~wogg_linked.reindex(tilt.index).fillna(value=False),
        "wogg_linked_only": wogg_linked.reindex(tilt.index).fillna(value=False),
    }
    rows = [
        pd.concat(
            [
                pd.Series(
                    {"group": group_name, "weighting_scheme": scheme_name},
                    dtype="object",
                ),
                summarise_distribution(
                    tilt.loc[selector],
                    weight.reindex(tilt.index).loc[selector],
                ),
            ],
        )
        for group_name, selector in groups.items()
        for scheme_name, weight in weights.items()
    ]
    return pd.DataFrame(rows).reset_index(drop=True)


def check_wogg_linked_tilt(
    tilt: pd.Series,
    wogg_linked: pd.Series,
) -> pd.Series:
    """Test empirically whether the WoGG-linked group carries no tilt (D7).

    D7 says K is a fixed multiple of W at every household size for these
    Gemeinden, which forces `F = 0`. That is a claim about the data, not an
    identity the code may assume, so it is measured here and reported. Caps are
    published rounded to whole euro, so a Gemeinde that genuinely applies the
    table can still show a tilt of a few thousandths.

    Args:
        tilt: The Familien-Tilt, indexed by `ags`.
        wogg_linked: `wogg_linked_flag`, indexed the same way.

    Returns:
        A series with the flagged and unflagged counts, the share of flagged
        Gemeinden at exactly zero, the largest absolute flagged tilt, and the
        share of flagged Gemeinden within a thousandth of zero.

    """
    flag = wogg_linked.reindex(tilt.index).fillna(value=False).astype(bool)
    flagged = tilt.loc[flag].dropna()
    unflagged = tilt.loc[~flag].dropna()
    exactly_zero = flagged.abs() <= ZERO_TILT_TOLERANCE
    return pd.Series(
        {
            "n_flagged": float(len(flagged)),
            "n_unflagged": float(len(unflagged)),
            "share_exactly_zero_flagged": float(exactly_zero.mean())
            if len(flagged)
            else float("nan"),
            "share_exactly_zero_unflagged": float(
                (unflagged.abs() <= ZERO_TILT_TOLERANCE).mean(),
            )
            if len(unflagged)
            else float("nan"),
            "max_abs_tilt_flagged": float(flagged.abs().max())
            if len(flagged)
            else float("nan"),
            "share_within_one_thousandth_flagged": float(
                (flagged.abs() <= NEAR_ZERO_TILT_TOLERANCE).mean(),
            )
            if len(flagged)
            else float("nan"),
        },
    )


@dataclass(frozen=True)
class Variant:
    """One cell of the §18 robustness grid: a distribution under one restriction."""

    dimension: str
    """The robustness dimension, for example `"quality_tier"`."""
    group: str
    """The restriction within that dimension, for example `"A only"`."""
    distribution: pd.Series
    """The values to summarise, indexed by `ags`."""
    weights: pd.Series | None = None
    """Optional weights; one per Gemeinde when the scheme is not unweighted."""
    wogg_linked: pd.Series | None = None
    """`wogg_linked_flag`, so the D7 with/without pair travels with every row."""
    note: str = ""
    """Why the cell is empty, when it is; blank otherwise."""


def build_variant_table(variants: Sequence[Variant]) -> pd.DataFrame:
    """Summarise every §18 robustness variant into one tidy table.

    Every row carries both the full distribution and the distribution with the
    WoGG-linked Gemeinden removed, because D7 forbids presenting the pooled
    figure alone. A variant with no usable observations still produces a row,
    carrying its `note`, so that an unavailable robustness check is visible
    rather than absent.

    Args:
        variants: The cells to report.

    Returns:
        One row per variant.

    """
    rows = []
    for variant in variants:
        row: dict[str, object] = {
            "dimension": variant.dimension,
            "group": variant.group,
            "note": variant.note,
        }
        row.update(
            summarise_distribution(variant.distribution, variant.weights).to_dict()
        )
        row.update(_excluding_wogg_linked(variant))
        rows.append(row)
    return pd.DataFrame(rows)


def _excluding_wogg_linked(variant: Variant) -> dict[str, float]:
    if variant.wogg_linked is None:
        return {}
    keep = ~variant.wogg_linked.reindex(variant.distribution.index).fillna(value=False)
    weights = None if variant.weights is None else variant.weights.loc[keep]
    summary = summarise_distribution(variant.distribution.loc[keep], weights)
    return {f"{name}_excl_wogg_linked": float(value) for name, value in summary.items()}


def build_rank_stability_table(
    caps: pd.DataFrame,
    relative_levels: pd.DataFrame,
    *,
    reference_size: int = TILT_REFERENCE_SIZE,
) -> pd.DataFrame:
    """Assemble the §10.3 Spearman correlations and decile-movement shares.

    Args:
        caps: Wide frame of `K(g,h)`, one column per household size.
        relative_levels: Wide frame of `log(K/W)`, one column per size.
        reference_size: The size every pair is measured against.

    Returns:
        One row per statistic with `statistic`, `household_size`, `value` and
        `n`.

    """
    rows = []
    for size in sorted(caps.columns):
        if size == reference_size:
            continue
        pair = caps[[reference_size, size]].dropna()
        rows.append(
            {
                "statistic": "spearman_kdu_cap",
                "household_size": size,
                "value": spearman_correlation(pair[reference_size], pair[size]),
                "n": len(pair),
            },
        )
        rows.append(
            {
                "statistic": "share_moving_at_least_two_deciles_kdu_cap",
                "household_size": size,
                "value": share_moving_at_least_deciles(
                    pair[reference_size],
                    pair[size],
                ),
                "n": len(pair),
            },
        )
    for size in sorted(relative_levels.columns):
        if size == reference_size:
            continue
        pair = relative_levels[[reference_size, size]].dropna()
        rows.append(
            {
                "statistic": "spearman_proxy_error",
                "household_size": size,
                "value": spearman_correlation(pair[reference_size], pair[size]),
                "n": len(pair),
            },
        )
        rows.append(
            {
                "statistic": "share_moving_at_least_two_deciles_proxy_error",
                "household_size": size,
                "value": share_moving_at_least_deciles(
                    pair[reference_size],
                    pair[size],
                ),
                "n": len(pair),
            },
        )
    return pd.DataFrame(rows)


def build_marginal_summary(
    marginal: pd.DataFrame,
    *,
    weights: pd.Series | None = None,
    weighting_scheme: str = "gemeinde_unweighted",
) -> pd.DataFrame:
    """Summarise `ΔK`, `ΔW`, `Q` and the per-capita caps by household size (§10.1).

    Args:
        marginal: The frame `build_marginal_amounts` returns.
        weights: Optional Gemeinde weights, indexed by `ags`.
        weighting_scheme: Name of the §8.2 scheme `weights` implements.

    Returns:
        One row per `(household_size, quantity)` with the columns
        `summarise_distribution` produces.

    """
    quantities = (
        "kdu_step",
        "wogg_step",
        "marginal_ratio",
        "kdu_per_capita",
        "wogg_per_capita",
    )
    rows = []
    for size, block in marginal.groupby("household_size"):
        weight = (
            None
            if weights is None
            else weights.reindex(block["ags"]).set_axis(block.index)
        )
        for quantity in quantities:
            summary = summarise_distribution(block[quantity], weight)
            if summary.empty:
                continue
            rows.append(
                pd.concat(
                    [
                        pd.Series(
                            {
                                "household_size": size,
                                "quantity": quantity,
                                "weighting_scheme": weighting_scheme,
                            },
                            dtype="object",
                        ),
                        summary,
                    ],
                ),
            )
    return pd.DataFrame(rows).reset_index(drop=True)


def build_marginal_ratio_status_counts(marginal: pd.DataFrame) -> pd.DataFrame:
    """Count why `Q(g,h)` is undefined, by household size.

    The `ΔW = 0` and `ΔW` missing rules are only defensible if the reader can
    see how often they bite, so the counts travel with the summary table.
    """
    counts = (
        marginal.value_counts(["household_size", "marginal_ratio_status"])
        .reset_index()
        .rename(columns={"count": "n"})
        .sort_values(["household_size", "marginal_ratio_status"])
    )
    counts["marginal_ratio_status"] = counts["marginal_ratio_status"].astype("string")
    return counts


def _log_relative_level(
    long: pd.DataFrame,
    *,
    kdu_column: str,
    wogg_column: str,
) -> pd.DataFrame:
    kdu = _as_float(long[kdu_column])
    wogg = _as_float(long[wogg_column])
    usable = (kdu > 0) & (wogg > 0)
    level = pd.Series(np.nan, index=long.index, dtype="float64")
    level.loc[usable] = np.log(kdu.loc[usable] / wogg.loc[usable])
    tidy = pd.DataFrame(
        {
            "ags": long["ags"].astype("string"),
            "household_size": long["household_size"].astype("int64"),
            "level": level,
        },
    )
    # pivot_table would aggregate; `ags x household_size` is already unique.
    wide = tidy.pivot(  # noqa: PD010
        index="ags",
        columns="household_size",
        values="level",
    )
    wide.columns.name = None
    return wide


def _classify_marginal_ratio(frame: pd.DataFrame) -> pd.Series:
    status = pd.Series(
        MarginalRatioStatus.DEFINED.value,
        index=frame.index,
        dtype="string",
    )
    smallest = frame["household_size"] == frame.groupby("ags")[
        "household_size"
    ].transform("min")
    status.loc[frame["kdu_step"].isna()] = MarginalRatioStatus.KDU_STEP_MISSING.value
    status.loc[frame["wogg_step"].isna()] = MarginalRatioStatus.WOGG_STEP_MISSING.value
    status.loc[frame["wogg_step"].abs() <= ZERO_STEP_TOLERANCE] = (
        MarginalRatioStatus.WOGG_STEP_ZERO.value
    )
    status.loc[smallest] = MarginalRatioStatus.NO_PREVIOUS_SIZE.value
    return status


def _safe_ratio(
    numerator: pd.Series,
    denominator: pd.Series,
    *,
    defined: pd.Series,
) -> pd.Series:
    ratio = pd.Series(np.nan, index=numerator.index, dtype="float64")
    ratio.loc[defined] = numerator.loc[defined] / denominator.loc[defined]
    return ratio


def _weighted_share(frame: pd.DataFrame, selector: pd.Series, total: float) -> float:
    return float(frame.loc[selector, "weight"].sum() / total)


def _as_float(column: pd.Series) -> pd.Series:
    return pd.to_numeric(column, errors="coerce").astype("float64")


def _fail_if_household_sizes_are_not_contiguous(long: pd.DataFrame) -> None:
    sizes = long.groupby("ags")["household_size"].agg(["min", "max", "nunique"])
    ragged = sizes.loc[sizes["max"] - sizes["min"] + 1 != sizes["nunique"]]
    if not ragged.empty:
        msg = (
            f"household sizes must be contiguous within each Gemeinde so that a "
            f"difference is a step of exactly one person; {len(ragged)} Gemeinden "
            f"are not, the first being {ragged.index[0]}"
        )
        raise ValueError(msg)
