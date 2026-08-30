"""The §8 proxy error: how far the Wohngeld Höchstbetrag misses the local KdU cap.

`K` is the local maximum recognisable Bruttokaltmiete, `W` the Wohngeld
Höchstbetrag a tax-transfer model would substitute for it. §8.1 defines four
measures of the gap, §8.2 four weighting schemes, §8.3 the descriptive
breakdowns, and §8.4 the rent grid on which the gap becomes benefit-relevant.

Two facts govern every number this module produces:

- **A2.** 119 of the 9,442 main-sample Gemeinden have no statutory Mietenstufe,
  so no Wohngeld benchmark exists for them under the statute. Every K−W
  comparison therefore runs on 9,323 Gemeinden. `comparable` marks the rows.
- **D7.** A Kreis without a schlüssiges Konzept may set `K = 1.10 × W` under BSG
  case law. Where it does, the proxy error is a definitional identity, not an
  empirical finding. `wogg_linked_flag` and `at_safety_markup` mark those rows,
  and every headline is reported with and without them.

Everything here is a pure function of frames handed in; the pytask wrappers in
{mod}`kdu.analysis.task_proxy_error` own the I/O.
"""

from collections.abc import Iterator, Mapping, Sequence
from enum import StrEnum
from typing import cast

import numpy as np
import pandas as pd

from kdu.config import WOGG_SAFETY_MARKUP, WeightingScheme


class BenchmarkVariant(StrEnum):
    """Which Wohngeld quantity plays the role of `W` (D6)."""

    BASE = "base"
    """`wogg_base_cap` alone: the primary benchmark of every headline number."""
    BASE_PLUS_CLIMATE = "base_plus_climate"
    """Base Höchstbetrag plus Klimakomponente: the mandated §18 robustness."""
    BASE_PLUS_SAFETY_MARKUP = "base_plus_safety_markup"
    """Base Höchstbetrag times the 10 % Sicherheitszuschlag: the primary benchmark."""


# The benchmark every headline number, map and Table 2 row is read against (D15).
#
# A model with no local KdU parameter is, by construction, in the situation
# § 22 SGB II case law addresses: no schlüssiges Konzept is available. The
# fallback the BSG prescribes there is the § 12 WoGG table plus a 10 %
# Sicherheitszuschlag, so that product — not the bare table — is the value a
# model should substitute, and the standard the proxy error is measured against.
PRIMARY_BENCHMARK = BenchmarkVariant.BASE_PLUS_SAFETY_MARKUP


class LinkageGroup(StrEnum):
    """How a table row treats the WoGG-linked Gemeinden (D7)."""

    ALL = "all"
    """Pooled: never to be read as an empirical regularity."""
    EXCLUDING_WOGG_LINKED = "excluding_wogg_linked"
    """`wogg_linked_flag` removed — the union of D7's two detectors."""
    WOGG_LINKED_ONLY = "wogg_linked_only"
    """Only the flagged Gemeinden, where the gap is definitional."""
    EXCLUDING_AT_SAFETY_MARKUP = "excluding_at_safety_markup"
    """Only Gemeinden whose `K/W` is away from 1.10 at this household size."""
    AT_SAFETY_MARKUP_ONLY = "at_safety_markup_only"
    """Only Gemeinden sitting exactly on the 10 % Sicherheitszuschlag."""


# The five §8.4 rent points, in the order the figure walks them.
RENT_POINT_LABELS: tuple[str, ...] = (
    "0.8 × min(K, W)",
    "min(K, W)",
    "0.5 × (K + W)",
    "max(K, W)",
    "1.2 × max(K, W)",
)

# Tolerance on `K/W` that isolates the Gemeinden sitting *exactly* on the 10 %
# Sicherheitszuschlag. Decision-log A8 records this value as the one that
# reproduces D7's anchor of 1,203 Gemeinden at h=1. It is deliberately tighter
# than `config.WOGG_SAFETY_MARKUP_TOLERANCE`, which the P0.1 detector applies
# across household sizes and which admits a far wider group.
SAFETY_MARKUP_RATIO_TOLERANCE = 5e-4

# Euro thresholds §8.3 requires a share above.
ABSOLUTE_ERROR_THRESHOLDS_EUR: tuple[int, ...] = (25, 50, 100)

