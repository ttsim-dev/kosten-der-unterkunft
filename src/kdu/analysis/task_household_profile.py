"""Build the §10 household-size profile, the Familien-Tilt, and their tables.

Two samples run side by side and are never pooled (D3):

- the h=1…4 main sample, 9,442 Gemeinden, of which 9,323 have a statutory
  Mietenstufe and therefore a Wohngeld benchmark to compare against (A2);
- the h=1…5 balanced subsample, 8,543 Gemeinden, which carries the h=5 tilt
  alone and is labelled with its own N wherever it appears.
"""

import textwrap
from pathlib import Path
from typing import Annotated, cast

import numpy as np
import pandas as pd
from pytask import Product

from kdu.analysis.household_profile import (
    DECILE_MOVE_THRESHOLD,
    HEADLINE_TILT_SIZE,
    HOUSEHOLD_PROFILE_GEMEINDE,
    HOUSEHOLD_PROFILE_GEMEINDE_H5,
    HOUSEHOLD_PROFILE_MARGINAL,
    INTERPRETATION_TEXT,
    KDU_COLUMN,
    N_DECILES,
    TABLE_MARGINAL,
    TABLE_RANK_STABILITY,
    TABLE_ROBUSTNESS,
    TABLE_TILT,
    TABLE_TRANSITION,
    TABLE_WOGG_LINKED_CHECK,
    TILT_REFERENCE_SIZE,
    WOGG_KLIMA_COLUMN,
    ZERO_TILT_TOLERANCE,
    Variant,
    bedarfsgemeinschaft_weights,
    build_familien_tilt,
    build_marginal_amounts,
    build_marginal_ratio_status_counts,
    build_marginal_summary,
    build_rank_stability_table,
    build_tilt_summary,
    build_variant_table,
    check_wogg_linked_tilt,
    decile_transition_matrix,
    share_moving_at_least_deciles,
    spearman_correlation,
)
from kdu.analysis.proxy_error import load_bedarfsgemeinschaft_stocks
from kdu.analysis.task_proxy_error import BA_WOHNKOSTEN
from kdu.config import DATA_CATALOG, MAIN_SAMPLE_HOUSEHOLD_SIZES, WeightingScheme
from kdu.final.manifest import register_result

_ANALYSIS_SAMPLE_MAIN = cast("Path", DATA_CATALOG["analysis_sample_main"])
_WOGG_BENCHMARK = cast("Path", DATA_CATALOG["wogg_benchmark"])
_MUNICIPALITY_CROSSWALK = cast("Path", DATA_CATALOG["municipality_crosswalk"])

# Bundesland codes of the neue Länder. Berlin (11) is reported on its own,
# because it is a single Gemeinde spanning both parts of the former divide.
EAST_STATE_CODES: tuple[str, ...] = ("12", "13", "14", "15", "16")
# A Kreis counts as WoGG-linked when more than this share of its Gemeinden are.
KREIS_WOGG_LINKED_MAJORITY = 0.5
# Household sizes the h=5 subsample is balanced over (D3).
EXTENDED_HOUSEHOLD_SIZES: tuple[int, ...] = (1, 2, 3, 4, 5)
# What the Bedarfsgemeinschaft weighting of §8.2 rests on, carried into every
# table that uses it, because the within-Kreis split is an assumption.
_BEDARFSGEMEINSCHAFT_NOTE = (
    "Kreis Bedarfsgemeinschaft stock at this household size, spread over the "
    "Kreis's Gemeinden in proportion to population; BA publishes no "
    "Gemeinde-level stock."
)

_SCRIPT = "src/kdu/analysis/task_household_profile.py"
_DATASET = "household_profile_gemeinde.parquet"


