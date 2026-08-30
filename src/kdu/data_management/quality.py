"""The §6.5 automated checks, the §6.6 validation worklist, and the report.

Every check returns a {class}`QualityCheckResult` naming the rows it objects
to. A violated check raises a warn flag on those rows and nothing else: §6.5 is
explicit that a failed plausibility rule never excludes an observation on its
own. Check 5 is descriptive rather than a rule at all, because 210 of the 400
Kreise define Vergleichsräume internally and a Kreis carrying several caps is
the normal case, not an error (D1).

The worklist is the residue: everything §6.6 wants a human to look at, minus
whatever could be settled automatically against the extracted document text.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from kdu.config import ANALYSIS_DATE, MAIN_SAMPLE_HOUSEHOLD_SIZES
from kdu.data_management.harmonise import (
    CENT_TOLERANCE,
    DerivedValueFlag,
    QualityTier,
    balanced_municipalities,
)
from kdu.data_management.provenance import (
    amount_pattern,
    normalise_name,
    split_source_document,
)

# Absolute warn thresholds on a monthly Bruttokaltmiete cap in euro. Nothing
# below or above these can be a plausible cap for a German Gemeinde; they sit
# far outside the observed range so they catch data errors, not tight markets.
ABSOLUTE_CAP_FLOOR_EUR = 150.0
ABSOLUTE_CAP_CEILING_EUR = 2_500.0

# Percentile band, per household size, outside which a cap is flagged as an
# outlier for review.
OUTLIER_PERCENTILES = (0.005, 0.995)

# Minimum size of the §6.6 stratified random sample.
MIN_RANDOM_SAMPLE = 100

# Minimum observations per Bundesland in that sample.
MIN_PER_STATE = 2

# How many of the largest positive and negative K-W deviations to review.
N_EXTREME_DEVIATIONS = 20

RANDOM_SEED = 20260831


@dataclass(frozen=True)
class QualityCheckResult:
    """The outcome of one §6.5 check."""

    check_id: int
    """Position of the check in §6.5's list, 1 to 12."""
    name: str
    """Short English name used as a column and a report row label."""
    description: str
    """What the check asserts, in one sentence."""
    n_evaluated: int
    """Rows the check could be applied to."""
    n_violations: int
    """Rows that failed it."""
    violating_keys: pd.DataFrame = field(repr=False)
    """`ags` and, where applicable, `household_size` of the failing rows."""
    is_descriptive: bool = False
    """Descriptive checks report a number and never raise a warn flag."""
    detail: str = ""
    """Any figure worth carrying into the report alongside the count."""

    @property
    def warn_column(self) -> str:
        """Name of the boolean column this check contributes to the long table."""
        return f"warn_{self.name}"


def run_all_checks(
    long: pd.DataFrame,
    *,
    geometry_ags: frozenset[str],
    lookup_ags: frozenset[str],
    source_valid_from: Mapping[str, frozenset[str]],
) -> tuple[QualityCheckResult, ...]:
    """Run all twelve §6.5 checks and return their results in order."""
    return (
        _check_key_uniqueness(long),
        _check_single_policy_region(long),
        _check_positive_values(long),
        _check_monotonicity(long),
        _check_within_region_dispersion(long),
        _check_missing_household_sizes(long),
        _check_extreme_values(long),
        _check_conflicting_sources(long),
        _check_component_consistency(long),
        _check_ags_conflicts(long, lookup_ags),
        _check_missing_geometry(long, geometry_ags),
        _check_competing_rules(long, source_valid_from),
    )


def add_warn_flags(
    long: pd.DataFrame,
    results: Sequence[QualityCheckResult],
) -> pd.DataFrame:
    """Add one boolean warn column per non-descriptive check, plus a total."""
    flagged = long.copy()
    warn_columns = []
    for result in results:
        if result.is_descriptive:
            continue
        flagged[result.warn_column] = _mark(long, result.violating_keys)
        warn_columns.append(result.warn_column)
    flagged["n_warn_flags"] = flagged[warn_columns].sum(axis=1)
    return flagged


