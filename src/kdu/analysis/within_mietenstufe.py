"""P0.4 — how much local KdU variation survives the Wohngeld-Mietenstufe.

Under § 12 WoGG the Mietenstufe is assigned *kreisweise* for Gemeinden below
10,000 inhabitants and individually only for larger ones, so the statutory
classification is institutionally coarse by construction. This module measures
what that coarseness costs: the dispersion of the local KdU cap `K` and of the
ratio `K/W` that remains inside each Mietenstufe (§9.1), and the share of the
variation in `log K` a Mietenstufe classification can account for (§9.2).

The public surface is:

- `prepare_analysis_frame` — join the sample, the crosswalk and the benchmark
  into the one frame every routine below expects
- `dispersion_within_mietenstufe` and `stratified_dispersion` — the §9.1
  descriptives, by household size and Mietenstufe, overall and by stratum
- `fit_variance_decomposition` and `variance_decomposition_table` — the §9.2
  nested specifications
- `table_3` — the §19 Table 3 rows
- `robustness_table` — the §18 variants
- `interpretation` — the §21 four-part reading of the main figure

Three properties of the exercise govern every routine here.

**It is descriptive.** §9.2 states outright that this is a variance
decomposition and that p-values are not to be presented as a main result, so
nothing here reports significance and no output carries causal language (§20).

**Standard errors cluster on the Kreis.** Decision D1 makes the Kreis the unit
at which an independent KdU decision is taken — it is the Träger that publishes
the Richtlinie — so Gemeinden inside one Kreis are not independent draws.
Wherever a standard error appears it is clustered on `policy_region_id`, and
the classical one is reported beside it only to show how much the clustering
matters.

**The WoGG-linked Gemeinden must be shown both ways.** Decision D7: a Kreis
without a schlüssiges Konzept may adopt the § 12 WoGG table plus a 10 %
Sicherheitszuschlag, and its Gemeinden then have `K/W` pinned at exactly 1.10.
Their within-Mietenstufe variation in `K/W` is zero *by construction*, so they
mechanically deflate every dispersion statistic and inflate every `R²`.
`wogg_linked_flag` is the union of D7's two detectors (A8 item 2). It is
broader than, and not a superset of, the `exact_ratio` group sitting exactly at
1.100 (A22), so the residual variation inside it is small rather than
identically zero. Every
dispersion measure and every regression below is therefore produced twice, with
and without `wogg_linked_flag`, and the flagged group is also reported as its
own stratum so a reader can see the compression directly.
"""

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
import pandas as pd

from kdu.config import SMALL_GEMEINDE_THRESHOLD, WOGG_SAFETY_MARKUP

# Column holding the statutory Mietenstufe the analysis conditions on. D6 fixes
# the lookup key as `wogv_mietstufe`, the purely statutory value, which arrives
# in the benchmark as `wogg_rent_level`.
MIETENSTUFE_COLUMN = "wogg_rent_level"

# Column holding the local KdU cap `K`, the maximal recognised Bruttokaltmiete.
CAP_COLUMN = "kdu_bkc_cap"

# Column holding the ratio `K/W` against the primary Wohngeld benchmark (D6).
RATIO_COLUMN = "kdu_over_wogg"

# Column the Kreis clustering and weighting scheme 3 run on (D1).
CLUSTER_COLUMN = "policy_region_id"

# The two euro distances from the own-Mietenstufe median §9.1 point 5 asks for.
EURO_DEVIATION_THRESHOLDS: tuple[float, ...] = (50.0, 100.0)

# The five neue Länder plus Berlin, for the §18 east/west robustness split.
# Berlin is counted east, as is conventional for a whole-city unit.
EAST_GERMAN_STATES: frozenset[str] = frozenset(
    {
        "Berlin",
        "Brandenburg",
        "Mecklenburg-Vorpommern",
        "Sachsen",
        "Sachsen-Anhalt",
        "Thüringen",
    },
)


class Specification(StrEnum):
    """The three nested §9.2 specifications for `log K`."""

    MIETENSTUFE = "mietenstufe"
    """`log K_g = α + μ_Mietenstufe(g) + ε_g`, fitted per household size."""
    POOLED = "pooled"
    """`log K_gh = α_h + μ_Mietenstufe(g)×h + ε_gh`, all household sizes at once."""
    POOLED_WITH_STATE = "pooled_with_state"
    """The pooled specification plus `λ_Bundesland(g)`."""


class Sample(StrEnum):
    """The two samples every §9.1 and §9.2 output is produced on (D7)."""

    ALL = "all"
    """Every Gemeinde with a statutory Mietenstufe, WoGG-linked ones included."""
    EXCLUDING_WOGG_LINKED = "excluding_wogg_linked"
    """Only Gemeinden whose cap is not pinned to the WoGG table plus 10 %."""


class Stratum(StrEnum):
    """The §9.1 strata the descriptives are repeated on."""

    ALL = "all"
    """Every Gemeinde with a statutory Mietenstufe."""
    POPULATION_BELOW_THRESHOLD = "population_below_10000"
    """Gemeinden the WoGV classifies kreisweise, not individually (§ 12 WoGG)."""
    POPULATION_AT_OR_ABOVE_THRESHOLD = "population_10000_and_over"
    """Gemeinden the WoGV classifies individually."""
    KREISFREI = "kreisfrei"
    """Kreisfreie Städte, which are their own Träger."""
    KREISANGEHOERIG = "kreisangehoerig"
    """Gemeinden inside a Landkreis, sharing their Träger with their neighbours."""
    WOGG_LINKED = "wogg_linked"
    """Gemeinden whose cap is the WoGG table plus the 10 % Sicherheitszuschlag."""
    EXCLUDING_WOGG_LINKED = "excluding_wogg_linked"
    """The complement, where the cap rests on an independent local decision."""