def task_household_profile(
    analysis_sample_main_file: Path = _ANALYSIS_SAMPLE_MAIN,
    wogg_benchmark_file: Path = _WOGG_BENCHMARK,
    municipality_crosswalk_file: Path = _MUNICIPALITY_CROSSWALK,
    gemeinde_file: Annotated[Path, Product] = HOUSEHOLD_PROFILE_GEMEINDE,
    gemeinde_h5_file: Annotated[Path, Product] = HOUSEHOLD_PROFILE_GEMEINDE_H5,
    marginal_file: Annotated[Path, Product] = HOUSEHOLD_PROFILE_MARGINAL,
    marginal_table_file: Annotated[Path, Product] = TABLE_MARGINAL,
    tilt_table_file: Annotated[Path, Product] = TABLE_TILT,
    rank_stability_file: Annotated[Path, Product] = TABLE_RANK_STABILITY,
    transition_file: Annotated[Path, Product] = TABLE_TRANSITION,
    robustness_file: Annotated[Path, Product] = TABLE_ROBUSTNESS,
    wogg_linked_check_file: Annotated[Path, Product] = TABLE_WOGG_LINKED_CHECK,
    interpretation_file: Annotated[Path, Product] = INTERPRETATION_TEXT,
) -> None:
    """Compute every §10 object and write the per-Gemeinde frames and tables."""
    main = pd.read_parquet(analysis_sample_main_file)
    benchmark = pd.read_parquet(wogg_benchmark_file)
    crosswalk = pd.read_parquet(municipality_crosswalk_file)

    stocks = _load_stocks()
    marginal = build_marginal_amounts(main)
    gemeinde = _build_gemeinde_frame(main, crosswalk)
    gemeinde_h5 = _build_gemeinde_frame(
        _extended_long(benchmark, main),
        crosswalk,
        sizes=EXTENDED_HOUSEHOLD_SIZES,
    )

    caps = _wide(main, KDU_COLUMN)
    levels = _relative_levels(gemeinde)

    for path, frame in (
        (gemeinde_file, gemeinde),
        (gemeinde_h5_file, gemeinde_h5),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path)
    marginal.to_parquet(marginal_file)

    marginal_table = pd.concat(
        [
            _marginal_summaries(marginal, gemeinde, stocks),
            build_marginal_ratio_status_counts(marginal),
        ],
        ignore_index=True,
    )
    tilt_table = pd.concat(
        [
            _tilt_summary(gemeinde, sample="main_h1_h4", stocks=stocks),
            _tilt_summary(gemeinde_h5, sample="balanced_h1_h5", stocks=stocks),
        ],
        ignore_index=True,
    )
    rank_stability = build_rank_stability_table(caps, levels)
    transition = decile_transition_matrix(
        caps[TILT_REFERENCE_SIZE],
        caps[HEADLINE_TILT_SIZE],
    ).reset_index()
    robustness = _robustness(main, gemeinde, gemeinde_h5, stocks)
    wogg_linked_check = _wogg_linked_check(gemeinde, gemeinde_h5)

    _write_csv(marginal_table_file, marginal_table)
    _write_csv(tilt_table_file, tilt_table)
    _write_csv(rank_stability_file, rank_stability)
    _write_csv(transition_file, transition)
    _write_csv(robustness_file, robustness)
    _write_csv(wogg_linked_check_file, wogg_linked_check)
    _register(
        marginal=marginal_table,
        tilt=tilt_table,
        rank_stability=rank_stability,
        transition=transition,
        robustness=robustness,
        wogg_linked_check=wogg_linked_check,
    )
    interpretation_file.write_text(
        _interpretation(main, marginal, gemeinde, gemeinde_h5, caps, levels),
        encoding="utf-8",
    )
    _register_interpretation(interpretation_file, gemeinde)


def _register_interpretation(path: Path, gemeinde: pd.DataFrame) -> None:
    """Record the §21 reading of the four §10.4 figures in the manifest."""
    tilt = gemeinde[f"tilt_h{HEADLINE_TILT_SIZE}"].dropna()
    check = check_wogg_linked_tilt(
        gemeinde[f"tilt_h{HEADLINE_TILT_SIZE}"],
        gemeinde["wogg_linked_flag"],
    )
    register_result(
        filename=path.name,
        analysis_module="P0.5",
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"The §21 four-part reading of the four §10.4 figures: across "
            f"{tilt.size:,} comparable Gemeinden the median Familien-Tilt is "
            f"{tilt.median():+.4f} log points but the P10–P90 span runs "
            f"{tilt.quantile(0.10):+.4f} to {tilt.quantile(0.90):+.4f}, so the "
            "error a model makes by substituting the Wohngeld Höchstbetrag "
            "changes with household size inside one and the same Gemeinde."
        ),
        limitation=(
            f"{int(check['n_flagged']):,} of those Gemeinden are "
            "`linked_union`, and where K is a fixed multiple of W at every h "
            "the tilt is zero by construction, so the pooled median understates "
            "the dispersion; every distribution is therefore also reported "
            "without them. A steep cap schedule is never evidence of "
            "family-friendly local policy: the schedule is endogenous to the "
            "local housing stock and to how the Kreis draws its Vergleichsräume."
        ),
    )


