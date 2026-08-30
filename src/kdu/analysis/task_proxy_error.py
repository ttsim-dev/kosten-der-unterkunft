"""Compute the §8 proxy-error frames, descriptive tables, and §18 robustness grid.

The task reads the two analysis samples and the crosswalk, stamps the §8.1
measures under both D6 benchmark variants, and writes one long frame per
artefact. Every table is long over its grouping columns, so a reader never has
to guess which column a number belongs to.

The BG weighting of §8.2 needs the BA Bedarfsgemeinschaft stocks. Where
`bld/ba_wohnkosten_long.parquet` is absent the other three schemes are written
and `bld/tables/proxy_error_weighting_availability.csv` records which scheme was
dropped and why.
"""

from pathlib import Path
from typing import Annotated, cast

import pandas as pd
from pytask import Product

from kdu.analysis.proxy_error import (
    BREAKDOWN_COLUMNS,
    PRIMARY_BENCHMARK,
    RENT_POINT_LABELS,
    BenchmarkVariant,
    LinkageGroup,
    build_analysis_frame,
    build_rent_grid,
    describe,
    describe_by,
    iter_household_sizes,
    linkage_groups,
    load_bedarfsgemeinschaft_stocks,
    observation_weights,
    winsorise_for_display,
)
from kdu.config import BLD, DATA_CATALOG, TABLES, WeightingScheme
from kdu.final.manifest import register_result

_ANALYSIS_SAMPLE_MAIN = cast("Path", DATA_CATALOG["analysis_sample_main"])
_ANALYSIS_SAMPLE_EXTENDED = cast("Path", DATA_CATALOG["analysis_sample_extended"])
_MUNICIPALITY_CROSSWALK = cast("Path", DATA_CATALOG["municipality_crosswalk"])

# Written by P1.2; absent until the BA module has run.
BA_WOHNKOSTEN = BLD / "ba_wohnkosten_long.parquet"

PROXY_ERROR_FRAME = BLD / "proxy_error_gemeinde_household.parquet"
RENT_GRID_FRAME = BLD / "proxy_error_rent_grid.parquet"
DESCRIPTIVES_TABLE = TABLES / "proxy_error_descriptives.csv"
BREAKDOWNS_TABLE = TABLES / "proxy_error_breakdowns.csv"
RENT_GRID_TABLE = TABLES / "proxy_error_rent_dependent.csv"
ROBUSTNESS_TABLE = TABLES / "proxy_error_robustness.csv"
WEIGHTING_AVAILABILITY_TABLE = TABLES / "proxy_error_weighting_availability.csv"

_SCRIPT = "src/kdu/analysis/task_proxy_error.py"
_DATASET = "proxy_error_gemeinde_household.parquet"

# The §18 data-quality subsets, as the tiers each admits.
_QUALITY_SUBSETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tier_a_only", ("A",)),
    ("tier_a_and_b", ("A", "B")),
    ("main_sample_all_tiers", ("A", "B", "C")),
)

# The §8.1 measures every descriptive table reports.
_MEASURES: tuple[str, ...] = (
    "proxy_error_eur",
    "proxy_error_pct",
    "proxy_error_log",
    "proxy_error_abs",
)