class Weighting(StrEnum):
    """The §8.2 Berichtsgewichte, as far as this module can supply them."""

    GEMEINDE_UNWEIGHTED = "gemeinde_unweighted"
    """One Gemeinde, one weight."""
    GEMEINDE_POPULATION = "gemeinde_population"
    """Weighted by Gemeinde population."""
    POLICY_REGION_UNWEIGHTED = "policy_region_unweighted"
    """Each Kreis carries weight one, split evenly across its Gemeinden (D1)."""
    BEDARFSGEMEINSCHAFT = "bedarfsgemeinschaft"
    """Weighted by SGB II Bedarfsgemeinschaften; not available before P1."""


@dataclass(frozen=True)
class VarianceDecomposition:
    """One fitted §9.2 specification and everything §9.2 asks to be reported."""

    specification: Specification
    """Which of the three nested specifications was fitted."""
    sample: Sample
    """Whether the WoGG-linked Gemeinden are in or out (D7)."""
    weighting: Weighting
    """Which Berichtsgewicht the fit carries."""
    household_size: int | None
    """The `h` fitted, or `None` for the pooled specifications."""
    n_obs: int
    """Gemeinde-by-household-size rows entering the fit."""
    n_gemeinden: int
    """Distinct Gemeinden entering the fit."""
    n_policy_regions: int
    """Distinct Kreise, which are also the clusters (D1)."""
    n_parameters: int
    """Rank of the design matrix, used as the residual degrees of freedom."""
    r_squared: float
    """Share of the variation in `log K` the specification accounts for."""
    residual_sd: float
    """`sqrt(RSS / (n_obs − n_parameters))`, in log points."""
    residual_p10: float
    """10th percentile of the residuals, in log points."""
    residual_p90: float
    """90th percentile of the residuals, in log points."""
    mean_abs_residual: float
    """Mean absolute residual, in log points."""
    coefficients: pd.DataFrame = field(repr=False)
    """`name`, `estimate`, `classical_se`, `cluster_se`; clustered on the Kreis."""

    def as_row(self) -> dict[str, object]:
        """Render the reported quantities as one flat table row."""
        return {
            "specification": self.specification.value,
            "sample": self.sample.value,
            "weighting": self.weighting.value,
            "household_size": self.household_size,
            "n_obs": self.n_obs,
            "n_gemeinden": self.n_gemeinden,
            "n_policy_regions": self.n_policy_regions,
            "n_parameters": self.n_parameters,
            "r_squared": self.r_squared,
            "residual_sd": self.residual_sd,
            "residual_p10": self.residual_p10,
            "residual_p90": self.residual_p90,
            "mean_abs_residual": self.mean_abs_residual,
        }


def prepare_analysis_frame(
    sample: pd.DataFrame,
    crosswalk: pd.DataFrame,
) -> pd.DataFrame:
    """Join the main sample to the crosswalk and derive the analysis columns.

    The main sample already carries `kdu_bkc_cap`, the Wohngeld benchmark and
    `wogg_linked_flag`; the crosswalk adds the population, the size class and
    the kreisfrei indicator §9.1 splits on. Gemeinden without a statutory
    Mietenstufe are kept here and dropped only where a routine conditions on
    the Mietenstufe, so that the count lost stays visible (A2: 119 Gemeinden in
    27 Kreise are gemeindefreie Gebiete the Anlage zur WoGV does not list).

    Args:
        sample: `analysis_sample_main`, long in `ags × household_size`.
        crosswalk: `municipality_crosswalk`, one row per Gemeinde.

    Returns:
        The sample plus `population`, `is_small_gemeinde`, `is_kreisfrei`,
        `gemeinde_size_class`, `is_east_german`, `kdu_over_wogg` and
        `kdu_over_wogg_klima`.

    """
    added = [
        "ags",
        "population",
        "is_small_gemeinde",
        "is_kreisfrei",
        "gemeinde_size_class",
    ]
    frame = pd.merge(
        sample,
        crosswalk.loc[:, added],
        on="ags",
        how="left",
        validate="many_to_one",
    )
    frame["is_kreisfrei"] = frame["is_kreisfrei"].astype(bool)
    frame["is_east_german"] = frame["state_name"].isin(EAST_GERMAN_STATES)
    # `W` carries the BSG Sicherheitszuschlag (D15); the Klima row keeps the
    # bare table so it still isolates D6's Klimakomponente question.
    frame[RATIO_COLUMN] = _ratio(
        frame["kdu_bkc_cap"],
        frame["wogg_base_cap"] * WOGG_SAFETY_MARKUP,
    )
    frame["kdu_over_wogg_klima"] = _ratio(
        frame["kdu_bkc_cap"],
        frame["wogg_base_cap"] + frame["wogg_climate_component"],
    )
    return frame


def dispersion_within_mietenstufe(
    frame: pd.DataFrame,
    value_column: str,
    weight_column: str | None = None,
    deviation_thresholds: tuple[float, ...] = EURO_DEVIATION_THRESHOLDS,
) -> pd.DataFrame:
    """Describe the spread of `value_column` inside each Mietenstufe (§9.1).

    Args:
        frame: Prepared analysis frame; rows without a Mietenstufe are dropped.
        value_column: The measured column, `kdu_bkc_cap` or a `K/W` ratio.
        weight_column: Berichtsgewicht; `None` weights every Gemeinde equally.
        deviation_thresholds: Distances from the own-Mietenstufe median whose
            exceedance share is reported. Pass `()` for a ratio column, where a
            euro distance has no meaning.

    Returns:
        One row per household size and Mietenstufe with the count of Gemeinden
        and Kreise, the median, `P10`, `P90`, the `P90 − P10` spread, the
        standard deviation of the log value, and one exceedance share per
        threshold.

    """
    conditioned = frame.loc[frame[MIETENSTUFE_COLUMN].notna()]
    grouped = conditioned.groupby(
        ["household_size", MIETENSTUFE_COLUMN],
        dropna=True,
        observed=True,
    )
    rows = [
        _describe_cell(
            group,
            value_column=value_column,
            weight_column=weight_column,
            deviation_thresholds=deviation_thresholds,
        )
        | {"household_size": int(household_size), "mietenstufe": int(mietenstufe)}
        for (household_size, mietenstufe), group in grouped
    ]
    return (
        pd.DataFrame(rows)
        .sort_values(["household_size", "mietenstufe"])
        .reset_index(
            drop=True,
        )
    )