def _register(
    marginal: pd.DataFrame,
    tilt: pd.DataFrame,
    rank_stability: pd.DataFrame,
    transition: pd.DataFrame,
    robustness: pd.DataFrame,
    wogg_linked_check: pd.DataFrame,
) -> None:
    """Record the six §5.2 tables of the household-size profile."""
    unweighted = WeightingScheme.GEMEINDE_UNWEIGHTED.value
    ratios = marginal.query(
        "quantity == 'marginal_ratio' and weighting_scheme == @unweighted",
    )
    register_result(
        filename=TABLE_MARGINAL.name,
        analysis_module="P0.5",
        dataset="household_profile_marginal.parquet",
        script=_SCRIPT,
        interpretation=(
            f"The euro step each additional person adds to the local cap, "
            f"against the same step in the Wohngeld table: the median ratio "
            f"stays between {ratios['p50'].min():.2f} and "
            f"{ratios['p50'].max():.2f}, so Kreise scale their caps with "
            f"household size close to the statutory profile at the median."
        ),
        limitation=(
            "A ratio of two steps is undefined wherever the Wohngeld step is "
            "missing or a Gemeinde has no previous household size; the status "
            "rows at the foot of the table count exactly how often that happens."
        ),
    )

    headline_tilt = f"tilt_h{HEADLINE_TILT_SIZE}"
    headline = tilt.query(
        "sample == 'main_h1_h4' and tilt == @headline_tilt "
        "and group == 'all' and weighting_scheme == @unweighted",
    ).iloc[0]
    register_result(
        filename=TABLE_TILT.name,
        analysis_module="P0.5",
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"The median Familien-Tilt is {headline['p50']:.3f} across "
            f"{headline['n']:,.0f} Gemeinden, but "
            f"{headline['share_positive']:.0%} tilt towards larger households "
            f"and {headline['share_negative']:.0%} against them, with a "
            f"P10–P90 span of {headline['p10']:+.3f} to {headline['p90']:+.3f}."
        ),
        limitation=(
            "The tilt is a ratio of two administrative caps, so a Gemeinde with "
            "a tilt of zero is not thereby neutral towards families; over half "
            "the WoGG-linked Gemeinden sit at exactly zero by construction."
        ),
    )

    spearman = rank_stability.query("statistic == 'spearman_kdu_cap'")
    moving = rank_stability.query(
        "statistic == 'share_moving_at_least_two_deciles_kdu_cap'",
    )
    register_result(
        filename=TABLE_RANK_STABILITY.name,
        analysis_module="P0.5",
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"Gemeinden largely keep their place in the cap distribution as the "
            f"household grows — Spearman against household size 1 falls only "
            f"from {spearman['value'].max():.2f} to {spearman['value'].min():.2f} "
            f"— yet up to {moving['value'].max():.0%} still move at least two "
            f"deciles."
        ),
        limitation=(
            "Computed on the fixed h=1…4 main sample of D3, so it says nothing "
            "about the h=5 subsample, which carries its own N and is reported "
            "separately."
        ),
    )

    diagonal = _transition_diagonal(transition)
    register_result(
        filename=TABLE_TRANSITION.name,
        analysis_module="P0.5",
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"Between the household-size-1 and household-size-"
            f"{HEADLINE_TILT_SIZE} cap deciles the extreme deciles are the "
            f"sticky ones — {diagonal[0]:.0%} of the bottom and "
            f"{diagonal[-1]:.0%} of the top decile stay put — while the middle "
            f"deciles retain around {diagonal[3:7].mean():.0%}."
        ),
        limitation=(
            "A transition between two rankings of the same caps at one "
            "Stichtag, not a movement over time: a Gemeinde changing decile has "
            "changed no policy."
        ),
    )

    register_result(
        filename=TABLE_ROBUSTNESS.name,
        analysis_module="P0.5",
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"The §18 grid over {robustness['dimension'].nunique()} dimensions "
            f"— benchmark, quality tier, weighting, cost concept, Regionstyp, "
            f"Mietenstufe, Gemeindegröße, spatial unit, household size and "
            f"outliers — leaves the median tilt within "
            f"{robustness['p50'].abs().max():.3f} of zero throughout."
        ),
        limitation=(
            "A robustness grid, not a headline: each row varies one dimension "
            "at a time against the same base specification, and the Jobcenter "
            "and Bedarfsgemeinschaft rows stay empty until the P1.2 BA extract "
            "exists."
        ),
    )

    check = wogg_linked_check.query("sample == 'main_h1_h4'")
    register_result(
        filename=TABLE_WOGG_LINKED_CHECK.name,
        analysis_module="P0.5",
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"The D7 cross-check: of the {check['n_flagged'].max():,.0f} "
            f"WoGG-linked Gemeinden "
            f"{check['share_exactly_zero_flagged'].min():.0%} carry a tilt of "
            f"exactly zero against "
            f"{check['share_exactly_zero_unflagged'].max():.0%} of the "
            f"{check['n_unflagged'].max():,.0f} unflagged ones, so the flag "
            f"does mark Gemeinden reading their caps off the WoGG table."
        ),
        limitation=(
            "The identity holds only to the precision of the published data: "
            "caps are printed in whole euro, so a genuinely linked Gemeinde can "
            "still show a tilt of a few thousandths, which is why the table "
            "reports a within-one-thousandth share alongside the exact one."
        ),
    )


def _transition_diagonal(transition: pd.DataFrame) -> np.ndarray:
    matrix = transition.set_index(transition.columns[0])
    return np.diag(matrix.to_numpy(dtype=float))


def _build_gemeinde_frame(
    long: pd.DataFrame,
    crosswalk: pd.DataFrame,
    *,
    sizes: tuple[int, ...] = MAIN_SAMPLE_HOUSEHOLD_SIZES,
) -> pd.DataFrame:
    """Assemble one row per Gemeinde: tilts, levels, weights and stratifiers."""
    balanced = long.loc[long["household_size"].isin(sizes)]
    tilt = build_familien_tilt(balanced)
    tilt_klima = build_familien_tilt(balanced, wogg_column=WOGG_KLIMA_COLUMN)

    frame = tilt.copy()
    for size in sizes:
        column = f"tilt_h{size}"
        if column in tilt_klima.columns:
            frame[f"{column}_klima"] = tilt_klima[column]
    frame["mean_log_relative_level_klima"] = tilt_klima["mean_log_relative_level"]

    per_gemeinde = balanced.groupby("ags").first()
    for column in (
        "wogg_linked_flag",
        "quality_tier",
        "calculation_method",
        "wogg_rent_level",
    ):
        if column in per_gemeinde.columns:
            frame[column] = per_gemeinde[column].reindex(frame.index)
    if "wogg_linked_flag" not in frame.columns:
        frame["wogg_linked_flag"] = False
    frame["wogg_linked_flag"] = (
        frame["wogg_linked_flag"]
        .fillna(value=False)
        .astype(
            bool,
        )
    )

    meta = crosswalk.set_index("ags").reindex(frame.index)
    frame["gemeinde"] = meta["gemeinde"]
    frame["policy_region_id"] = meta["policy_region_id"]
    frame["kreis"] = meta["kreis"]
    frame["bundesland"] = meta["bundesland"]
    frame["is_kreisfrei"] = meta["is_kreisfrei"].fillna(value=False).astype(bool)
    frame["mietenstufe"] = meta["mietenstufe"]
    frame["population"] = meta["population"].astype("float64")
    frame["gemeinde_size_class"] = meta["gemeinde_size_class"].astype("string")
    frame["is_small_gemeinde"] = (
        meta["is_small_gemeinde"]
        .fillna(
            value=False,
        )
        .astype(bool)
    )
    frame["east_west"] = _east_west(frame.index.to_series())

    frame["weight_gemeinde"] = 1.0
    frame["weight_population"] = frame["population"]
    frame["weight_policy_region"] = 1.0 / frame.groupby("policy_region_id")[
        "weight_gemeinde"
    ].transform("size")
    return frame