def build_coverage_table(
    long: pd.DataFrame,
    population: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Report coverage by Bundesland, per §6.5's acceptance criteria.

    Args:
        long: The harmonised long table.
        population: Optional `ags` to `population` frame (D8). When given, the
            table also reports the share of inhabitants the main sample covers.

    """
    at_h1 = long[long["household_size"] == 1]
    if population is not None:
        at_h1 = at_h1.merge(
            population[["ags", "population"]],
            on="ags",
            how="left",
            validate="one_to_one",
        )
    main_ags = set(balanced_municipalities(long, MAIN_SAMPLE_HOUSEHOLD_SIZES))
    grouped = at_h1.groupby(["state_code", "state_name"], dropna=False)
    coverage = grouped.agg(
        n_municipalities=("ags", "size"),
        n_policy_regions=("policy_region_id", "nunique"),
        n_with_gross_cold_cap=("kdu_bkc_cap", "count"),
        n_with_net_cold_cap=("net_cold_cap_total", "count"),
    ).reset_index()
    coverage["n_in_main_sample"] = (
        at_h1.assign(in_main=at_h1["ags"].isin(main_ags))
        .groupby(["state_code", "state_name"], dropna=False)["in_main"]
        .sum()
        .to_numpy()
    )
    coverage["n_with_wogg_benchmark"] = (
        at_h1.assign(has_wogg=at_h1["wogg_base_cap"].notna())
        .groupby(["state_code", "state_name"], dropna=False)["has_wogg"]
        .sum()
        .to_numpy()
    )
    coverage["share_in_main_sample"] = (
        coverage["n_in_main_sample"] / coverage["n_municipalities"]
    )
    if population is not None:
        by_state = at_h1.assign(in_main=at_h1["ags"].isin(main_ags)).groupby(
            ["state_code", "state_name"],
            dropna=False,
        )
        coverage["population"] = by_state["population"].sum().to_numpy()
        coverage["population_in_main_sample"] = by_state.apply(
            lambda group: group.loc[group["in_main"], "population"].sum(),
            include_groups=False,
        ).to_numpy()
        coverage["share_population_in_main_sample"] = (
            coverage["population_in_main_sample"] / coverage["population"]
        )
    return coverage.sort_values("state_code").reset_index(drop=True)


def build_validation_worklist(
    long: pd.DataFrame,
    *,
    check_results: Sequence[QualityCheckResult],
    file_index: Mapping[str, Path],
    text_index: Mapping[str, Path],
    neighbour_jump_flags: pd.DataFrame,
    seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    """Assemble §6.6's manual validation worklist and pre-check what it can.

    The worklist is the union of the six §6.6 strata. Every entry that cites a
    document with an extracted text layer is checked automatically by looking
    for its euro amount in that text; `auto_check_result` records the outcome,
    so the manual remainder is exactly the rows machine evidence cannot settle.

    Args:
        long: The harmonised long table, keyed `ags × household_size`.
        check_results: Every §6.5 check result, for the strata read off them.
        file_index: Corpus filename to path, for the automatic amount check.
        text_index: Corpus filename to extracted `.txt`, same purpose.
        neighbour_jump_flags: `bld/neighbour_jump_flags.parquet`, the real
            cross-border cap-step flag the `large_neighbour_jump` stratum
            selects on.
        seed: Seed of the stratified random sample.

    """
    strata = _collect_worklist_strata(
        long,
        check_results,
        neighbour_jump_flags=neighbour_jump_flags,
        seed=seed,
    )
    worklist = (
        pd.concat(strata, ignore_index=True)
        .groupby(["ags", "household_size"], as_index=False)
        .agg(
            reason=("reason", lambda values: "; ".join(sorted(set(values)))),
        )
    )
    columns = [
        "ags",
        "household_size",
        "municipality_name",
        "state_name",
        "policy_region_id",
        "policy_region_name",
        "kdu_bkc_cap",
        "wogg_base_cap",
        "quality_tier",
        "derived_value_flag",
        "calculation_method",
        "source_document",
        "notes",
    ]
    worklist = worklist.merge(
        long[columns],
        on=["ags", "household_size"],
        how="left",
        validate="one_to_one",
    )
    checked = _auto_check_amounts(worklist, file_index, text_index)
    worklist = pd.concat([worklist, checked], axis=1)
    worklist["source_paths"] = worklist["source_document"].map(
        lambda document: _source_paths(document, file_index),
    )
    worklist["figure_to_check"] = worklist.apply(
        lambda row: (
            f"Bruttokaltmiete cap for h={row['household_size']}: "
            f"{row['kdu_bkc_cap']:.2f} EUR"
            if pd.notna(row["kdu_bkc_cap"])
            else f"absence of a cap for h={row['household_size']}"
        ),
        axis=1,
    )
    return worklist.sort_values(["reason", "ags", "household_size"]).reset_index(
        drop=True,
    )


def build_data_dictionary(
    long: pd.DataFrame,
    descriptions: Mapping[str, str],
) -> pd.DataFrame:
    """Describe every column of the long table, with its filled share."""
    records = []
    for column in long.columns:
        values = long[column]
        records.append(
            {
                "variable": column,
                "dtype": str(values.dtype),
                "description": descriptions.get(column, ""),
                "n_non_null": int(values.notna().sum()),
                "share_non_null": float(values.notna().mean()),
                "n_distinct": int(values.nunique(dropna=True)),
                "example": _example_value(values),
            },
        )
    return pd.DataFrame.from_records(records)


def build_quality_report(
    long: pd.DataFrame,
    *,
    check_results: Sequence[QualityCheckResult],
    coverage: pd.DataFrame,
    unmatched_sources: pd.DataFrame,
    disagreements: pd.DataFrame,
    worklist: pd.DataFrame,
) -> str:
    """Render the Gate 1 quality report as a self-contained HTML page."""
    at_h1 = long[long["household_size"] == 1]
    sections = [
        _report_header(long),
        _report_section(
            "Quality tiers",
            "Tier A needs the printed cap located in the source's own text; "
            "tier B needs it reproducible from printed components or held in a "
            "primary document without a text layer; everything else is tier C.",
            _bar_of_counts(long["quality_tier"], "quality_tier", "Rows"),
        ),
        _report_section(
            "How each cap was established",
            "`unknown` is a real state, not a failure to try: roughly half the "
            "cited documents have no extracted text layer to check against.",
            _bar_of_counts(
                long["derived_value_flag"],
                "derived_value_flag",
                "Rows",
            ),
        ),
        _report_section(
            "Cap distribution by household size",
            "Bruttokaltmiete caps in euro per month, all Gemeinden with a cap.",
            _cap_distribution(long),
        ),
        _report_section(
            "Coverage by Bundesland",
            "Gemeinden with a Bruttokaltmiete cap, against all Gemeinden.",
            _coverage_figure(coverage),
        ),
        _report_section(
            "Automated checks (§6.5)",
            "A violated check raises a warn flag. It never excludes a row.",
            _table_html(_check_summary(check_results)),
        ),
        _report_section(
            "Unresolved source citations",
            "Citations that name a document the corpus does not hold. These are "
            "reported, never matched by similarity.",
            _table_html(
                unmatched_sources.loc[~unmatched_sources["has_any_file"]].head(50),
            ),
        ),
        _report_section(
            "WoGG-link detector disagreements (D7)",
            f"{len(disagreements)} Gemeinden where the notes detector and the "
            "K/W ratio detector disagree. Listed for manual review; neither "
            "detector overrides the other.",
            _table_html(disagreements.head(50)),
        ),
        _report_section(
            "Validation worklist (§6.6)",
            f"{len(worklist)} observations selected for validation, of which "
            f"{int(worklist['auto_check_result'].eq('pass').sum())} passed the "
            "automatic text check, "
            f"{int(worklist['auto_check_result'].eq('fail').sum())} failed it, "
            f"and {int(worklist['auto_check_result'].eq('manual').sum())} need "
            "a human to open the document.",
            _table_html(
                worklist["auto_check_result"].value_counts().reset_index(),
            ),
        ),
        _report_section(
            "Coverage headline",
            "",
            _table_html(_headline_table(at_h1, long)),
        ),
    ]
    return _wrap_html("KdU data quality report", sections)


def _check_key_uniqueness(long: pd.DataFrame) -> QualityCheckResult:
    key = ["ags", "household_size", "analysis_date"]
    duplicated = long[long.duplicated(subset=key, keep=False)]
    return QualityCheckResult(
        check_id=1,
        name="duplicate_key",
        description="ags, household_size and analysis_date identify a row uniquely.",
        n_evaluated=len(long),
        n_violations=len(duplicated),
        violating_keys=duplicated[["ags", "household_size"]],
    )


def _check_single_policy_region(long: pd.DataFrame) -> QualityCheckResult:
    per_ags = long.groupby("ags")["policy_region_id"].nunique()
    offending = per_ags[per_ags > 1].index
    return QualityCheckResult(
        check_id=2,
        name="ambiguous_policy_region",
        description="Every Gemeinde belongs to exactly one policy region.",
        n_evaluated=int(per_ags.size),
        n_violations=len(offending),
        violating_keys=long.loc[long["ags"].isin(offending), ["ags", "household_size"]],
    )


def _check_positive_values(long: pd.DataFrame) -> QualityCheckResult:
    cap = long["kdu_bkc_cap"]
    bad = long[cap.notna() & (~np.isfinite(cap.astype("float64")) | cap.le(0))]
    return QualityCheckResult(
        check_id=3,
        name="non_positive_cap",
        description="Every cap that exists is a finite, strictly positive amount.",
        n_evaluated=int(cap.notna().sum()),
        n_violations=len(bad),
        violating_keys=bad[["ags", "household_size"]],
    )


def _check_monotonicity(long: pd.DataFrame) -> QualityCheckResult:
    ordered = long.sort_values(["ags", "household_size"])
    steps = ordered.groupby("ags")["kdu_bkc_cap"].diff()
    falling_ags = ordered.loc[steps.lt(0), "ags"].unique()
    flat_ags = ordered.loc[steps.eq(0), "ags"].unique()
    violating = ordered.loc[ordered["ags"].isin(falling_ags), ["ags", "household_size"]]
    return QualityCheckResult(
        check_id=4,
        name="non_monotone_in_household_size",
        description="The cap never falls as the household grows.",
        n_evaluated=int(
            ordered.groupby("ags")["kdu_bkc_cap"].count().gt(1).sum().item()
        ),
        n_violations=len(falling_ags),
        violating_keys=violating,
        detail=(
            f"{len(falling_ags)} Gemeinden fall at least once; "
            f"{len(flat_ags)} have at least one flat step."
        ),
    )


def _check_within_region_dispersion(long: pd.DataFrame) -> QualityCheckResult:
    at_h1 = long[long["household_size"] == 1]
    per_region = at_h1.groupby("policy_region_id")["kdu_bkc_cap"].nunique()
    dispersed = per_region[per_region > 1]
    return QualityCheckResult(
        check_id=5,
        name="within_region_dispersion",
        description=(
            "Descriptive only (D1): how many Kreise carry more than one cap at "
            "h=1, because they define Vergleichsräume internally."
        ),
        n_evaluated=int(per_region.size),
        n_violations=int(dispersed.size),
        violating_keys=at_h1.loc[
            at_h1["policy_region_id"].isin(dispersed.index),
            ["ags", "household_size"],
        ],
        is_descriptive=True,
        detail=(
            f"{dispersed.size} of {per_region.size} Kreise carry more than one "
            f"distinct cap at h=1."
        ),
    )


def _check_missing_household_sizes(long: pd.DataFrame) -> QualityCheckResult:
    per_ags = long.groupby("ags")["kdu_bkc_cap"].count()
    has_any = per_ags[per_ags > 0]
    incomplete = has_any[has_any < long["household_size"].nunique()].index
    return QualityCheckResult(
        check_id=6,
        name="incomplete_household_sizes",
        description="A Gemeinde with any cap has one for every household size.",
        n_evaluated=int(has_any.size),
        n_violations=len(incomplete),
        violating_keys=long.loc[
            long["ags"].isin(incomplete),
            ["ags", "household_size"],
        ],
    )


def _check_extreme_values(long: pd.DataFrame) -> QualityCheckResult:
    low, high = OUTLIER_PERCENTILES
    per_size = long.groupby("household_size")["kdu_bkc_cap"]
    bounds = per_size.quantile(q=np.array(OUTLIER_PERCENTILES))
    cap = long["kdu_bkc_cap"]
    lower = long["household_size"].map(bounds.xs(low, level=1))
    upper = long["household_size"].map(bounds.xs(high, level=1))
    outside = cap.notna() & (
        cap.lt(lower)
        | cap.gt(upper)
        | cap.lt(ABSOLUTE_CAP_FLOOR_EUR)
        | cap.gt(ABSOLUTE_CAP_CEILING_EUR)
    )
    return QualityCheckResult(
        check_id=7,
        name="extreme_cap",
        description=(
            "Caps sit inside the 0.5th to 99.5th percentile of their household "
            f"size and inside [{ABSOLUTE_CAP_FLOOR_EUR:.0f}, "
            f"{ABSOLUTE_CAP_CEILING_EUR:.0f}] EUR."
        ),
        n_evaluated=int(cap.notna().sum()),
        n_violations=int(outside.sum()),
        violating_keys=long.loc[outside, ["ags", "household_size"]],
    )


def _check_conflicting_sources(long: pd.DataFrame) -> QualityCheckResult:
    key = ["source_document", "kdu_region", "household_size"]
    with_source = long.dropna(subset=["source_document", "kdu_region"])
    per_key = with_source.groupby(key)["kdu_bkc_cap"].nunique()
    conflicting = per_key[per_key > 1].index
    mask = pd.MultiIndex.from_frame(with_source[key]).isin(conflicting)
    return QualityCheckResult(
        check_id=8,
        name="conflicting_source_values",
        description=(
            "One source document gives one cap per region and household size."
        ),
        n_evaluated=int(per_key.size),
        n_violations=len(conflicting),
        violating_keys=with_source.loc[mask, ["ags", "household_size"]],
    )


def _check_component_consistency(long: pd.DataFrame) -> QualityCheckResult:
    gross = long["gross_cold_cap_total"]
    components = long["net_cold_cap_total"] + long["cold_opex_cap_total"]
    both = gross.notna() & components.notna()
    inconsistent = both & (gross - components).abs().gt(CENT_TOLERANCE)
    return QualityCheckResult(
        check_id=9,
        name="component_total_mismatch",
        description=(
            "Where both are published, the Bruttokaltmiete equals the "
            "Nettokaltmiete plus the cold-cost cap."
        ),
        n_evaluated=int(both.sum()),
        n_violations=int(inconsistent.sum()),
        violating_keys=long.loc[inconsistent, ["ags", "household_size"]],
    )


def _check_ags_conflicts(
    long: pd.DataFrame,
    lookup_ags: frozenset[str],
) -> QualityCheckResult:
    unknown = long[~long["ags"].isin(lookup_ags)]
    return QualityCheckResult(
        check_id=10,
        name="ags_not_in_gebietsstand",
        description="Every AGS exists in the lookup table's Gebietsstand.",
        n_evaluated=int(long["ags"].nunique()),
        n_violations=int(unknown["ags"].nunique()),
        violating_keys=unknown[["ags", "household_size"]],
    )


def _check_missing_geometry(
    long: pd.DataFrame,
    geometry_ags: frozenset[str],
) -> QualityCheckResult:
    missing = long[~long["ags"].isin(geometry_ags)]
    return QualityCheckResult(
        check_id=11,
        name="no_geometry",
        description="Every Gemeinde in the table has a boundary polygon.",
        n_evaluated=int(long["ags"].nunique()),
        n_violations=int(missing["ags"].nunique()),
        violating_keys=missing[["ags", "household_size"]],
    )


def _check_competing_rules(
    long: pd.DataFrame,
    source_valid_from: Mapping[str, frozenset[str]],
) -> QualityCheckResult:
    competing = {
        document
        for document, dates in source_valid_from.items()
        if len({date for date in dates if isinstance(date, str)}) > 1
    }
    mask = long["source_document"].isin(competing)
    return QualityCheckResult(
        check_id=12,
        name="competing_rules_at_analysis_date",
        description=(
            "A Gemeinde's citation resolves to documents that take effect on "
            "one date, not several."
        ),
        n_evaluated=int(long["source_document"].notna().sum()),
        n_violations=int(mask.sum()),
        violating_keys=long.loc[mask, ["ags", "household_size"]],
    )


def _collect_worklist_strata(
    long: pd.DataFrame,
    check_results: Sequence[QualityCheckResult],
    *,
    neighbour_jump_flags: pd.DataFrame,
    seed: int,
) -> list[pd.DataFrame]:
    rng = np.random.default_rng(seed)
    strata = [
        _stratified_random_sample(long, rng),
        _label(long[long["quality_tier"].eq(QualityTier.C.value)], "quality_tier_c"),
        _extreme_deviations(long),
        _label(
            _keys_of(check_results, "non_monotone_in_household_size"),
            "non_monotone",
        ),
        _neighbour_jumps(long, neighbour_jump_flags),
        _label(
            long[long["derived_value_flag"].eq(DerivedValueFlag.UNKNOWN.value)]
            .groupby("policy_region_id", group_keys=False)
            .head(1),
            "derivation_unverified",
        ),
    ]
    return [frame for frame in strata if not frame.empty]


def _stratified_random_sample(
    long: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    pool = long[long["kdu_bkc_cap"].notna()]
    per_state = max(
        MIN_PER_STATE,
        -(-MIN_RANDOM_SAMPLE // max(pool["state_code"].nunique(), 1)),
    )
    picked = []
    for _, group in pool.groupby("state_code"):
        size = min(per_state, len(group))
        positions = rng.choice(len(group), size=size, replace=False)
        picked.append(group.iloc[positions])
    sample = pd.concat(picked, ignore_index=True)
    return _label(sample, "stratified_random")


def _extreme_deviations(long: pd.DataFrame) -> pd.DataFrame:
    comparable = long[
        long["kdu_bkc_cap"].notna() & long["wogg_base_cap"].notna()
    ].copy()
    comparable["deviation"] = comparable["kdu_bkc_cap"] - comparable["wogg_base_cap"]
    ordered = comparable.sort_values("deviation")
    extreme = pd.concat(
        [ordered.head(N_EXTREME_DEVIATIONS), ordered.tail(N_EXTREME_DEVIATIONS)],
    )
    return _label(extreme, "extreme_kdu_wogg_deviation")


def _neighbour_jumps(long: pd.DataFrame, flags: pd.DataFrame) -> pd.DataFrame:
    """Select Gemeinden whose cap steps unusually far across a real shared border.

    `flags` is `bld/neighbour_jump_flags.parquet`, keyed `ags × household_size`,
    where `large_neighbour_jump` compares the largest cap step to a directly
    adjacent Gemeinde in another policy region against the 95th percentile of
    all such cross-border steps at that household size. A Gemeinde with no
    eligible cross-border neighbour carries `has_cross_border_neighbour = False`
    and is never flagged: no evidence is not evidence of no jump.
    """
    flagged = flags.loc[flags["large_neighbour_jump"], ["ags", "household_size"]]
    selected = long.merge(flagged, on=["ags", "household_size"], how="inner")
    return _label(selected, "large_neighbour_jump")


def _auto_check_amounts(
    worklist: pd.DataFrame,
    file_index: Mapping[str, Path],
    text_index: Mapping[str, Path],
) -> pd.DataFrame:
    cache: dict[str, list[str]] = {}
    readable: dict[str, bool] = {}
    results = []
    evidence = []
    for document, amount in zip(
        worklist["source_document"], worklist["kdu_bkc_cap"], strict=True
    ):
        if not isinstance(document, str) or pd.isna(amount):
            results.append("manual")
            evidence.append("no_document_or_no_amount")
            continue
        if document not in cache:
            cache[document] = _texts_for(document, file_index, text_index)
            readable[document] = _texts_carry_any_amount(
                cache[document],
                worklist.loc[
                    worklist["source_document"].eq(document),
                    "kdu_bkc_cap",
                ],
            )
        texts = cache[document]
        if not texts:
            results.append("manual")
            evidence.append("no_text_layer")
            continue
        if not readable[document]:
            results.append("manual")
            evidence.append("document_text_carries_no_amounts")
            continue
        pattern = amount_pattern(float(amount))
        if any(pattern.search(text) for text in texts):
            results.append("pass")
            evidence.append("amount_found_in_extracted_text")
        else:
            results.append("fail")
            evidence.append("amount_absent_from_extracted_text")
    return pd.DataFrame(
        {
            "auto_check_result": pd.Series(
                results, index=worklist.index, dtype="string"
            ),
            "auto_check_evidence": pd.Series(
                evidence, index=worklist.index, dtype="string"
            ),
        },
    )


def _texts_carry_any_amount(texts: Sequence[str], amounts: pd.Series) -> bool:
    """Whether the extraction contains at least one of the document's own caps.

    When it contains none, the table is an image or a failed scan, so a missing
    amount says nothing about the recorded value.
    """
    return any(
        amount_pattern(float(amount)).search(text)
        for amount in amounts.dropna().unique()
        for text in texts
    )


def _texts_for(
    document: str,
    file_index: Mapping[str, Path],
    text_index: Mapping[str, Path],
) -> list[str]:
    keys = [
        normalise_name(Path(component).stem)
        for component in split_source_document(document, file_index)
    ]
    return [
        text_index[key].read_text(errors="replace") for key in keys if key in text_index
    ]


def _source_paths(document: object, file_index: Mapping[str, Path]) -> str:
    if not isinstance(document, str):
        return ""
    paths = [
        str(file_index[normalise_name(component)])
        for component in split_source_document(document, file_index)
        if normalise_name(component) in file_index
    ]
    return " | ".join(paths)


def _keys_of(results: Sequence[QualityCheckResult], name: str) -> pd.DataFrame:
    for result in results:
        if result.name == name:
            return result.violating_keys
    return pd.DataFrame(columns=["ags", "household_size"])


def _label(frame: pd.DataFrame, reason: str) -> pd.DataFrame:
    selected = frame[["ags", "household_size"]].drop_duplicates().copy()
    selected["reason"] = reason
    return selected


def _mark(long: pd.DataFrame, keys: pd.DataFrame) -> pd.Series:
    if keys.empty:
        return pd.Series(data=False, index=long.index, dtype=bool)
    marked = pd.MultiIndex.from_frame(long[["ags", "household_size"]]).isin(
        pd.MultiIndex.from_frame(keys[["ags", "household_size"]].drop_duplicates()),
    )
    return pd.Series(marked, index=long.index, dtype=bool)


def _check_summary(results: Sequence[QualityCheckResult]) -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "check": result.check_id,
                "name": result.name,
                "kind": "descriptive" if result.is_descriptive else "rule",
                "evaluated": result.n_evaluated,
                "violations": result.n_violations,
                "description": result.description,
                "detail": result.detail,
            }
            for result in results
        ],
    )


def _headline_table(at_h1: pd.DataFrame, long: pd.DataFrame) -> pd.DataFrame:
    main_ags = balanced_municipalities(long, MAIN_SAMPLE_HOUSEHOLD_SIZES)
    with_benchmark = long[long["ags"].isin(main_ags) & long["wogg_base_cap"].notna()][
        "ags"
    ].nunique()
    return pd.DataFrame(
        [
            ("Gemeinden in the table", at_h1["ags"].nunique()),
            ("Policy regions (Kreise)", at_h1["policy_region_id"].nunique()),
            ("Gemeinden with a Bruttokaltmiete cap", int(at_h1["kdu_bkc_cap"].count())),
            ("Gemeinden in analysis_sample_main", len(main_ags)),
            ("Gemeinden in main with a WoGG benchmark", with_benchmark),
        ],
        columns=["measure", "value"],
    )


def _bar_of_counts(values: pd.Series, label: str, y_title: str) -> go.Figure:
    counts = values.value_counts(dropna=False).sort_index()
    figure = go.Figure(
        go.Bar(
            x=counts.index.astype(str),
            y=counts.to_numpy(),
            marker_color="#6b7280",
            text=counts.to_numpy(),
            textposition="outside",
        ),
    )
    figure.update_layout(
        xaxis_title=label,
        yaxis_title=y_title,
        template="plotly_white",
        height=340,
        margin={"l": 60, "r": 20, "t": 20, "b": 50},
        showlegend=False,
    )
    return figure


def _cap_distribution(long: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    for household_size, group in long.groupby("household_size"):
        figure.add_trace(
            go.Box(
                y=group["kdu_bkc_cap"].dropna(),
                name=f"h={household_size}",
                marker_color="#6b7280",
                boxpoints=False,
            ),
        )
    figure.update_layout(
        yaxis_title="kdu_bkc_cap (EUR per month)",
        template="plotly_white",
        height=380,
        margin={"l": 70, "r": 20, "t": 20, "b": 40},
        showlegend=False,
    )
    return figure


def _coverage_figure(coverage: pd.DataFrame) -> go.Figure:
    ordered = coverage.sort_values("share_in_main_sample")
    figure = go.Figure(
        go.Bar(
            x=ordered["share_in_main_sample"],
            y=ordered["state_name"],
            orientation="h",
            marker_color="#6b7280",
        ),
    )
    figure.update_layout(
        xaxis_title="Share of Gemeinden in analysis_sample_main",
        xaxis_tickformat=".0%",
        template="plotly_white",
        height=460,
        margin={"l": 200, "r": 20, "t": 20, "b": 50},
        showlegend=False,
    )
    return figure


def _report_header(long: pd.DataFrame) -> str:
    return (
        "<h1>KdU data quality report</h1>"
        f"<p class='lede'>Module P0.1, Analysestichtag {ANALYSIS_DATE.isoformat()}. "
        f"{long['ags'].nunique():,} Gemeinden, {len(long):,} rows keyed by AGS and "
        "household size.</p>"
    )


def _report_section(title: str, lede: str, body: object) -> str:
    rendered = (
        body.to_html(full_html=False, include_plotlyjs="cdn")
        if isinstance(body, go.Figure)
        else str(body)
    )
    lede_html = f"<p class='lede'>{lede}</p>" if lede else ""
    return f"<section><h2>{title}</h2>{lede_html}{rendered}</section>"


def _table_html(frame: pd.DataFrame) -> str:
    return frame.to_html(index=False, border=0, classes="data", na_rep="")


def _wrap_html(title: str, sections: Sequence[str]) -> str:
    style = (
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        "max-width:1100px;margin:2rem auto;padding:0 1.5rem;color:#111;}"
        "h1{font-size:1.6rem;}h2{font-size:1.15rem;margin-top:2.5rem;}"
        ".lede{color:#4b5563;font-size:0.95rem;max-width:70ch;}"
        "table.data{border-collapse:collapse;font-size:0.85rem;width:100%;"
        "overflow-x:auto;display:block;}"
        "table.data th,table.data td{border-bottom:1px solid #e5e7eb;padding:4px 8px;"
        "text-align:left;vertical-align:top;}"
        "table.data th{background:#f9fafb;}"
    )
    body = "".join(sections)
    return (
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{title}</title><style>{style}</style></head>"
        f"<body>{body}</body></html>"
    )


def _example_value(values: pd.Series) -> str:
    non_null = values.dropna()
    return "" if non_null.empty else str(non_null.iloc[0])[:60]