def stratified_dispersion(
    frame: pd.DataFrame,
    value_column: str,
    weight_column: str | None = None,
    deviation_thresholds: tuple[float, ...] = EURO_DEVIATION_THRESHOLDS,
) -> pd.DataFrame:
    """Repeat `dispersion_within_mietenstufe` on every §9.1 and D7 stratum.

    The four §9.1 splits ask what the institutional coarseness of § 12 WoGG
    does: below 10,000 inhabitants the Mietenstufe is a Kreis-level attribute,
    above it a Gemeinde-level one. The two D7 strata are added because the
    WoGG-linked Gemeinden have no within-Mietenstufe variation in `K/W` at all,
    and pooling them with the rest understates the dispersion of everyone else.

    Args:
        frame: Prepared analysis frame.
        value_column: The measured column.
        weight_column: Berichtsgewicht; `None` weights every Gemeinde equally.
        deviation_thresholds: As in `dispersion_within_mietenstufe`.

    Returns:
        The dispersion table with a leading `stratum` column. Strata with no
        Gemeinden are absent.

    """
    pieces = []
    for stratum in Stratum:
        subset = frame.loc[_stratum_mask(frame, stratum)]
        if subset.empty:
            continue
        described = dispersion_within_mietenstufe(
            subset,
            value_column=value_column,
            weight_column=weight_column,
            deviation_thresholds=deviation_thresholds,
        )
        described.insert(0, "stratum", stratum.value)
        pieces.append(described)
    return pd.concat(pieces, ignore_index=True)


def fit_variance_decomposition(
    frame: pd.DataFrame,
    specification: Specification,
    sample: Sample = Sample.ALL,
    weighting: Weighting = Weighting.GEMEINDE_UNWEIGHTED,
    weight_column: str | None = None,
    cap_column: str = CAP_COLUMN,
) -> VarianceDecomposition:
    """Fit one §9.2 specification of `log K` and report its dispersion.

    The three specifications are nested, so the comparison of their `R²` is the
    variance decomposition §9.2 asks for: what the Mietenstufe accounts for,
    what a household-size interaction adds, and what Bundesland effects absorb
    on top. The fit is by least squares on a dummy design; a rank-deficient
    design is resolved by the pseudo-inverse, and the rank rather than the
    column count supplies the residual degrees of freedom.

    Standard errors are clustered on `policy_region_id`, the Kreis. D1 makes
    the Kreis the entity that takes the KdU decision and publishes the
    Richtlinie, so Gemeinden within a Kreis are not independent observations
    and an unclustered standard error would overstate the precision by roughly
    the square root of the average Kreis size. The classical standard error is
    carried alongside only to make that gap visible. Neither is a hypothesis
    test: §9.2 is explicit that p-values are not a result here.

    Args:
        frame: Prepared analysis frame, already restricted to the intended
            sample and household size.
        specification: Which of the three nested designs to fit.
        sample: Label recording whether WoGG-linked Gemeinden are included.
        weighting: Label recording the Berichtsgewicht.
        weight_column: Column of weights; `None` weights every row equally.
        cap_column: The euro cap whose log is the outcome.

    Returns:
        The fitted decomposition.

    Raises:
        ValueError: If no row survives the Mietenstufe and positivity filters.

    """
    usable = frame.loc[frame[MIETENSTUFE_COLUMN].notna() & (frame[cap_column] > 0)]
    if usable.empty:
        raise ValueError(
            "No observation has both a statutory Mietenstufe and a positive cap; "
            "check that the frame was prepared with `prepare_analysis_frame`.",
        )
    outcome = np.log(usable[cap_column].to_numpy(dtype=float))
    design = _design_matrix(usable, specification)
    weights = _normalised_weights(usable, weight_column)
    clusters = usable[CLUSTER_COLUMN].to_numpy()
    estimates, classical_se, cluster_se, residuals, rank = _least_squares(
        design.to_numpy(dtype=float),
        outcome,
        weights,
        clusters,
    )
    total = _weighted_sum_of_squares(outcome, weights)
    residual = float(np.sum(weights * residuals**2))
    household_sizes = usable["household_size"].unique()
    return VarianceDecomposition(
        specification=specification,
        sample=sample,
        weighting=weighting,
        household_size=(int(household_sizes[0]) if len(household_sizes) == 1 else None),
        n_obs=len(usable),
        n_gemeinden=int(usable["ags"].nunique()),
        n_policy_regions=int(usable[CLUSTER_COLUMN].nunique()),
        n_parameters=rank,
        r_squared=1.0 - residual / total if total > 0 else float("nan"),
        residual_sd=float(np.sqrt(residual / max(len(usable) - rank, 1))),
        residual_p10=weighted_quantile(residuals, weights, 0.10),
        residual_p90=weighted_quantile(residuals, weights, 0.90),
        mean_abs_residual=float(
            np.sum(weights * np.abs(residuals)) / np.sum(weights),
        ),
        coefficients=pd.DataFrame(
            {
                "name": design.columns,
                "estimate": estimates,
                "classical_se": classical_se,
                "cluster_se": cluster_se,
            },
        ),
    )