def _extended_long(benchmark: pd.DataFrame, main: pd.DataFrame) -> pd.DataFrame:
    """Restrict the benchmark to the Gemeinden balanced over h=1…5 (D3).

    The benchmark carries the caps for all five sizes but none of the
    per-Gemeinde flags, so `wogg_linked_flag` and the quality columns are
    carried over from the main sample, where they were established.
    """
    usable = benchmark.loc[
        benchmark["household_size"].isin(EXTENDED_HOUSEHOLD_SIZES)
        & benchmark[KDU_COLUMN].notna()
    ]
    complete = usable.groupby("ags")["household_size"].nunique() == len(
        EXTENDED_HOUSEHOLD_SIZES,
    )
    balanced = usable.loc[usable["ags"].isin(complete.loc[complete].index)].astype(
        {"household_size": "int64", "ags": "string"},
    )
    flags = (
        main.astype({"ags": "string"})
        .groupby("ags")[["wogg_linked_flag", "quality_tier", "calculation_method"]]
        .first()
    )
    return balanced.merge(flags, how="left", left_on="ags", right_index=True)


def _relative_levels(gemeinde: pd.DataFrame) -> pd.DataFrame:
    columns = {
        int(column.removeprefix("log_relative_level_h")): gemeinde[column]
        for column in gemeinde.columns
        if column.startswith("log_relative_level_h")
    }
    return pd.DataFrame(columns)


def _wide(long: pd.DataFrame, column: str) -> pd.DataFrame:
    wide = long.pivot(  # noqa: PD010 - pivot_table would aggregate; the key is unique
        index="ags",
        columns="household_size",
        values=column,
    )
    wide.columns = [int(size) for size in wide.columns]
    return wide.astype("float64")


def _weights(
    gemeinde: pd.DataFrame,
    stocks: pd.DataFrame | None,
    *,
    household_size: int,
) -> dict[str, pd.Series]:
    """The §8.2 schemes available for one household size.

    The Bedarfsgemeinschaft scheme is the one P0.3 built; it joins the other
    three whenever the BA stock table exists, and is absent otherwise.
    """
    schemes = {
        WeightingScheme.GEMEINDE_UNWEIGHTED.value: gemeinde["weight_gemeinde"],
        WeightingScheme.GEMEINDE_POPULATION.value: gemeinde["weight_population"],
        WeightingScheme.POLICY_REGION_UNWEIGHTED.value: gemeinde[
            "weight_policy_region"
        ],
    }
    if stocks is None:
        return schemes
    schemes[WeightingScheme.BEDARFSGEMEINSCHAFT.value] = bedarfsgemeinschaft_weights(
        gemeinde,
        stocks,
        household_size=household_size,
    )
    return schemes


def _load_stocks() -> pd.DataFrame | None:
    if not BA_WOHNKOSTEN.exists():
        return None
    return load_bedarfsgemeinschaft_stocks(pd.read_parquet(BA_WOHNKOSTEN))


def _tilt_summary(
    gemeinde: pd.DataFrame,
    *,
    sample: str,
    stocks: pd.DataFrame | None,
) -> pd.DataFrame:
    rows = []
    for column in sorted(c for c in gemeinde.columns if _is_plain_tilt(c)):
        summary = build_tilt_summary(
            gemeinde[column],
            wogg_linked=gemeinde["wogg_linked_flag"],
            weights=_weights(
                gemeinde,
                stocks,
                household_size=int(column.removeprefix("tilt_h")),
            ),
        )
        summary.insert(0, "sample", sample)
        summary.insert(1, "tilt", column)
        rows.append(summary)
    return pd.concat(rows, ignore_index=True)


def _is_plain_tilt(column: str) -> bool:
    return column.startswith("tilt_h") and not column.endswith("_klima")


def _marginal_summaries(
    marginal: pd.DataFrame,
    gemeinde: pd.DataFrame,
    stocks: pd.DataFrame | None,
) -> pd.DataFrame:
    """Summarise the §10.1 marginal amounts under every available §8.2 scheme.

    The Bedarfsgemeinschaft weight is specific to a household size, so its
    rows are built one size at a time; the other three schemes are constant
    across sizes and are summarised in one call each.
    """
    sizes = sorted(marginal["household_size"].unique())
    constant = _weights(gemeinde, None, household_size=HEADLINE_TILT_SIZE)
    pieces = [
        build_marginal_summary(marginal, weights=weight, weighting_scheme=scheme)
        for scheme, weight in constant.items()
    ]
    if stocks is not None:
        scheme = WeightingScheme.BEDARFSGEMEINSCHAFT.value
        pieces += [
            build_marginal_summary(
                marginal.loc[marginal["household_size"] == size],
                weights=bedarfsgemeinschaft_weights(
                    gemeinde,
                    stocks,
                    household_size=int(size),
                ),
                weighting_scheme=scheme,
            )
            for size in sizes
        ]
    return pd.concat(pieces, ignore_index=True)