def task_proxy_error(
    sample_main_file: Path = _ANALYSIS_SAMPLE_MAIN,
    sample_extended_file: Path = _ANALYSIS_SAMPLE_EXTENDED,
    crosswalk_file: Path = _MUNICIPALITY_CROSSWALK,
    proxy_error_file: Annotated[Path, Product] = PROXY_ERROR_FRAME,
    rent_grid_file: Annotated[Path, Product] = RENT_GRID_FRAME,
    descriptives_file: Annotated[Path, Product] = DESCRIPTIVES_TABLE,
    breakdowns_file: Annotated[Path, Product] = BREAKDOWNS_TABLE,
    rent_grid_table_file: Annotated[Path, Product] = RENT_GRID_TABLE,
    robustness_file: Annotated[Path, Product] = ROBUSTNESS_TABLE,
    weighting_availability_file: Annotated[
        Path,
        Product,
    ] = WEIGHTING_AVAILABILITY_TABLE,
) -> None:
    """Write every §8.3, §8.4, and §18 artefact of the proxy-error analysis."""
    sample_main = pd.read_parquet(sample_main_file)
    sample_extended = pd.read_parquet(sample_extended_file)
    crosswalk = pd.read_parquet(crosswalk_file)
    stocks = _load_stocks()

    frame = build_proxy_error_frame(sample_main, sample_extended, crosswalk)
    primary = frame.loc[
        (frame["benchmark_variant"] == str(PRIMARY_BENCHMARK)) & frame["comparable"]
    ]

    rent_grid = build_rent_grid(primary)

    for path, table in (
        (proxy_error_file, frame),
        (rent_grid_file, rent_grid),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        table.to_parquet(path, index=False)

    tables = {
        descriptives_file: build_descriptives(frame, stocks),
        breakdowns_file: build_breakdowns(primary),
        rent_grid_table_file: summarise_rent_grid(rent_grid),
        robustness_file: build_robustness(frame, stocks),
        weighting_availability_file: _weighting_availability(stocks),
    }
    for path, table in tables.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(path, index=False)

    _register(
        descriptives=tables[descriptives_file],
        breakdowns=tables[breakdowns_file],
        rent_dependent=tables[rent_grid_table_file],
        robustness=tables[robustness_file],
        availability=tables[weighting_availability_file],
    )


def build_proxy_error_frame(
    sample_main: pd.DataFrame,
    sample_extended: pd.DataFrame,
    crosswalk: pd.DataFrame,
) -> pd.DataFrame:
    """Stamp the §8.1 measures on h=1…4 from the main sample and h=5 beside it.

    D3 keeps h=5 on its own footing: it is reported separately, on the 8,543
    Gemeinden balanced over h=1…5, and never pooled into a cross-h object. The
    `sample` column carries that distinction to every consumer.

    Args:
        sample_main: `analysis_sample_main`, balanced over h=1…4.
        sample_extended: `analysis_sample_extended`, which carries h=5.
        crosswalk: The Gemeinde crosswalk.

    """
    fifth = sample_extended.query(
        "household_size == 5 and sample_stratum == 'main_balanced_h1_h4'",
    ).dropna(subset=["kdu_bkc_cap"])
    columns = [column for column in sample_main.columns if column in fifth.columns]

    pieces = []
    for variant in BenchmarkVariant:
        for label, sample in (
            ("main_h1_h4", sample_main),
            ("balanced_h1_h5", fifth.loc[:, columns]),
        ):
            piece = build_analysis_frame(sample, crosswalk, variant=variant)
            piece["sample"] = label
            pieces.append(piece)
    return pd.concat(pieces, ignore_index=True)


def build_descriptives(
    frame: pd.DataFrame,
    stocks: pd.DataFrame | None,
) -> pd.DataFrame:
    """Build the §8.3 statistic block for every cell the plan requires.

    One row per benchmark variant, household size, linkage group, weighting
    scheme, and §8.1 measure. D7 forbids a household size appearing without its
    with/without pair, so the linkage group is a key, never a filter.
    """
    rows: list[dict[str, object]] = []
    for variant, variant_rows in frame.query("comparable").groupby(
        "benchmark_variant",
    ):
        for household_size, cell in iter_household_sizes(variant_rows):
            rows.extend(
                _describe_cell(
                    cell,
                    stocks,
                    benchmark_variant=str(variant),
                    household_size=household_size,
                ),
            )
    return pd.DataFrame(rows)


def _describe_cell(
    cell: pd.DataFrame,
    stocks: pd.DataFrame | None,
    *,
    benchmark_variant: str,
    household_size: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for scheme in _available_schemes(stocks):
        weights = observation_weights(cell, scheme, stocks)
        for group, mask in linkage_groups(cell).items():
            selected = cell.loc[mask]
            if selected.empty:
                continue
            rows.extend(
                {
                    "benchmark_variant": benchmark_variant,
                    "household_size": household_size,
                    "group": str(group),
                    "weighting": str(scheme),
                    "measure": measure,
                    **describe(
                        selected,
                        value_column=measure,
                        weights=weights.loc[selected.index],
                    ),
                }
                for measure in _MEASURES
            )
    return rows


def build_breakdowns(primary: pd.DataFrame) -> pd.DataFrame:
    """Run the five §8.3 breakdowns on the primary benchmark, in long form.

    Bundesland, Mietenstufe, Gemeindegrößenklasse, kreisfrei versus
    kreisangehörig, and quality tier, each for every household size and each
    with and without the WoGG-linked Gemeinden.
    """
    reported = (
        LinkageGroup.ALL,
        LinkageGroup.EXCLUDING_WOGG_LINKED,
        LinkageGroup.WOGG_LINKED_ONLY,
    )
    rows = []
    for household_size, cell in iter_household_sizes(primary):
        masks = linkage_groups(cell)
        for group in reported:
            selected = cell.loc[masks[group]]
            if selected.empty:
                continue
            for breakdown in BREAKDOWN_COLUMNS:
                table = describe_by(selected, group_column=breakdown)
                table = table.rename(columns={breakdown: "level"})
                table.insert(0, "breakdown", breakdown)
                table.insert(0, "group", str(group))
                table.insert(0, "household_size", household_size)
                rows.append(table)
    return pd.concat(rows, ignore_index=True)


def summarise_rent_grid(rent_grid: pd.DataFrame) -> pd.DataFrame:
    """Summarise the §8.4 error at each rent point, split by the sign of `K − W`.

    The split is what makes the point: the error is bounded by `K − W` from
    above and reaches it only once actual rent clears the higher cap, so the
    same cap gap bites very differently depending on which way it runs.
    """
    grouped = rent_grid.groupby(
        ["household_size", "difference_sign", "rent_point"],
        observed=True,
    )
    summary = grouped.agg(
        n_observations=("benefit_relevant_error_eur", "size"),
        mean_error_eur=("benefit_relevant_error_eur", "mean"),
        median_error_eur=("benefit_relevant_error_eur", "median"),
        p10_error_eur=("benefit_relevant_error_eur", lambda x: x.quantile(0.10)),
        p90_error_eur=("benefit_relevant_error_eur", lambda x: x.quantile(0.90)),
        mean_full_difference_eur=("full_difference_eur", "mean"),
        median_rent_eur=("rent_eur", "median"),
    ).reset_index()
    summary["share_of_full_difference"] = 100.0 * (
        summary["mean_error_eur"] / summary["mean_full_difference_eur"]
    )
    summary["share_error_is_zero"] = (
        grouped["benefit_relevant_error_eur"]
        .apply(lambda x: 100.0 * float((x == 0).mean()))
        .to_numpy()
    )
    return summary


def build_robustness(
    frame: pd.DataFrame,
    stocks: pd.DataFrame | None,
) -> pd.DataFrame:
    """Build the §18 robustness grid over every variation the plan mandates.

    Benchmark variant, data-quality subset, weighting scheme, household size,
    linkage group, and the outlier treatment. Winsorising appears only as a
    display variant: §18 permits clipping for graphical scaling and forbids
    deleting a genuine extreme value merely for being large, so the winsorised
    rows are labelled and never carry a headline.
    """
    rows: list[dict[str, object]] = []
    comparable = frame.query("comparable")
    for variant, variant_rows in comparable.groupby("benchmark_variant"):
        for household_size, cell in iter_household_sizes(variant_rows):
            for subset_name, tiers in _QUALITY_SUBSETS:
                subset = cell.loc[cell["quality_tier"].astype(str).isin(tiers)]
                if subset.empty:
                    continue
                rows.extend(
                    _robustness_rows(
                        subset,
                        stocks,
                        benchmark_variant=str(variant),
                        household_size=household_size,
                        quality_subset=subset_name,
                    ),
                )
    return pd.DataFrame(rows)


def _robustness_rows(
    subset: pd.DataFrame,
    stocks: pd.DataFrame | None,
    *,
    benchmark_variant: str,
    household_size: int,
    quality_subset: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for scheme in _available_schemes(stocks):
        weights = observation_weights(subset, scheme, stocks)
        for group, mask in linkage_groups(subset).items():
            selected = subset.loc[mask]
            if selected.empty:
                continue
            selected_weights = weights.loc[selected.index]
            treatments = {
                "full_sample": selected["proxy_error_eur"],
                "winsorised_for_display_only": winsorise_for_display(
                    selected["proxy_error_eur"],
                ),
            }
            rows.extend(
                {
                    "benchmark_variant": benchmark_variant,
                    "quality_subset": quality_subset,
                    "weighting": str(scheme),
                    "household_size": household_size,
                    "group": str(group),
                    "outlier_treatment": outliers,
                    **describe(
                        selected.assign(proxy_error_eur=values),
                        value_column="proxy_error_eur",
                        weights=selected_weights,
                    ),
                }
                for outliers, values in treatments.items()
            )
    return rows


def _register(
    descriptives: pd.DataFrame,
    breakdowns: pd.DataFrame,
    rent_dependent: pd.DataFrame,
    robustness: pd.DataFrame,
    availability: pd.DataFrame,
) -> None:
    """Record the five §5.2 tables of this module with real numbers in each."""
    pooled = _headline(descriptives, group=str(LinkageGroup.ALL))
    unlinked = _headline(descriptives, group=str(LinkageGroup.EXCLUDING_WOGG_LINKED))
    register_result(
        filename=DESCRIPTIVES_TABLE.name,
        analysis_module="P0.3",
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"The §8.3 statistic block for every benchmark variant, household "
            f"size, linkage group, weighting scheme and §8.1 measure: at "
            f"household size 1 the unweighted median `K − W` is "
            f"{pooled['median']:+,.0f} € over {pooled['n_gemeinden']:,.0f} "
            f"Gemeinden and {unlinked['median']:+,.0f} € over the "
            f"{unlinked['n_gemeinden']:,.0f} that are not WoGG-linked."
        ),
        limitation=(
            "Every row is a distribution over Gemeinden, not over households: "
            "`K` and `W` are caps, so the share of Gemeinden with a non-zero "
            "gap is an upper bound on the share of Bedarfsgemeinschaften the "
            "gap reaches."
        ),
    )

    states = breakdowns.query(
        "household_size == 1 and group == 'all' and breakdown == 'bundesland'",
    )
    lowest = states.loc[states["median"].idxmin()]
    highest = states.loc[states["median"].idxmax()]
    register_result(
        filename=BREAKDOWNS_TABLE.name,
        analysis_module="P0.3",
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"The seven §8.3 and §18 breakdowns in long form; at household size "
            f"1 the Bundesland medians of `K − W` run from "
            f"{lowest['median']:+,.0f} € in {lowest['level']} to "
            f"{highest['median']:+,.0f} € in {highest['level']}, so the "
            f"deviation has a sign that depends on where one looks."
        ),
        limitation=(
            "A Bundesland, Gemeindegrößenklasse or east-west level averages "
            "over Kreise that set their caps independently; none of these "
            "levels is itself a policy parameter, and no ranking of them is a "
            "causal statement."
        ),
    )

    lower_cap_point = RENT_POINT_LABELS[1]
    at_lower = rent_dependent.query("rent_point == @lower_cap_point")
    register_result(
        filename=RENT_GRID_TABLE.name,
        analysis_module="P0.3",
        dataset="proxy_error_rent_grid.parquet",
        script=_SCRIPT,
        interpretation=(
            f"`e(m) = min(m, K) − min(m, W)` is exactly zero in "
            f"{at_lower['share_error_is_zero'].min():.0f} % of observations at "
            f"and below the lower of the two caps and reaches the full cap "
            f"difference only once actual rent clears the higher one, so the "
            f"cap gap is an upper bound on the simulation error, not the error."
        ),
        limitation=(
            "The five rent points are a normalised grid anchored on `K` and "
            "`W`, not an observed rent distribution, so the table says when the "
            "gap would bite and never how many households sit there."
        ),
    )

    tier_a = _robustness_headline(robustness, quality_subset="tier_a_only")
    all_tiers = _robustness_headline(robustness, quality_subset="main_sample_all_tiers")
    register_result(
        filename=ROBUSTNESS_TABLE.name,
        analysis_module="P0.3",
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"The §18 grid over benchmark variant, quality subset, weighting, "
            f"household size, linkage group and outlier treatment: the "
            f"household-size-1 median moves only from "
            f"{tier_a['median']:+,.0f} € on the "
            f"{tier_a['n_gemeinden']:,.0f} tier-A Gemeinden to "
            f"{all_tiers['median']:+,.0f} € on all "
            f"{all_tiers['n_gemeinden']:,.0f}."
        ),
        limitation=(
            "A robustness grid, not a headline: the winsorised rows exist for "
            "graphical scaling only, and §18 forbids removing a genuine extreme "
            "value from any reported figure merely for being large."
        ),
    )

    available = availability["available"].astype(bool)
    register_result(
        filename=WEIGHTING_AVAILABILITY_TABLE.name,
        analysis_module="P0.3",
        dataset="ba_wohnkosten_long.parquet",
        script=_SCRIPT,
        interpretation=(
            f"{int(available.sum())} of the {len(availability)} §8.2 weighting "
            f"schemes were computable in this run; the Bedarfsgemeinschaft "
            f"scheme exists only once the P1.2 BA extract is built, and this "
            f"table is where a reader learns which schemes a given build had."
        ),
        limitation=(
            "The Bedarfsgemeinschaft weights spread a Kreis stock over its "
            "Gemeinden in proportion to population, because the BA publishes no "
            "Gemeinde-level stock; that split is an assumption, not data."
        ),
    )