def variance_decomposition_table(
    frame: pd.DataFrame,
    weighting: Weighting = Weighting.GEMEINDE_UNWEIGHTED,
    weight_column: str | None = None,
) -> pd.DataFrame:
    """Fit all three §9.2 specifications, with and without the WoGG-linked group.

    Args:
        frame: Prepared analysis frame.
        weighting: Label recording the Berichtsgewicht.
        weight_column: Column of weights; `None` weights every row equally.

    Returns:
        One row per specification, sample and household size. The per-household
        specification contributes one row per `h`; the two pooled ones
        contribute a single row each, with `household_size` left empty.

    """
    rows = []
    for sample in Sample:
        subset = frame.loc[_sample_mask(frame, sample)]
        for household_size in sorted(subset["household_size"].unique()):
            fit = fit_variance_decomposition(
                subset.loc[subset["household_size"] == household_size],
                specification=Specification.MIETENSTUFE,
                sample=sample,
                weighting=weighting,
                weight_column=weight_column,
            )
            rows.append(fit.as_row())
        for specification in (Specification.POOLED, Specification.POOLED_WITH_STATE):
            fit = fit_variance_decomposition(
                subset,
                specification=specification,
                sample=sample,
                weighting=weighting,
                weight_column=weight_column,
            )
            rows.append(fit.as_row())
    return pd.DataFrame(rows)


def table_3(frame: pd.DataFrame, weight_column: str | None = None) -> pd.DataFrame:
    """Build §19 Table 3, the within-Mietenstufe heterogeneity table.

    Args:
        frame: Prepared analysis frame.
        weight_column: Berichtsgewicht; `None` weights every Gemeinde equally.

    Returns:
        One row per household size and sample with `R²`, the residual standard
        deviation, the typical within-Mietenstufe `P90 − P10` spread of the cap
        in euro and of `K/W`, and the count of Gemeinden and Kreise.

    """
    rows = []
    for sample in Sample:
        subset = frame.loc[_sample_mask(frame, sample)]
        cap_spread = _mean_spread_by_household_size(
            subset,
            CAP_COLUMN,
            weight_column,
        )
        ratio_spread = _mean_spread_by_household_size(
            subset,
            RATIO_COLUMN,
            weight_column,
        )
        for household_size in sorted(subset["household_size"].unique()):
            fit = fit_variance_decomposition(
                subset.loc[subset["household_size"] == household_size],
                specification=Specification.MIETENSTUFE,
                sample=sample,
                weight_column=weight_column,
            )
            rows.append(
                {
                    "household_size": int(household_size),
                    "sample": sample.value,
                    "r_squared": fit.r_squared,
                    "residual_sd": fit.residual_sd,
                    "cap_p90_minus_p10_eur": cap_spread.get(household_size),
                    "ratio_p90_minus_p10": ratio_spread.get(household_size),
                    "n_gemeinden": fit.n_gemeinden,
                    "n_policy_regions": fit.n_policy_regions,
                },
            )
    return (
        pd.DataFrame(rows)
        .sort_values(["sample", "household_size"])
        .reset_index(
            drop=True,
        )
    )