def _robustness(
    main: pd.DataFrame,
    gemeinde: pd.DataFrame,
    gemeinde_h5: pd.DataFrame,
    stocks: pd.DataFrame | None,
) -> pd.DataFrame:
    tilt_column = f"tilt_h{HEADLINE_TILT_SIZE}"
    tilt = gemeinde[tilt_column]
    flag = gemeinde["wogg_linked_flag"]
    variants = [
        Variant("wohngeld_benchmark", "base Höchstbetrag", tilt, wogg_linked=flag),
        Variant(
            "wohngeld_benchmark",
            "base plus Klimakomponente",
            gemeinde[f"{tilt_column}_klima"],
            wogg_linked=flag,
        ),
    ]
    variants += [
        Variant("quality_tier", label, tilt.loc[selector], wogg_linked=flag)
        for label, selector in (
            ("A only", gemeinde["quality_tier"] == "A"),
            ("A and B", gemeinde["quality_tier"].isin(["A", "B"])),
            ("A, B and C", gemeinde["quality_tier"].notna()),
        )
    ]
    variants += [
        Variant(
            "weighting",
            name,
            tilt,
            weights=weight,
            wogg_linked=flag,
            note=_BEDARFSGEMEINSCHAFT_NOTE
            if name == WeightingScheme.BEDARFSGEMEINSCHAFT.value
            else "",
        )
        for name, weight in _weights(
            gemeinde,
            stocks,
            household_size=HEADLINE_TILT_SIZE,
        ).items()
    ]
    if stocks is None:
        variants.append(
            Variant(
                "weighting",
                WeightingScheme.BEDARFSGEMEINSCHAFT.value,
                tilt.iloc[:0],
                wogg_linked=flag,
                note=(
                    "bld/ba_wohnkosten_long.parquet is absent, so no "
                    "Bedarfsgemeinschaft stock exists to weight by."
                ),
            ),
        )
    variants += [
        Variant("cost_concept", label, tilt.loc[selector], wogg_linked=flag)
        for label, selector in (
            (
                "published Bruttokaltmiete",
                gemeinde["calculation_method"] == "published_gross_cold_total",
            ),
            (
                "summed from published components",
                gemeinde["calculation_method"] == "sum_of_published_components",
            ),
        )
    ]
    variants += _region_type_variants(gemeinde, tilt, flag)
    variants += _spatial_unit_variants(gemeinde, tilt_column, flag)
    variants += [
        Variant(
            "household_size",
            f"h={size} against h={TILT_REFERENCE_SIZE}, main sample",
            gemeinde[f"tilt_h{size}"],
            wogg_linked=flag,
        )
        for size in sorted(_tilt_sizes(gemeinde))
    ]
    variants += [
        Variant(
            "household_size",
            f"h={size} against h={TILT_REFERENCE_SIZE}, h=1-5 balanced subsample",
            gemeinde_h5[f"tilt_h{size}"],
            wogg_linked=gemeinde_h5["wogg_linked_flag"],
        )
        for size in sorted(_tilt_sizes(gemeinde_h5))
    ]
    variants.append(
        Variant(
            "outliers",
            "full sample, no winsorisation",
            tilt,
            wogg_linked=flag,
            note=(
                "Extreme values are genuine published caps and are never dropped; "
                "winsorisation is used for figure scaling only."
            ),
        ),
    )
    _fail_if_main_sample_is_unexpected(main, gemeinde)
    return build_variant_table(variants)


def _region_type_variants(
    gemeinde: pd.DataFrame,
    tilt: pd.Series,
    flag: pd.Series,
) -> list[Variant]:
    groups: list[tuple[str, str, pd.Series]] = [
        ("region_type", "kreisfrei", gemeinde["is_kreisfrei"]),
        ("region_type", "kreisangehörig", ~gemeinde["is_kreisfrei"]),
        ("region_type", "under 10,000 inhabitants", gemeinde["is_small_gemeinde"]),
        ("region_type", "10,000 inhabitants and over", ~gemeinde["is_small_gemeinde"]),
    ]
    groups += [
        ("region_type", label, gemeinde["east_west"] == part)
        for part, label in (
            ("East", "East Germany"),
            ("West", "West Germany"),
            ("Berlin", "Berlin"),
        )
    ]
    groups += [
        ("mietenstufe", f"Mietenstufe {int(level)}", gemeinde["mietenstufe"] == level)
        for level in sorted(gemeinde["mietenstufe"].dropna().unique())
    ]
    groups += [
        (
            "gemeinde_size_class",
            str(size_class),
            gemeinde["gemeinde_size_class"].eq(
                size_class,
            ),
        )
        for size_class in sorted(gemeinde["gemeinde_size_class"].dropna().unique())
    ]
    return [
        Variant(dimension, label, tilt.loc[selector], wogg_linked=flag)
        for dimension, label, selector in groups
    ]


def _spatial_unit_variants(
    gemeinde: pd.DataFrame,
    tilt_column: str,
    flag: pd.Series,
) -> list[Variant]:
    by_region = _aggregate_to_policy_region(gemeinde, tilt_column)
    return [
        Variant("spatial_unit", "Gemeinde", gemeinde[tilt_column], wogg_linked=flag),
        Variant(
            "spatial_unit",
            "policy region (Kreis), population-weighted mean",
            by_region["tilt"],
            wogg_linked=by_region["wogg_linked_flag"],
        ),
        Variant(
            "spatial_unit",
            "Jobcenter",
            gemeinde[tilt_column].iloc[:0],
            note=(
                "The Jobcenter crosswalk carries no assignment for the main sample, "
                "so the Kreis is the finest independent unit available."
            ),
        ),
    ]