# Columns `build_analysis_frame` takes from the Gemeinde crosswalk.
_CROSSWALK_COLUMNS: tuple[str, ...] = (
    "ags",
    "bundesland",
    "kreis",
    "is_kreisfrei",
    "mietenstufe",
    "population",
    "gemeinde_size_class",
    "is_small_gemeinde",
)

# The §8.3 breakdowns, as column names of the analysis frame. The last two
# carry the §18 Regionstyp variations the plan adds on top of §8.3: the
# <10,000 / >=10,000 split of §9.1 and the east-west split.
BREAKDOWN_COLUMNS: tuple[str, ...] = (
    "bundesland",
    "mietenstufe",
    "gemeinde_size_class",
    "region_type",
    "quality_tier",
    "gemeinde_size_group",
    "east_west",
)

# AGS state codes of the neue Länder. Berlin is reported on its own, because
# assigning the whole city to either side would be a claim the data cannot
# support.
EAST_STATE_CODES: frozenset[str] = frozenset({"12", "13", "14", "15", "16"})
BERLIN_STATE_CODE = "11"


def iter_household_sizes(frame: pd.DataFrame) -> Iterator[tuple[int, pd.DataFrame]]:
    """Yield `(household_size, rows)` with the size as a plain `int`.

    `DataFrame.groupby` types its key as `Hashable`, which every caller then
    has to narrow; doing it once here keeps the narrowing out of the analysis
    and figure code.
    """
    for household_size, group in frame.groupby("household_size"):
        yield int(cast("int", household_size)), group


def build_analysis_frame(
    sample: pd.DataFrame,
    crosswalk: pd.DataFrame,
    *,
    variant: BenchmarkVariant = BenchmarkVariant.BASE,
) -> pd.DataFrame:
    """Join the sample to its Gemeinde covariates and stamp the §8.1 measures.

    Args:
        sample: A long `ags × household_size` analysis sample.
        crosswalk: The Gemeinde crosswalk carrying population and geography.
        variant: Which Wohngeld quantity to use as `W` (D6).

    Returns:
        One row per `ags × household_size`, with `cap_eur`, `benchmark_eur`, the
        four §8.1 measures, the two D7 linkage flags, and every covariate the
        §8.3 breakdowns need.

    """
    covariates = crosswalk.loc[:, list(_CROSSWALK_COLUMNS)]
    joined = sample.merge(covariates, on="ags", how="left", validate="many_to_one")
    _fail_if_covariates_are_missing(joined)

    frame = add_proxy_error_measures(joined, variant=variant)
    frame["region_type"] = np.where(
        frame["is_kreisfrei"].astype("boolean").fillna(value=False),
        "kreisfrei",
        "kreisangehörig",
    )
    frame["at_safety_markup"] = at_safety_markup(frame)
    frame["population"] = frame["population"].astype("int64")
    frame["gemeinde_size_group"] = np.where(
        frame["is_small_gemeinde"].astype("boolean").fillna(value=False),
        "under 10,000 inhabitants",
        "10,000 inhabitants and over",
    )
    frame["east_west"] = _east_west(frame)
    return frame


def add_proxy_error_measures(
    frame: pd.DataFrame,
    *,
    variant: BenchmarkVariant = PRIMARY_BENCHMARK,
) -> pd.DataFrame:
    """Add the four §8.1 measures of the gap between `K` and `W`.

    `D = K − W` in euro, `P = 100 (K/W − 1)` in percent, `L = 100 (log K − log W)`
    in log points, and `A = |D|`. §8.1 prefers `L` for maps and regressions and
    `D` for social-policy interpretation.

    Args:
        frame: Any frame carrying `kdu_bkc_cap` and the `wogg_*` columns.
        variant: Which Wohngeld quantity to use as `W` (D6).

    Returns:
        A copy of `frame` with `cap_eur`, `benchmark_eur`, `proxy_error_eur`,
        `proxy_error_pct`, `proxy_error_log`, `proxy_error_abs`, `cap_ratio`,
        and the boolean `comparable`.

    """
    result = frame.copy()
    cap = _as_float(result["kdu_bkc_cap"])
    benchmark = _benchmark(result, variant=variant)

    result["benchmark_variant"] = str(variant)
    result["cap_eur"] = cap
    result["benchmark_eur"] = benchmark
    result["cap_ratio"] = cap / benchmark
    result["proxy_error_eur"] = cap - benchmark
    result["proxy_error_pct"] = 100.0 * (result["cap_ratio"] - 1.0)
    result["proxy_error_log"] = 100.0 * (np.log(cap) - np.log(benchmark))
    result["proxy_error_abs"] = result["proxy_error_eur"].abs()
    result["comparable"] = result["proxy_error_eur"].notna()
    return result