def _headline(descriptives: pd.DataFrame, group: str) -> pd.Series:
    unweighted = str(WeightingScheme.GEMEINDE_UNWEIGHTED)
    primary = str(PRIMARY_BENCHMARK)
    return descriptives.query(
        "benchmark_variant == @primary and household_size == 1 "
        "and weighting == @unweighted "
        "and measure == 'proxy_error_eur' and group == @group",
    ).iloc[0]


def _robustness_headline(robustness: pd.DataFrame, quality_subset: str) -> pd.Series:
    unweighted = str(WeightingScheme.GEMEINDE_UNWEIGHTED)
    primary = str(PRIMARY_BENCHMARK)
    return robustness.query(
        "benchmark_variant == @primary and household_size == 1 "
        "and weighting == @unweighted "
        "and group == 'all' and outlier_treatment == 'full_sample' "
        "and quality_subset == @quality_subset",
    ).iloc[0]


def _available_schemes(stocks: pd.DataFrame | None) -> tuple[WeightingScheme, ...]:
    schemes = (
        WeightingScheme.GEMEINDE_UNWEIGHTED,
        WeightingScheme.GEMEINDE_POPULATION,
        WeightingScheme.POLICY_REGION_UNWEIGHTED,
    )
    if stocks is None:
        return schemes
    return (*schemes, WeightingScheme.BEDARFSGEMEINSCHAFT)


def _load_stocks() -> pd.DataFrame | None:
    if not BA_WOHNKOSTEN.exists():
        return None
    return load_bedarfsgemeinschaft_stocks(pd.read_parquet(BA_WOHNKOSTEN))


def _weighting_availability(stocks: pd.DataFrame | None) -> pd.DataFrame:
    available = _available_schemes(stocks)
    note = (
        "Kreis Bedarfsgemeinschaft stock at this household size, spread over the "
        "Kreis's Gemeinden in proportion to population; BA publishes no "
        "Gemeinde-level stock."
        if stocks is not None
        else "bld/ba_wohnkosten_long.parquet is absent, so no BG stock exists yet."
    )
    return pd.DataFrame(
        [
            {
                "weighting": str(scheme),
                "available": scheme in available,
                "note": note if scheme is WeightingScheme.BEDARFSGEMEINSCHAFT else "",
            }
            for scheme in WeightingScheme
        ],
    )