def _aggregate_to_policy_region(
    gemeinde: pd.DataFrame,
    tilt_column: str,
) -> pd.DataFrame:
    frame = gemeinde.loc[
        gemeinde[tilt_column].notna(),
        [tilt_column, "policy_region_id", "population", "wogg_linked_flag"],
    ]
    weighted = frame[tilt_column] * frame["population"]
    grouped = frame.assign(weighted=weighted).groupby("policy_region_id")
    return pd.DataFrame(
        {
            "tilt": grouped["weighted"].sum() / grouped["population"].sum(),
            "wogg_linked_flag": grouped["wogg_linked_flag"].mean()
            > KREIS_WOGG_LINKED_MAJORITY,
        },
    )


def _tilt_sizes(gemeinde: pd.DataFrame) -> list[int]:
    return [
        int(column.removeprefix("tilt_h"))
        for column in gemeinde.columns
        if _is_plain_tilt(column)
    ]


def _wogg_linked_check(
    gemeinde: pd.DataFrame,
    gemeinde_h5: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for sample, frame in (
        ("main_h1_h4", gemeinde),
        ("balanced_h1_h5", gemeinde_h5),
    ):
        for size in sorted(_tilt_sizes(frame)):
            check = check_wogg_linked_tilt(
                frame[f"tilt_h{size}"],
                frame["wogg_linked_flag"],
            )
            rows.append(
                pd.concat(
                    [
                        pd.Series(
                            {"sample": sample, "tilt": f"tilt_h{size}"},
                            dtype="object",
                        ),
                        check,
                    ],
                ),
            )
    return pd.DataFrame(rows).reset_index(drop=True)


def _between_kreis_variance_share(gemeinde: pd.DataFrame, tilt_column: str) -> float:
    """Return the share of the tilt's variance that lies between Kreise.

    The Kreis is the Träger that writes the Richtlinie (D1), so a tilt that is
    a genuine policy parameter should vary mostly across Kreise rather than
    within them. Kreise that define Vergleichsräume internally are what keeps
    this below one.
    """
    frame = gemeinde.loc[gemeinde[tilt_column].notna(), [tilt_column, "kreis"]]
    total = float(frame[tilt_column].var(ddof=0))
    if total == 0:
        return float("nan")
    within = float(
        frame.groupby("kreis")[tilt_column]
        .transform(lambda block: block - block.mean())
        .var(ddof=0),
    )
    return 1.0 - within / total


def _part(gemeinde: pd.DataFrame, values: pd.Series, part: str) -> pd.Series:
    """Select the values belonging to one part of the country."""
    return gemeinde["east_west"].reindex(values.index) == part


def _share_of_zeros_flagged(gemeinde: pd.DataFrame, tilt: pd.Series) -> float:
    """Return the share of the spike at F=0 that carries `wogg_linked_flag`."""
    at_zero = tilt.abs() <= ZERO_TILT_TOLERANCE
    if not bool(at_zero.any()):
        return float("nan")
    return float(gemeinde["wogg_linked_flag"].reindex(tilt.index).loc[at_zero].mean())


def _east_west(ags: pd.Series) -> pd.Series:
    state = ags.str.slice(0, 2)
    return pd.Series(
        np.where(
            state == "11",
            "Berlin",
            np.where(state.isin(EAST_STATE_CODES), "East", "West"),
        ),
        index=ags.index,
        dtype="string",
    )


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _fail_if_main_sample_is_unexpected(
    main: pd.DataFrame,
    gemeinde: pd.DataFrame,
) -> None:
    expected_gemeinden = 9_442
    expected_comparable = 9_323
    n_gemeinden = int(main["ags"].nunique())
    n_comparable = int(gemeinde[f"tilt_h{HEADLINE_TILT_SIZE}"].notna().sum())
    if n_gemeinden != expected_gemeinden or n_comparable != expected_comparable:
        msg = (
            f"the main sample should hold {expected_gemeinden} Gemeinden of which "
            f"{expected_comparable} carry a Wohngeld benchmark (D3, A2); got "
            f"{n_gemeinden} and {n_comparable}. Either the sample changed or the "
            f"tilt lost Gemeinden it should keep."
        )
        raise ValueError(msg)


def _interpretation(
    main: pd.DataFrame,
    marginal: pd.DataFrame,
    gemeinde: pd.DataFrame,
    gemeinde_h5: pd.DataFrame,
    caps: pd.DataFrame,
    levels: pd.DataFrame,
) -> str:
    """Render the §21 four-part interpretation from the computed statistics."""
    tilt = gemeinde[f"tilt_h{HEADLINE_TILT_SIZE}"].dropna()
    unflagged = tilt.loc[~gemeinde["wogg_linked_flag"].reindex(tilt.index)]
    tilt5 = gemeinde_h5["tilt_h5"].dropna()
    steps = marginal.loc[marginal["household_size"] == HEADLINE_TILT_SIZE]
    check = check_wogg_linked_tilt(
        gemeinde[f"tilt_h{HEADLINE_TILT_SIZE}"],
        gemeinde["wogg_linked_flag"],
    )
    tilt5_unflagged = tilt5.loc[~gemeinde_h5["wogg_linked_flag"].reindex(tilt5.index)]
    context = {
        "n_gemeinden": int(main["ags"].nunique()),
        "n_comparable": int(tilt.size),
        "n_flagged": int(check["n_flagged"]),
        "n_h5_balanced": int(gemeinde_h5.index.size),
        "n_h5": int(tilt5.size),
        "median_h5_unflagged": float(tilt5_unflagged.median()),
        "p10_h5_unflagged": float(tilt5_unflagged.quantile(0.10)),
        "p90_h5_unflagged": float(tilt5_unflagged.quantile(0.90)),
        "level_tilt_spearman": spearman_correlation(
            gemeinde["mean_log_relative_level"],
            gemeinde[f"tilt_h{HEADLINE_TILT_SIZE}"],
        ),
        "median_wogg_step": float(steps["wogg_step"].median()),
        "between_kreis_variance_share": _between_kreis_variance_share(
            gemeinde,
            f"tilt_h{HEADLINE_TILT_SIZE}",
        ),
        "share_of_zeros_flagged": _share_of_zeros_flagged(gemeinde, tilt),
        "median_east": float(
            unflagged.loc[_part(gemeinde, unflagged, "East")].median()
        ),
        "median_west": float(
            unflagged.loc[_part(gemeinde, unflagged, "West")].median()
        ),
        "n_east": int(_part(gemeinde, unflagged, "East").sum()),
        "n_west": int(_part(gemeinde, unflagged, "West").sum()),
        "median": float(tilt.median()),
        "p10": float(tilt.quantile(0.10)),
        "p90": float(tilt.quantile(0.90)),
        "share_zero": float((tilt.abs() <= ZERO_TILT_TOLERANCE).mean()),
        "median_unflagged": float(unflagged.median()),
        "p10_unflagged": float(unflagged.quantile(0.10)),
        "p90_unflagged": float(unflagged.quantile(0.90)),
        "share_over_ten_pct": float((tilt.abs() > np.log(1.10)).mean()),
        "median_step": float(steps["kdu_step"].median()),
        "p10_step": float(steps["kdu_step"].quantile(0.10)),
        "p90_step": float(steps["kdu_step"].quantile(0.90)),
        "median_ratio": float(steps["marginal_ratio"].median()),
        "p10_ratio": float(steps["marginal_ratio"].quantile(0.10)),
        "p90_ratio": float(steps["marginal_ratio"].quantile(0.90)),
        "spearman_caps": spearman_correlation(caps[1], caps[4]),
        "spearman_levels": spearman_correlation(levels[1], levels[4]),
        "move_share": share_moving_at_least_deciles(caps[1], caps[4]),
        "move_share_levels": share_moving_at_least_deciles(levels[1], levels[4]),
        "max_abs_flagged": float(check["max_abs_tilt_flagged"]),
        "share_exact_flagged": float(check["share_exactly_zero_flagged"]),
        "median_h5": float(tilt5.median()),
        "move_threshold": DECILE_MOVE_THRESHOLD,
        "n_deciles": N_DECILES,
    }
    return _rewrap(_INTERPRETATION_TEMPLATE.format(**context))


def _rewrap(text: str, width: int = 88) -> str:
    """Re-flow the rendered text, whose line breaks moved when numbers were filled in.

    Headings and bullets keep their own line; a bullet's continuation lines are
    indented by two spaces so the markdown survives the rewrap.
    """
    blocks = []
    for block in text.split("\n\n"):
        if block.startswith("#"):
            blocks.append(block)
        elif block.lstrip().startswith("- "):
            items = [
                "- " + " ".join(part.split())
                for part in block.removeprefix("- ").split("\n- ")
            ]
            blocks.append(
                "\n".join(
                    textwrap.fill(
                        item,
                        width=width,
                        subsequent_indent="  ",
                        break_on_hyphens=False,
                    )
                    for item in items
                ),
            )
        else:
            blocks.append(
                textwrap.fill(
                    " ".join(block.split()),
                    width=width,
                    break_on_hyphens=False,
                ),
            )
    return "\n\n".join(blocks)


_INTERPRETATION_TEMPLATE = """# P0.5 — Household-size profile and Familien-Tilt

All figures below are computed on the h=1…4 balanced main sample of
{n_gemeinden:,} Gemeinden, of which {n_comparable:,} carry a statutory
Mietenstufe and therefore a Wohngeld benchmark (D3, A2). The h=5 quantities run
on the separate h=1…5 balanced subsample of {n_h5_balanced:,} Gemeinden, of
which {n_h5:,} carry a benchmark, and are never pooled with the rest.

## Figure 1 — Average relative KdU level against the Familien-Tilt

**What is measured?** For each Gemeinde, the average of log(K/W) over h=1…4 on
the horizontal axis, and the Familien-Tilt
F = log(K4/W4) - log(K1/W1) on the vertical.

**Central quantitative finding.** The median Familien-Tilt is
{median:+.4f} log points, with a P10-P90 range of {p10:+.4f} to {p90:+.4f}.
Excluding the {n_flagged:,} WoGG-linked Gemeinden the median is
{median_unflagged:+.4f} and the range widens to {p10_unflagged:+.4f} to
{p90_unflagged:+.4f}. In {share_over_ten_pct:.1%} of Gemeinden the absolute tilt
exceeds log(1.10), i.e. K4/W4 differs from K1/W1 by more than ten percent
within one and the same Gemeinde. The Spearman correlation between the average
relative level and the tilt is {level_tilt_spearman:+.3f}, so how high a
Gemeinde's caps sit relative to the benchmark says little about how that
relative position changes with household size.

**Why it matters for tax-transfer simulation.** A model that substitutes the
Wohngeld Höchstbetrag for the local cap does not make one Gemeinde-specific
level error that a fixed regional intercept could absorb. The error changes
with household size within the same Gemeinde, so the mismeasurement is
correlated with household composition.

**What may not be concluded.** A steeply rising cap schedule is not evidence of
family-friendly local policy. Cap schedules are endogenous to the local housing
stock, the definition of Vergleichsräume, and the vintage of the underlying
Konzept; a Kreis facing a market where large flats are relatively expensive
must set a steeper schedule to recognise the same housing standard.

## Figure 2 — Distribution of marginal KdU amounts per additional person

**What is measured?** ΔK(g,h) = K(g,h) - K(g,h-1), the euro amount the local cap
rises by for one more person in the Bedarfsgemeinschaft, and its ratio to the
statutory step Q(g,h) = ΔK/ΔW.

**Central quantitative finding.** For the fourth person the median local step is
{median_step:.0f} EUR per month, with a P10-P90 range of {p10_step:.0f} to
{p90_step:.0f} EUR, against a median statutory Wohngeld step of
{median_wogg_step:.0f} EUR. The median ratio Q(g,4) = ΔK/ΔW is
{median_ratio:.2f}, and its P10-P90 range of {p10_ratio:.2f} to {p90_ratio:.2f}
straddles one: in a substantial minority of Gemeinden the local schedule rises
by less per additional person than the statutory table does, and in another it
rises by half as much again.

**Why it matters for tax-transfer simulation.** The marginal amount is what a
simulated household gains by adding a member, so it enters every equivalence
scale computed from recognised Bedarf. A wrong step propagates to the exit
threshold and to every household-size comparison built on it.

**What may not be concluded.** ΔK is a cap increment, not an actual KdU payment,
and it is not a measure of what a larger household in that Gemeinde receives.
Where the Wohngeld step is missing — the gemeindefreie Gebiete without a
statutory Mietenstufe — or zero, Q is reported as missing, never as an
infinity.

## Figure 3 — Map of the Familien-Tilt

**What is measured?** F per Gemeinde, on a diverging scale centred at zero.

**Central quantitative finding.** {between_kreis_variance_share:.1%} of the
variance of F lies between Kreise, which is what D1 predicts: the Kreis writes
the Richtlinie, so its whole territory usually shares one schedule, and the
remainder is the internal Vergleichsräume of the 210 Kreise that define them.
{share_zero:.1%} of Gemeinden sit exactly at zero, and
{share_of_zeros_flagged:.1%} of that spike is WoGG-linked. The sharpest single
contrast is East against West: excluding the WoGG-linked Gemeinden the median
tilt is {median_east:+.4f} across {n_east:,} eastern Gemeinden against
{median_west:+.4f} across {n_west:,} western ones. The h=5 tilt on the
separate
{n_h5:,}-Gemeinde subsample has a median of {median_h5:+.4f}, or
{median_h5_unflagged:+.4f} once the WoGG-linked Gemeinden are removed, with a
P10-P90 range of {p10_h5_unflagged:+.4f} to {p90_h5_unflagged:+.4f}.

**Why it matters for tax-transfer simulation.** A regional parameter that varies
at the Kreis level and in a household-size-dependent way cannot be recovered
from the Mietenstufe, which is the only regional housing parameter such models
currently carry.

**What may not be concluded.** Neighbouring Gemeinden with different tilts are
not evidence of a discontinuity in housing costs; without the adjacency
analysis of P1.1 the map is descriptive only. Nothing here is a causal effect
of a local policy choice.

## Figure 4 — Decile transition matrix, h=1 against h=4

**What is measured?** Where a Gemeinde sits in the national distribution of
K(g,1) and where it sits in the distribution of K(g,4), in deciles.

**Central quantitative finding.** The Spearman rank correlation between K(g,1)
and K(g,4) is {spearman_caps:.3f}; between the proxy errors log(K/W) at h=1 and
h=4 it is {spearman_levels:.3f}. {move_share:.1%} of Gemeinden move at least
{move_threshold} deciles in the cap ranking between the two household sizes,
and {move_share_levels:.1%} do so in the proxy-error ranking.

**Why it matters for tax-transfer simulation.** Rank stability is high but not
complete. Calibrating a regional housing parameter on single-person households
and reusing the ranking for families reproduces most of the ordering while
misplacing a non-trivial minority of Gemeinden by two deciles or more.

**What may not be concluded.** Movement between deciles is not evidence that a
Gemeinde changed its policy; it reflects where its published schedule sits
relative to all others at two different household sizes at one Stichtag.

## D7 verification — the WoGG-linked Gemeinden

{n_flagged:,} Gemeinden carry `wogg_linked_flag`. Their Familien-Tilt is
{share_exact_flagged:.1%} exactly zero and never exceeds
{max_abs_flagged:.4f} in absolute value. The residual is rounding: caps are
published in whole euro, so a Gemeinde that genuinely applies the § 12 WoGG
table plus a fixed Sicherheitszuschlag can still show a tilt of a few
thousandths. The claim that these Gemeinden can carry no tilt therefore holds
to the precision of the published data, but not as an exact identity in the
computed numbers, and every tilt distribution is reported with and without
them.

## Limitations that travel with every number here

- All Δ are conditional on the cap being in force; inside the Karenzzeit of
  § 22 Abs. 1 S. 2-3 SGB II actual Unterkunftskosten are recognised in full and
  the proxy error is identically zero (D11).
- 119 main-sample Gemeinden have a cap but no statutory Mietenstufe, so no
  Wohngeld benchmark exists for them and they carry no tilt (A2).
- The sample mixes document vintages from 2019 to 2026 (D2).
- The national deciles of Figure 4 are {n_deciles} equally sized groups of
  Gemeinden, not equally sized groups of people.
"""