def rent_dependent_error(
    rent: float | np.ndarray | pd.Series,
    cap: float | np.ndarray | pd.Series,
    benchmark: float | np.ndarray | pd.Series,
) -> float | np.ndarray | pd.Series:
    """Evaluate `e(m) = min(m, K) − min(m, W)`, the §8.4 benefit-relevant error.

    The cap difference only reaches the household once actual rent `m` clears
    the lower of the two caps: below that both scenarios recognise the rent in
    full and `e(m) = 0`. Above the higher cap the error saturates at `K − W`.

    Args:
        rent: Actual Bruttokaltmiete `m`.
        cap: The local KdU cap `K`.
        benchmark: The Wohngeld Höchstbetrag `W`.

    Returns:
        The difference in recognised Unterkunftsbedarf, in euro per month.

    """
    return np.minimum(rent, cap) - np.minimum(rent, benchmark)


def build_rent_grid(frame: pd.DataFrame) -> pd.DataFrame:
    """Evaluate the §8.4 error on the five prescribed rent points.

    Args:
        frame: Comparable rows carrying `cap_eur` and `benchmark_eur`.

    Returns:
        A long frame, five rows per input row, with `rent_point`, `rent_eur`,
        `benefit_relevant_error_eur`, `share_of_full_difference`, and the
        `difference_sign` the figure facets on.

    """
    cap = frame["cap_eur"].astype(float)
    benchmark = frame["benchmark_eur"].astype(float)
    lower = np.minimum(cap, benchmark)
    upper = np.maximum(cap, benchmark)
    rents = {
        RENT_POINT_LABELS[0]: 0.8 * lower,
        RENT_POINT_LABELS[1]: lower,
        RENT_POINT_LABELS[2]: 0.5 * (cap + benchmark),
        RENT_POINT_LABELS[3]: upper,
        RENT_POINT_LABELS[4]: 1.2 * upper,
    }

    carried = [
        column
        for column in ("ags", "household_size", "wogg_linked_flag", "at_safety_markup")
        if column in frame.columns
    ]
    pieces = []
    for label, rent in rents.items():
        piece = frame.loc[:, carried].copy()
        piece["rent_point"] = label
        piece["rent_eur"] = rent
        piece["benefit_relevant_error_eur"] = rent_dependent_error(
            rent,
            cap,
            benchmark,
        )
        piece["full_difference_eur"] = cap - benchmark
        pieces.append(piece)

    grid = pd.concat(pieces, ignore_index=True)
    grid["rent_point"] = pd.Categorical(
        grid["rent_point"],
        categories=list(RENT_POINT_LABELS),
        ordered=True,
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        grid["share_of_full_difference"] = np.where(
            grid["full_difference_eur"] == 0,
            np.nan,
            100.0
            * grid["benefit_relevant_error_eur"]
            / grid["full_difference_eur"].replace(0.0, np.nan),
        )
    grid["difference_sign"] = np.select(
        [grid["full_difference_eur"] > 0, grid["full_difference_eur"] < 0],
        ["K above W", "K below W"],
        default="K equals W",
    )
    return grid.sort_values(
        [*carried, "rent_point"],
        kind="stable",
    ).reset_index(drop=True)


def observation_weights(
    frame: pd.DataFrame,
    scheme: WeightingScheme,
    bedarfsgemeinschaft_stocks: pd.DataFrame | None = None,
) -> pd.Series:
    """Return the §8.2 weight of every row under `scheme`.

    The four schemes answer four different questions: what the administrative
    landscape looks like, what the population is exposed to, how independent
    regulatory regimes differ, and what potentially affected households face.

    - `GEMEINDE_UNWEIGHTED` — one per row.
    - `GEMEINDE_POPULATION` — Gemeinde population, so the weights sum to the
      population the sample covers.
    - `POLICY_REGION_UNWEIGHTED` — `1/n` within each Kreis, so every Kreis
      carries total weight one whatever its Gemeinde count (D1).
    - `BEDARFSGEMEINSCHAFT` — the Kreis's BG stock at this household size,
      spread over its Gemeinden in proportion to population. BA publishes no
      Gemeinde-level stock, so the within-Kreis split is an assumption, and it
      is the only one available that does not ignore Gemeinde size.

    Args:
        frame: Rows to weight, all at one household size for scheme 4.
        scheme: The §8.2 weighting scheme.
        bedarfsgemeinschaft_stocks: `policy_region_id × household_size × bg_stock`,
            required by `BEDARFSGEMEINSCHAFT` and ignored otherwise.

    Raises:
        ValueError: If BG weights are requested without a stock table.

    """
    if scheme is WeightingScheme.GEMEINDE_UNWEIGHTED:
        return pd.Series(data=1.0, index=frame.index, name="weight")
    if scheme is WeightingScheme.GEMEINDE_POPULATION:
        return frame["population"].astype(float).rename("weight")
    if scheme is WeightingScheme.POLICY_REGION_UNWEIGHTED:
        counts = frame.groupby("policy_region_id")["ags"].transform("size")
        return (1.0 / counts.astype(float)).rename("weight")
    if bedarfsgemeinschaft_stocks is None:
        msg = (
            "Bedarfsgemeinschaft weights need a stock table; pass "
            "`bedarfsgemeinschaft_stocks` or drop the scheme and say so."
        )
        raise ValueError(msg)
    return _bedarfsgemeinschaft_weights(frame, bedarfsgemeinschaft_stocks)


def load_bedarfsgemeinschaft_stocks(frame: pd.DataFrame) -> pd.DataFrame:
    """Reduce the BA Wohnkosten table to a Kreis-by-household-size BG stock.

    Args:
        frame: `bld/ba_wohnkosten_long.parquet` as written by P1.2.

    Returns:
        `policy_region_id`, `household_size`, `bg_stock`, one row per pair.

    """
    stocks = frame.query(
        "measure == 'bg_stock' and region_level == 'kreis' "
        "and breakdown == 'household_size' and category != 'total'",
    ).copy()
    stocks["household_size"] = (
        stocks["category"].astype(str).str.extract(r"^(\d+)", expand=False).astype(int)
    )
    stocks = stocks.rename(
        columns={"region_code": "policy_region_id", "value": "bg_stock"},
    )
    return (
        stocks.groupby(["policy_region_id", "household_size"], as_index=False)[
            "bg_stock"
        ]
        .sum()
        .astype({"bg_stock": float})
    )


def weighted_quantile(
    values: pd.Series,
    weights: pd.Series,
    quantile: float,
) -> float:
    """Return the `quantile` of `values` under `weights`.

    Interpolates on the cumulative weight shifted by half a weight, so that
    equal weights reproduce the ordinary linear-interpolation quantile.

    Args:
        values: The quantity to summarise.
        weights: Non-negative weights aligned with `values`.
        quantile: A probability in `[0, 1]`.

    """
    clean = pd.DataFrame({"value": values, "weight": weights}).dropna()
    clean = clean.loc[clean["weight"] > 0].sort_values("value", kind="stable")
    if clean.empty:
        return float("nan")
    weight = clean["weight"].to_numpy(dtype=float)
    total = weight.sum()
    position = (np.cumsum(weight) - 0.5 * weight) / total
    return float(np.interp(quantile, position, clean["value"].to_numpy(dtype=float)))


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    """Return the weighted mean of `values`, ignoring missing observations."""
    clean = pd.DataFrame({"value": values, "weight": weights}).dropna()
    if clean.empty or clean["weight"].sum() == 0:
        return float("nan")
    return float(np.average(clean["value"], weights=clean["weight"]))


def weighted_std(values: pd.Series, weights: pd.Series) -> float:
    """Return the weighted standard deviation of `values`."""
    clean = pd.DataFrame({"value": values, "weight": weights}).dropna()
    if len(clean) < 2 or clean["weight"].sum() == 0:  # noqa: PLR2004
        return float("nan")
    mean = np.average(clean["value"], weights=clean["weight"])
    variance = np.average((clean["value"] - mean) ** 2, weights=clean["weight"])
    return float(np.sqrt(variance))


def weighted_share(mask: pd.Series, weights: pd.Series) -> float:
    """Return the weighted share of `mask` that is true, in percent."""
    clean = pd.DataFrame({"flag": mask.astype(float), "weight": weights}).dropna()
    if clean.empty or clean["weight"].sum() == 0:
        return float("nan")
    return float(100.0 * np.average(clean["flag"], weights=clean["weight"]))


def describe(
    frame: pd.DataFrame,
    *,
    value_column: str = "proxy_error_eur",
    weights: pd.Series | None = None,
) -> dict[str, float]:
    """Return the §8.3 statistic block for one group of observations.

    Counts of Gemeinden and Policy-Regionen and the covered population are
    unweighted throughout: they describe the group, not the distribution. Every
    moment, quantile, and share below them is weighted.

    Args:
        frame: The rows to summarise.
        value_column: Which §8.1 measure to describe.
        weights: Row weights; unweighted if omitted.

    """
    weight = (
        pd.Series(data=1.0, index=frame.index)
        if weights is None
        else weights.astype(float)
    )
    values = frame[value_column].astype(float)
    absolute = values.abs()

    stats: dict[str, float] = {
        "n_gemeinden": float(frame["ags"].nunique()),
        "n_policy_regions": float(frame["policy_region_id"].nunique()),
        "population_covered": float(frame["population"].sum()),
        "mean": weighted_mean(values, weight),
        "std": weighted_std(values, weight),
        "min": float(values.min()) if values.notna().any() else float("nan"),
        "max": float(values.max()) if values.notna().any() else float("nan"),
        "share_positive": weighted_share(values > 0, weight),
        "share_negative": weighted_share(values < 0, weight),
        "mean_absolute": weighted_mean(absolute, weight),
    }
    for name, probability in (
        ("p10", 0.10),
        ("p25", 0.25),
        ("median", 0.50),
        ("p75", 0.75),
        ("p90", 0.90),
    ):
        stats[name] = weighted_quantile(values, weight, probability)
    for threshold in ABSOLUTE_ERROR_THRESHOLDS_EUR:
        stats[f"share_abs_gt_{threshold}"] = weighted_share(
            absolute > threshold,
            weight,
        )
    return stats


def describe_by(
    frame: pd.DataFrame,
    *,
    group_column: str,
    value_column: str = "proxy_error_eur",
    weights: pd.Series | None = None,
) -> pd.DataFrame:
    """Run {func}`describe` within every level of `group_column`.

    Args:
        frame: The rows to summarise.
        group_column: The §8.3 breakdown to split on.
        value_column: Which §8.1 measure to describe.
        weights: Row weights; unweighted if omitted.

    Returns:
        One row per group level, sorted by level, with the group in the first
        column.

    """
    weight = (
        pd.Series(data=1.0, index=frame.index)
        if weights is None
        else weights.astype(float)
    )
    rows = []
    for level, group in frame.groupby(group_column, observed=True, dropna=False):
        stats = describe(
            group,
            value_column=value_column,
            weights=weight.loc[group.index],
        )
        rows.append({group_column: level, **stats})
    return (
        pd.DataFrame(rows)
        .sort_values(group_column, kind="stable")
        .reset_index(drop=True)
    )


def linkage_groups(frame: pd.DataFrame) -> Mapping[LinkageGroup, pd.Series]:
    """Return the D7 row masks every headline must be reported under."""
    flagged = frame["wogg_linked_flag"].astype(bool)
    at_markup = frame["at_safety_markup"].astype(bool)
    return {
        LinkageGroup.ALL: pd.Series(data=True, index=frame.index),
        LinkageGroup.EXCLUDING_WOGG_LINKED: ~flagged,
        LinkageGroup.WOGG_LINKED_ONLY: flagged,
        LinkageGroup.EXCLUDING_AT_SAFETY_MARKUP: ~at_markup,
        LinkageGroup.AT_SAFETY_MARKUP_ONLY: at_markup,
    }


def linkage_overlap(frame: pd.DataFrame) -> pd.DataFrame:
    """Cross the `linked_union` and `exact_ratio` groups, per household size.

    A12 requires every table to name which of the two WoGG-linkage groups it
    uses, because they are not the same set of Gemeinden. A22 sharpens that:
    `linked_union` is **broader than, and not a superset of** `exact_ratio`.
    This function is what lets a table note say so with its own numbers rather
    than a remembered figure.

    - `linked_union` — `wogg_linked_flag`, the union of D7's notes-regex and
      ratio detectors, which applies its tolerance across household sizes.
    - `exact_ratio` — `at_safety_markup`, `K/W` at 1.10 within
      `WOGG_SAFETY_MARKUP_TOLERANCE` at *this* household size.

    Args:
        frame: The proxy-error frame, carrying `wogg_linked_flag`,
            `at_safety_markup` and `comparable`.

    Returns:
        One row per `household_size` with `n_comparable`, `n_linked_union`,
        `n_exact_ratio`, `n_both`, `n_union_only` and `n_exact_only`. Only the
        comparable rows are counted: a Gemeinde with no statutory Mietenstufe
        has no Wohngeld benchmark at all, so neither group can speak for it
        (A2). Both group memberships are properties of the Gemeinde rather than
        of the benchmark variant, so a frame carrying one row per variant is
        deduplicated on `ags × household_size` and each Gemeinde counts once.

    """
    comparable = frame.loc[frame["comparable"].astype(bool)].drop_duplicates(
        subset=["ags", "household_size"],
    )
    union = comparable["wogg_linked_flag"].astype(bool)
    exact = comparable["at_safety_markup"].astype(bool)
    counts = pd.DataFrame(
        {
            "household_size": comparable["household_size"],
            "n_comparable": 1,
            "n_linked_union": union.astype(int),
            "n_exact_ratio": exact.astype(int),
            "n_both": (union & exact).astype(int),
            "n_union_only": (union & ~exact).astype(int),
            "n_exact_only": (~union & exact).astype(int),
        },
    )
    return (
        counts.groupby("household_size", as_index=False)
        .sum()
        .sort_values("household_size", kind="stable")
        .reset_index(drop=True)
    )


def proxy_error_by_household_size(
    frame: pd.DataFrame,
    *,
    weighting: WeightingScheme = WeightingScheme.GEMEINDE_UNWEIGHTED,
    bedarfsgemeinschaft_stocks: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build Table 2 of §19: the proxy error by household size.

    Every household size appears three times over — pooled, without the
    WoGG-linked Gemeinden, and for those Gemeinden alone — because D7 forbids
    reporting the pooled median as an empirical regularity. The share of
    Gemeinden sitting exactly on the 10 % Sicherheitszuschlag travels with each
    pooled row so a reader always sees how much of it is definitional.

    Args:
        frame: The analysis frame from {func}`build_analysis_frame`.
        weighting: Which §8.2 scheme to apply.
        bedarfsgemeinschaft_stocks: Needed only for the BG weighting.

    """
    comparable = frame.loc[frame["comparable"]]
    rows = []
    for household_size, size_group in iter_household_sizes(comparable):
        weights = observation_weights(
            size_group,
            weighting,
            bedarfsgemeinschaft_stocks,
        )
        share_at_markup = weighted_share(size_group["at_safety_markup"], weights)
        share_flagged = weighted_share(size_group["wogg_linked_flag"], weights)
        for group, mask in linkage_groups(size_group).items():
            selected = size_group.loc[mask]
            if selected.empty:
                continue
            selected_weights = weights.loc[selected.index]
            euro = describe(
                selected,
                value_column="proxy_error_eur",
                weights=selected_weights,
            )
            rows.append(
                {
                    "household_size": household_size,
                    "group": str(group),
                    "weighting": str(weighting),
                    "n_gemeinden": euro["n_gemeinden"],
                    "n_policy_regions": euro["n_policy_regions"],
                    "median_eur": euro["median"],
                    "mean_eur": euro["mean"],
                    "p10_eur": euro["p10"],
                    "p90_eur": euro["p90"],
                    "mean_absolute_eur": euro["mean_absolute"],
                    "share_abs_gt_50": euro["share_abs_gt_50"],
                    "share_abs_gt_100": euro["share_abs_gt_100"],
                    "median_log": weighted_quantile(
                        selected["proxy_error_log"],
                        selected_weights,
                        0.50,
                    ),
                    "mean_log": weighted_mean(
                        selected["proxy_error_log"],
                        selected_weights,
                    ),
                    "median_pct": weighted_quantile(
                        selected["proxy_error_pct"],
                        selected_weights,
                        0.50,
                    ),
                    "share_at_safety_markup_pct": share_at_markup,
                    "share_wogg_linked_flag_pct": share_flagged,
                },
            )
    return pd.DataFrame(rows)


def coverage_by_state(
    sample: pd.DataFrame,
    crosswalk: pd.DataFrame,
) -> pd.DataFrame:
    """Build Table 1 of §19: coverage and data quality by Bundesland.

    The denominator is every Gemeinde in Germany, not every Gemeinde in the
    sample, so the table shows what the analysis misses as well as what it
    holds. A Gemeinde's quality tier is the worst tier over its household
    sizes, because a table is only as good as its weakest entry.

    Args:
        sample: `analysis_sample_main`, long over `ags × household_size`.
        crosswalk: The Gemeinde crosswalk, all 10,980 Gemeinden.

    """
    per_gemeinde = _collapse_to_gemeinde(sample)
    joined = crosswalk.merge(per_gemeinde, on="ags", how="left", validate="one_to_one")
    joined["in_main_sample"] = joined["quality_tier"].notna()

    rows = []
    for state, group in joined.groupby("bundesland", observed=True):
        in_sample = group.loc[group["in_main_sample"]]
        n_in_sample = len(in_sample)
        rows.append(
            {
                "bundesland": state,
                "n_gemeinden_total": len(group),
                "n_gemeinden_main_sample": n_in_sample,
                "share_gemeinden_main_sample": 100.0 * n_in_sample / len(group),
                "population_total": int(group["population"].sum()),
                "population_main_sample": int(in_sample["population"].sum()),
                "share_population_covered": (
                    100.0 * in_sample["population"].sum() / group["population"].sum()
                ),
                "n_policy_regions_total": group["policy_region_id"].nunique(),
                "n_policy_regions_main_sample": in_sample["policy_region_id"].nunique(),
                "share_quality_a": _tier_share(in_sample, "A"),
                "share_quality_b": _tier_share(in_sample, "B"),
                "share_quality_c": _tier_share(in_sample, "C"),
                "share_published_gross_cold": _share_true(
                    in_sample,
                    "published_gross_cold",
                ),
                "n_without_wogg_benchmark": int(
                    in_sample["wogg_rent_level_missing"].sum(),
                ),
            },
        )
    return pd.DataFrame(rows).sort_values("bundesland").reset_index(drop=True)


def winsorise_for_display(
    values: pd.Series,
    *,
    share: float = 0.01,
) -> pd.Series:
    """Clip both tails at `share` for graphical scaling only.

    §18 permits winsorising to keep a colour scale readable and forbids
    deleting a genuine extreme value merely for being large. Nothing is
    dropped: the returned series has the same length and index, and no table
    in this module is computed from it.

    Args:
        values: The series to clip.
        share: Tail probability clipped at each end.

    """
    finite = values.dropna()
    if finite.empty:
        return values
    lower = float(finite.quantile(share))
    upper = float(finite.quantile(1.0 - share))
    return values.clip(lower=lower, upper=upper)


def symmetric_colour_range(values: Sequence[float] | pd.Series) -> tuple[float, float]:
    """Return a zero-centred `(low, high)` spanning `values`.

    §8.5 requires the h=1 and h=4 maps to share one colour scale centred on
    zero, so that a colour means the same thing on both.
    """
    series = pd.Series(list(values), dtype=float).dropna()
    if series.empty:
        return (-1.0, 1.0)
    bound = float(max(abs(series.min()), abs(series.max())))
    bound = bound if bound > 0 else 1.0
    return (-bound, bound)


def _benchmark(frame: pd.DataFrame, *, variant: BenchmarkVariant) -> pd.Series:
    base = _as_float(frame["wogg_base_cap"])
    if variant is BenchmarkVariant.BASE:
        return base
    if variant is BenchmarkVariant.BASE_PLUS_SAFETY_MARKUP:
        return base * WOGG_SAFETY_MARKUP
    climate = _as_float(frame["wogg_climate_component"])
    return base + climate.fillna(0.0)


def _as_float(column: pd.Series) -> pd.Series:
    return pd.to_numeric(column, errors="coerce").astype("float64")


def _east_west(frame: pd.DataFrame) -> pd.Series:
    state_code = frame["ags"].astype(str).str[:2]
    return pd.Series(
        np.select(
            [state_code == BERLIN_STATE_CODE, state_code.isin(EAST_STATE_CODES)],
            ["Berlin", "east"],
            default="west",
        ),
        index=frame.index,
        name="east_west",
    )


def at_safety_markup(frame: pd.DataFrame) -> pd.Series:
    """Flag rows whose cap sits on the BSG 10 % Sicherheitszuschlag (D7).

    The ratio is always `K / wogg_base_cap`, never `cap_ratio`, because the
    Sicherheitszuschlag is defined against the bare § 12 WoGG table. Reading
    `cap_ratio` instead would make the flag mean something different in every
    benchmark variant.

    Args:
        frame: Any frame carrying `kdu_bkc_cap` and `wogg_base_cap`.

    Returns:
        A boolean Series, `False` wherever either cap is missing.

    """
    ratio = _as_float(frame["kdu_bkc_cap"]) / _as_float(frame["wogg_base_cap"])
    close = (ratio - WOGG_SAFETY_MARKUP).abs() <= SAFETY_MARKUP_RATIO_TOLERANCE
    return close.fillna(value=False).astype(bool)


def _bedarfsgemeinschaft_weights(
    frame: pd.DataFrame,
    stocks: pd.DataFrame,
) -> pd.Series:
    population = frame["population"].astype(float)
    region_population = population.groupby(frame["policy_region_id"]).transform("sum")
    keys = pd.DataFrame(
        {
            "policy_region_id": frame["policy_region_id"].astype(str),
            "household_size": frame["household_size"].astype(int),
        },
        index=frame.index,
    )
    merged = keys.merge(
        stocks.astype({"policy_region_id": str, "household_size": int}),
        on=["policy_region_id", "household_size"],
        how="left",
    )
    merged.index = frame.index
    share = np.where(region_population > 0, population / region_population, 0.0)
    return (merged["bg_stock"].astype(float) * share).fillna(0.0).rename("weight")


def _collapse_to_gemeinde(sample: pd.DataFrame) -> pd.DataFrame:
    tier_rank = {"A": 0, "B": 1, "C": 2}
    frame = sample.copy()
    frame["tier_rank"] = frame["quality_tier"].astype(str).map(tier_rank)
    frame["published_gross_cold"] = (
        frame["calculation_method"].astype(str) == "published_gross_cold_total"
    )
    grouped = frame.groupby("ags", as_index=False).agg(
        tier_rank=("tier_rank", "max"),
        published_gross_cold=("published_gross_cold", "all"),
        wogg_rent_level_missing=("wogg_rent_level_missing", "any"),
    )
    grouped["quality_tier"] = grouped["tier_rank"].map({0: "A", 1: "B", 2: "C"})
    return grouped.drop(columns="tier_rank")


def _tier_share(frame: pd.DataFrame, tier: str) -> float:
    if frame.empty:
        return float("nan")
    return float(100.0 * (frame["quality_tier"] == tier).mean())


def _share_true(frame: pd.DataFrame, column: str) -> float:
    if frame.empty:
        return float("nan")
    return float(100.0 * frame[column].astype(bool).mean())


def _fail_if_covariates_are_missing(frame: pd.DataFrame) -> None:
    missing = frame.loc[frame["population"].isna(), "ags"].unique()
    if len(missing) > 0:
        msg = (
            f"{len(missing)} Gemeinden of the sample carry no crosswalk row, "
            f"first {missing[:5].tolist()}. D8 requires every AGS to join; a "
            f"failed join is an error to resolve, never a row to drop."
        )
        raise ValueError(msg)