def robustness_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Re-run the headline statistics under every §18 variant in scope.

    The variants covered are the two Wohngeld benchmarks (D6), the three
    quality-tier cuts (§6.4 with A8 item 3), all four Berichtsgewichte, the six
    region types, and the two spatial units. Each is reported with and without
    the WoGG-linked Gemeinden, because D7 binds on every one of them.

    Args:
        frame: Prepared analysis frame.

    Returns:
        One row per variant and sample, carrying the pooled `R²`, the residual
        standard deviation, the typical within-Mietenstufe `K/W` spread, and
        the counts. A variant whose input does not exist yet — the
        Bedarfsgemeinschaft weighting, which P1 supplies — carries empty
        statistics and a `note` saying so.

    """
    rows = []
    for group, variant, subset, ratio_column, weight_column in _robustness_variants(
        frame,
    ):
        for sample in Sample:
            selected = subset.loc[_sample_mask(subset, sample)]
            rows.append(
                _robustness_row(
                    group=group,
                    variant=variant,
                    sample=sample,
                    subset=selected,
                    ratio_column=ratio_column,
                    weight_column=weight_column,
                ),
            )
    rows.extend(
        {
            "variant_group": "weighting",
            "variant": Weighting.BEDARFSGEMEINSCHAFT.value,
            "sample": sample.value,
            "note": (
                "Bedarfsgemeinschaft counts are a P1 deliverable and do not "
                "exist at P0.4, so this weighting cannot be evaluated yet."
            ),
        }
        for sample in Sample
    )
    return pd.DataFrame(rows)


def interpretation(
    table: pd.DataFrame,
    cap_dispersion: pd.DataFrame,
    ratio_dispersion: pd.DataFrame,
    decomposition: pd.DataFrame,
) -> str:
    """Write the §21 four-part reading of the main figure from computed numbers.

    Args:
        table: The output of `table_3`.
        cap_dispersion: `stratified_dispersion` for the euro cap `K`.
        ratio_dispersion: `stratified_dispersion` for the ratio `K/W`.
        decomposition: The output of `variance_decomposition_table`.

    Returns:
        A markdown document with no placeholders left in it.

    """
    return _INTERPRETATION_TEMPLATE.format(
        **_interpretation_facts(
            table,
            cap_dispersion,
            ratio_dispersion,
            decomposition,
        )
    )


def weighted_quantile(
    values: np.ndarray,
    weights: np.ndarray,
    quantile: float,
) -> float:
    """Return the weight-proportional linear-interpolation quantile.

    Plotting positions run from zero at the smallest observation to one at the
    largest in proportion to the cumulative weight, so that equal weights
    reproduce the ordinary linear-interpolation quantile exactly.

    Args:
        values: Observations; must contain at least one finite entry.
        weights: Non-negative weights of the same length.
        quantile: Probability in `[0, 1]`.

    Returns:
        The interpolated quantile, or `nan` if nothing is usable.

    """
    finite = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not finite.any():
        return float("nan")
    ordered = np.argsort(values[finite], kind="stable")
    sorted_values = values[finite][ordered]
    sorted_weights = weights[finite][ordered]
    positions = np.cumsum(sorted_weights) - sorted_weights
    span = positions[-1]
    if span <= 0:
        return float(sorted_values[0])
    return float(np.interp(quantile, positions / span, sorted_values))


def weighted_standard_deviation(values: np.ndarray, weights: np.ndarray) -> float:
    """Return the frequency-weighted standard deviation, `nan` below two units."""
    finite = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if finite.sum() < 2:  # noqa: PLR2004
        return float("nan")
    used_values, used_weights = values[finite], weights[finite]
    total = used_weights.sum()
    if total <= 1:
        return float("nan")
    mean = float(np.sum(used_weights * used_values) / total)
    variance = float(np.sum(used_weights * (used_values - mean) ** 2) / (total - 1))
    return float(np.sqrt(variance))


def _describe_cell(
    group: pd.DataFrame,
    value_column: str,
    weight_column: str | None,
    deviation_thresholds: tuple[float, ...],
) -> dict[str, object]:
    values = group[value_column].to_numpy(dtype=float)
    weights = (
        np.ones(len(group))
        if weight_column is None
        else group[weight_column].to_numpy(dtype=float)
    )
    median = weighted_quantile(values, weights, 0.5)
    p10 = weighted_quantile(values, weights, 0.10)
    p90 = weighted_quantile(values, weights, 0.90)
    with np.errstate(divide="ignore", invalid="ignore"):
        logs = np.log(np.where(values > 0, values, np.nan))
    described: dict[str, object] = {
        "n_gemeinden": int(group["ags"].nunique()),
        "n_policy_regions": int(group[CLUSTER_COLUMN].nunique()),
        "median": median,
        "mean": float(np.sum(weights * values) / np.sum(weights)),
        "p10": p10,
        "p90": p90,
        "p90_minus_p10": p90 - p10,
        "sd_log": weighted_standard_deviation(logs, weights),
    }
    deviation = np.abs(values - median)
    for threshold in deviation_thresholds:
        share = float(
            np.sum(weights * (deviation > threshold)) / np.sum(weights),
        )
        described[f"share_abs_dev_above_{int(threshold)}_eur"] = share
    return described


def _stratum_mask(frame: pd.DataFrame, stratum: Stratum) -> pd.Series:
    if stratum is Stratum.ALL:
        return pd.Series(data=True, index=frame.index)
    if stratum is Stratum.POPULATION_BELOW_THRESHOLD:
        return frame["is_small_gemeinde"].astype(bool)
    if stratum is Stratum.POPULATION_AT_OR_ABOVE_THRESHOLD:
        return ~frame["is_small_gemeinde"].astype(bool)
    if stratum is Stratum.KREISFREI:
        return frame["is_kreisfrei"].astype(bool)
    if stratum is Stratum.KREISANGEHOERIG:
        return ~frame["is_kreisfrei"].astype(bool)
    if stratum is Stratum.WOGG_LINKED:
        return frame["wogg_linked_flag"].astype(bool)
    return ~frame["wogg_linked_flag"].astype(bool)


def _sample_mask(frame: pd.DataFrame, sample: Sample) -> pd.Series:
    if sample is Sample.ALL:
        return pd.Series(data=True, index=frame.index)
    return ~frame["wogg_linked_flag"].astype(bool)


def _design_matrix(frame: pd.DataFrame, specification: Specification) -> pd.DataFrame:
    mietenstufe = frame[MIETENSTUFE_COLUMN].astype("Int64").astype(str)
    household_size = frame["household_size"].astype(int).astype(str)
    factors: list[pd.Series] = []
    if specification is Specification.MIETENSTUFE:
        factors.append(mietenstufe.rename("mietenstufe"))
    else:
        factors.append(household_size.rename("household_size"))
        factors.append(
            (mietenstufe + "_x_" + household_size).rename("mietenstufe_x_h"),
        )
        if specification is Specification.POOLED_WITH_STATE:
            factors.append(frame["state_name"].astype(str).rename("bundesland"))
    columns = {"intercept": np.ones(len(frame))}
    for factor in factors:
        dummies = pd.get_dummies(factor, prefix=factor.name, drop_first=True)
        for name in dummies.columns:
            columns[str(name)] = dummies[name].to_numpy(dtype=float)
    return pd.DataFrame(columns, index=frame.index)


def _least_squares(
    design: np.ndarray,
    outcome: np.ndarray,
    weights: np.ndarray,
    clusters: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
    """Fit weighted least squares and return classical and Kreis-clustered errors."""
    root = np.sqrt(weights)
    weighted_design = design * root[:, None]
    weighted_outcome = outcome * root
    gram = weighted_design.T @ weighted_design
    gram_inverse = np.linalg.pinv(gram)
    estimates = gram_inverse @ (weighted_design.T @ weighted_outcome)
    residuals = outcome - design @ estimates
    rank = int(np.linalg.matrix_rank(weighted_design))
    n_obs = len(outcome)
    degrees_of_freedom = max(n_obs - rank, 1)
    sigma_squared = float(np.sum(weights * residuals**2)) / degrees_of_freedom
    classical = _standard_errors(sigma_squared * gram_inverse)
    scores = weighted_design * (root * residuals)[:, None]
    meat = np.zeros_like(gram)
    _, cluster_index = np.unique(clusters, return_inverse=True)
    n_clusters = int(cluster_index.max()) + 1
    for index in range(n_clusters):
        cluster_score = scores[cluster_index == index].sum(axis=0)
        meat += np.outer(cluster_score, cluster_score)
    correction = n_clusters / max(n_clusters - 1, 1) * (n_obs - 1) / degrees_of_freedom
    clustered = _standard_errors(
        correction * gram_inverse @ meat @ gram_inverse,
    )
    return estimates, classical, clustered, residuals, rank


def _normalised_weights(frame: pd.DataFrame, weight_column: str | None) -> np.ndarray:
    """Scale the Berichtsgewicht to mean one, so residual dispersion stays in log points.

    Weighted least squares is invariant to the scale of the weights, but
    `RSS / (n − k)` is not: population weights would otherwise report a
    residual standard deviation inflated by the average Gemeinde population.
    """
    if weight_column is None:
        return np.ones(len(frame))
    raw = frame[weight_column].to_numpy(dtype=float)
    usable = np.where(np.isfinite(raw) & (raw > 0), raw, 0.0)
    total = usable.sum()
    if total <= 0:
        return np.ones(len(frame))
    return usable * (len(frame) / total)


def _standard_errors(covariance: np.ndarray) -> np.ndarray:
    return np.sqrt(np.clip(np.diag(covariance), 0.0, None))


def _weighted_sum_of_squares(values: np.ndarray, weights: np.ndarray) -> float:
    mean = float(np.sum(weights * values) / np.sum(weights))
    return float(np.sum(weights * (values - mean) ** 2))


def _ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    left = pd.to_numeric(numerator, errors="coerce").astype(float)
    right = pd.to_numeric(denominator, errors="coerce").astype(float)
    return left.where(right > 0) / right.where(right > 0)


def _mean_spread_by_household_size(
    frame: pd.DataFrame,
    value_column: str,
    weight_column: str | None,
) -> dict[int, float]:
    """Average the within-Mietenstufe `P90 − P10` across Mietenstufen, by cell size."""
    dispersion = dispersion_within_mietenstufe(
        frame,
        value_column=value_column,
        weight_column=weight_column,
        deviation_thresholds=(),
    )
    if dispersion.empty:
        return {}
    weighted = dispersion.assign(
        product=dispersion["p90_minus_p10"] * dispersion["n_gemeinden"],
    )
    totals = weighted.groupby("household_size")[["product", "n_gemeinden"]].sum()
    return (totals["product"] / totals["n_gemeinden"]).to_dict()


def _robustness_variants(
    frame: pd.DataFrame,
) -> list[tuple[str, str, pd.DataFrame, str, str | None]]:
    """Enumerate the §18 variants as `(group, variant, subset, ratio, weight)`."""
    tiers = {
        "quality_tier_a_only": frame["quality_tier"].astype(str).isin(["A"]),
        "quality_tier_a_and_b": frame["quality_tier"].astype(str).isin(["A", "B"]),
        "quality_tier_all": pd.Series(data=True, index=frame.index),
    }
    regions = {
        "kreisfrei": frame["is_kreisfrei"].astype(bool),
        "kreisangehoerig": ~frame["is_kreisfrei"].astype(bool),
        f"population_below_{SMALL_GEMEINDE_THRESHOLD}": frame[
            "is_small_gemeinde"
        ].astype(bool),
        f"population_{SMALL_GEMEINDE_THRESHOLD}_and_over": ~frame[
            "is_small_gemeinde"
        ].astype(bool),
        "east_german_states": frame["is_east_german"].astype(bool),
        "west_german_states": ~frame["is_east_german"].astype(bool),
    }
    variants: list[tuple[str, str, pd.DataFrame, str, str | None]] = [
        ("wohngeld_benchmark", "base_hoechstbetrag", frame, RATIO_COLUMN, None),
        (
            "wohngeld_benchmark",
            "base_plus_klimakomponente",
            frame,
            "kdu_over_wogg_klima",
            None,
        ),
        ("weighting", Weighting.GEMEINDE_UNWEIGHTED.value, frame, RATIO_COLUMN, None),
        (
            "weighting",
            Weighting.GEMEINDE_POPULATION.value,
            frame,
            RATIO_COLUMN,
            "population",
        ),
        (
            "weighting",
            Weighting.POLICY_REGION_UNWEIGHTED.value,
            _with_policy_region_weight(frame),
            RATIO_COLUMN,
            "policy_region_weight",
        ),
        ("spatial_unit", "gemeinde", frame, RATIO_COLUMN, None),
        (
            "spatial_unit",
            "policy_region",
            collapse_to_policy_region(frame),
            RATIO_COLUMN,
            None,
        ),
    ]
    variants.extend(
        ("data_quality", name, frame.loc[mask], RATIO_COLUMN, None)
        for name, mask in tiers.items()
    )
    variants.extend(
        ("region_type", name, frame.loc[mask], RATIO_COLUMN, None)
        for name, mask in regions.items()
    )
    return variants


def _robustness_row(
    group: str,
    variant: str,
    sample: Sample,
    subset: pd.DataFrame,
    ratio_column: str,
    weight_column: str | None,
) -> dict[str, object]:
    usable = subset.loc[subset[MIETENSTUFE_COLUMN].notna()]
    if usable.empty:
        return {
            "variant_group": group,
            "variant": variant,
            "sample": sample.value,
            "note": "No Gemeinde with a statutory Mietenstufe in this variant.",
        }
    fit = fit_variance_decomposition(
        usable,
        specification=Specification.POOLED,
        sample=sample,
        weight_column=weight_column,
    )
    spread = _mean_spread_by_household_size(usable, ratio_column, weight_column)
    return {
        "variant_group": group,
        "variant": variant,
        "sample": sample.value,
        "r_squared": fit.r_squared,
        "residual_sd": fit.residual_sd,
        "residual_p10": fit.residual_p10,
        "residual_p90": fit.residual_p90,
        "mean_abs_residual": fit.mean_abs_residual,
        "ratio_p90_minus_p10": (
            float(np.mean(list(spread.values()))) if spread else float("nan")
        ),
        "n_gemeinden": fit.n_gemeinden,
        "n_policy_regions": fit.n_policy_regions,
        "note": "",
    }


def _with_policy_region_weight(frame: pd.DataFrame) -> pd.DataFrame:
    """Give every Kreis weight one, split evenly across its Gemeinden (D1)."""
    sizes = frame.groupby([CLUSTER_COLUMN, "household_size"])["ags"].transform("size")
    return frame.assign(policy_region_weight=1.0 / sizes)


def collapse_to_policy_region(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate the Gemeinde frame to one row per Kreis and household size.

    The §18 spatial-unit robustness asks whether the picture survives at the
    Kreis level. Caps and benchmarks are averaged over the Kreis weighted by
    population, and the Mietenstufe is the population-modal one, because D1's
    Kreis can contain several Vergleichsräume and several Mietenstufen.

    Args:
        frame: Prepared analysis frame at Gemeinde level.

    Returns:
        A frame with the same analysis columns, keyed on Kreis and household
        size, in which `ags` is the Kreis key so downstream counts stay honest.

    """
    conditioned = frame.loc[frame[MIETENSTUFE_COLUMN].notna()].copy()
    conditioned["weight"] = conditioned["population"].clip(lower=1)
    grouped = conditioned.groupby([CLUSTER_COLUMN, "household_size"], observed=True)
    collapsed = grouped.apply(_collapse_one_region, include_groups=False)
    return (
        collapsed.reset_index()
        .rename(columns={CLUSTER_COLUMN: "ags"})
        .assign(
            **{CLUSTER_COLUMN: lambda out: out["ags"]},
        )
    )


def _collapse_one_region(group: pd.DataFrame) -> pd.Series:
    weight = group["weight"].to_numpy(dtype=float)
    modal = group.groupby(MIETENSTUFE_COLUMN, observed=True)["weight"].sum().idxmax()
    cap = float(np.sum(weight * group[CAP_COLUMN].to_numpy(dtype=float)) / weight.sum())
    ratio = _weighted_mean(group[RATIO_COLUMN], weight)
    return pd.Series(
        {
            MIETENSTUFE_COLUMN: modal,
            CAP_COLUMN: cap,
            RATIO_COLUMN: ratio,
            "kdu_over_wogg_klima": _weighted_mean(
                group["kdu_over_wogg_klima"],
                weight,
            ),
            "state_name": group["state_name"].iloc[0],
            "is_kreisfrei": bool(group["is_kreisfrei"].iloc[0]),
            "is_small_gemeinde": bool(group["is_small_gemeinde"].all()),
            "is_east_german": bool(group["is_east_german"].iloc[0]),
            "wogg_linked_flag": bool(group["wogg_linked_flag"].all()),
            "quality_tier": group["quality_tier"].mode().iloc[0],
            "population": float(weight.sum()),
        },
    )


def _weighted_mean(values: pd.Series, weights: np.ndarray) -> float:
    numeric = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    finite = np.isfinite(numeric)
    if not finite.any():
        return float("nan")
    return float(
        np.sum(weights[finite] * numeric[finite]) / np.sum(weights[finite]),
    )


_INTERPRETATION_TEMPLATE = """# P0.4 — heterogeneity within the Wohngeld-Mietenstufen

## What is measured?

For every Gemeinde `g` and household size `h`, `K` is the maximal recognised
Bruttokaltmiete the responsible Kreis publishes, and `W` is the § 12 WoGG
Höchstbetrag for the Gemeinde's statutory Mietenstufe. This module measures how
much of the variation in `K` survives once Gemeinden are sorted into the seven
Mietenstufen: the spread of `K` and of `K/W` inside each Mietenstufe, and the
share of the variation in `log K` a Mietenstufe classification accounts for.
The sample is {n_gemeinden:,} Gemeinden in {n_policy_regions:,} Kreise, balanced
over `h = 1…4`.

## What is the central quantitative finding?

A Mietenstufe classification accounts for {r2_h1:.1%} of the variation in
`log K` for single-person households and {r2_h4:.1%} for four-person
households, leaving a residual standard deviation of {sd_h1:.3f} and
{sd_h4:.3f} log points. Inside a single Mietenstufe the typical `P90 − P10`
spread of the single-person cap is {spread_h1:.0f} €, and {share50_h1:.1%} of
Gemeinden sit more than 50 € — {share100_h1:.1%} more than 100 € — from the
median of their own Mietenstufe.

Excluding the Gemeinden whose Kreis adopted the § 12 WoGG table plus the 10 %
Sicherheitszuschlag rather than writing a schlüssiges Konzept, the same figures
are {r2_h1_excl:.1%} and {r2_h4_excl:.1%} explained, with residual standard
deviations of {sd_h1_excl:.3f} and {sd_h4_excl:.3f}, and the shares beyond 50 €
and 100 € rise to {share50_h1_excl:.1%} and {share100_h1_excl:.1%}. Those
{share_flagged:.1%} of Gemeinden carry a `K/W` pinned at or immediately beside
1.10 by construction, so they hold almost no within-Mietenstufe variation in
`K/W`: the within-Mietenstufe standard deviation of `log K/W` is
{sd_ratio_flagged:.4f} in that group against {sd_ratio_unflagged:.4f} outside
it, a factor of roughly {sd_ratio_factor:.0f}. Including them therefore
compresses every dispersion measure and raises every `R²`, which is why both
readings are reported side by side throughout. The flag is the union of the two
D7 detectors, so it is wider than the group at exactly 1.100 and the residual
variation inside it is small rather than identically zero.

Adding Bundesland fixed effects to the pooled specification moves `R²` from
{r2_pooled:.1%} to {r2_pooled_state:.1%}, so state-level differences absorb a
further {r2_state_gain:.1f} percentage points of the variation in `log K`. The
residual standard deviation falls from {sd_pooled:.3f} to
{sd_pooled_state:.3f} log points.

## Why does this matter for tax-transfer simulation?

A model that assigns housing needs by Mietenstufe assigns the same
administrative Bruttokaltbedarf to Gemeinden whose published caps differ by the
amounts above. Within one Mietenstufe the residual spread is of the same order
as the differences *between* adjacent Mietenstufen, so the classification
captures the local heterogeneity relevant to an SGB II or SGB XII simulation
only incompletely. Where the residual is large, the simulated Bedarf, the
simulated Anspruch and the simulated exit threshold inherit the whole
mismeasurement.

## Which interpretation is not admissible?

A high cap is not evidence of a more generous Kreis, and a low one is not
evidence of a restrictive one: the cap is endogenous to the local housing
market, to the administrative procedure and to how the Kreis draws its
Vergleichsräume. Nothing here identifies a causal effect, and the standard
errors — clustered on the Kreis, because D1 makes the Kreis the unit at which
the decision is taken — are reported as a description of precision, not as a
test. Where `K/W` sits exactly at 1.10 the ratio is a definitional identity
following BSG case law, not an empirical regularity; the `wogg_linked_flag`
split used here is broader than, and not a superset of, that group (A22). All figures are
conditional on the cap being in force, which under § 22 Abs. 1 S. 2–3 SGB II it
is not during the first twelve months of the Karenzzeit.
"""


def _interpretation_facts(
    table: pd.DataFrame,
    cap_dispersion: pd.DataFrame,
    dispersion: pd.DataFrame,
    decomposition: pd.DataFrame,
) -> dict[str, object]:
    def cell(sample: Sample, household_size: int, column: str) -> float:
        selected = table.loc[
            (table["sample"] == sample.value)
            & (table["household_size"] == household_size),
            column,
        ]
        return float(selected.to_numpy()[0])

    def pooled(specification: Specification, column: str) -> float:
        selected = decomposition.loc[
            (decomposition["specification"] == specification.value)
            & (decomposition["sample"] == Sample.ALL.value),
            column,
        ]
        return float(selected.to_numpy()[0])

    def ratio_sd(stratum: Stratum) -> float:
        selected = dispersion.loc[
            (dispersion["stratum"] == stratum.value)
            & (dispersion["household_size"] == 1),
            ["sd_log", "n_gemeinden"],
        ].dropna()
        if selected.empty:
            return float("nan")
        return float(
            np.average(selected["sd_log"], weights=selected["n_gemeinden"]),
        )

    all_h1 = dispersion.loc[
        (dispersion["stratum"] == Stratum.ALL.value)
        & (dispersion["household_size"] == 1)
    ]
    flagged_share = (
        all_h1["n_gemeinden"].sum()
        - dispersion.loc[
            (dispersion["stratum"] == Stratum.EXCLUDING_WOGG_LINKED.value)
            & (dispersion["household_size"] == 1),
            "n_gemeinden",
        ].sum()
    ) / all_h1["n_gemeinden"].sum()
    sd_ratio_flagged = ratio_sd(Stratum.WOGG_LINKED)
    sd_ratio_unflagged = ratio_sd(Stratum.EXCLUDING_WOGG_LINKED)
    r2_pooled = pooled(Specification.POOLED, "r_squared")
    r2_pooled_state = pooled(Specification.POOLED_WITH_STATE, "r_squared")
    return {
        "n_gemeinden": int(cell(Sample.ALL, 1, "n_gemeinden")),
        "n_policy_regions": int(cell(Sample.ALL, 1, "n_policy_regions")),
        "r2_h1": cell(Sample.ALL, 1, "r_squared"),
        "r2_h4": cell(Sample.ALL, 4, "r_squared"),
        "sd_h1": cell(Sample.ALL, 1, "residual_sd"),
        "sd_h4": cell(Sample.ALL, 4, "residual_sd"),
        "spread_h1": cell(Sample.ALL, 1, "cap_p90_minus_p10_eur"),
        "share50_h1": _share(cap_dispersion, 50, Stratum.ALL),
        "share100_h1": _share(cap_dispersion, 100, Stratum.ALL),
        "share50_h1_excl": _share(
            cap_dispersion,
            50,
            Stratum.EXCLUDING_WOGG_LINKED,
        ),
        "share100_h1_excl": _share(
            cap_dispersion,
            100,
            Stratum.EXCLUDING_WOGG_LINKED,
        ),
        "r2_h1_excl": cell(Sample.EXCLUDING_WOGG_LINKED, 1, "r_squared"),
        "r2_h4_excl": cell(Sample.EXCLUDING_WOGG_LINKED, 4, "r_squared"),
        "sd_h1_excl": cell(Sample.EXCLUDING_WOGG_LINKED, 1, "residual_sd"),
        "sd_h4_excl": cell(Sample.EXCLUDING_WOGG_LINKED, 4, "residual_sd"),
        "share_flagged": float(flagged_share),
        "sd_ratio_flagged": sd_ratio_flagged,
        "sd_ratio_unflagged": sd_ratio_unflagged,
        "sd_ratio_factor": sd_ratio_unflagged / sd_ratio_flagged,
        "r2_pooled": r2_pooled,
        "r2_pooled_state": r2_pooled_state,
        "r2_state_gain": 100.0 * (r2_pooled_state - r2_pooled),
        "sd_pooled": pooled(Specification.POOLED, "residual_sd"),
        "sd_pooled_state": pooled(Specification.POOLED_WITH_STATE, "residual_sd"),
    }


def _share(dispersion: pd.DataFrame, threshold: int, stratum: Stratum) -> float:
    """Average one exceedance share over the Mietenstufen of `h = 1`."""
    column = f"share_abs_dev_above_{threshold}_eur"
    selected = dispersion.loc[
        (dispersion["stratum"] == stratum.value) & (dispersion["household_size"] == 1),
        [column, "n_gemeinden"],
    ].dropna()
    if selected.empty:
        return float("nan")
    return float(np.average(selected[column], weights=selected["n_gemeinden"]))
