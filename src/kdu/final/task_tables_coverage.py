"""Write Tables 1 and 2 of §19 and register them in the results manifest.

Table 1 reports coverage and data quality by Bundesland against a denominator
of every Gemeinde in Germany. Table 2 reports the proxy error by household
size, and carries every household size three times over — pooled, without the
WoGG-linked Gemeinden, and for those alone — because D7 forbids presenting the
pooled median as an empirical regularity.

Each table is written as a CSV for downstream use and as a Markdown rendering
for reading.
"""

from pathlib import Path
from typing import Annotated, cast

import pandas as pd
from pytask import Product

from kdu.analysis.proxy_error import (
    PRIMARY_BENCHMARK,
    BenchmarkVariant,
    LinkageGroup,
    coverage_by_state,
    linkage_overlap,
    load_bedarfsgemeinschaft_stocks,
    proxy_error_by_household_size,
)
from kdu.analysis.task_proxy_error import (
    BA_WOHNKOSTEN,
    PROXY_ERROR_FRAME,
)
from kdu.config import DATA_CATALOG, TABLES, WeightingScheme
from kdu.final.manifest import register_result

_ANALYSIS_SAMPLE_MAIN = cast("Path", DATA_CATALOG["analysis_sample_main"])
_MUNICIPALITY_CROSSWALK = cast("Path", DATA_CATALOG["municipality_crosswalk"])

TABLE_ONE_CSV = TABLES / "table1_coverage_and_quality.csv"
TABLE_ONE_MARKDOWN = TABLES / "table1_coverage_and_quality.md"
TABLE_TWO_CSV = TABLES / "table2_proxy_error_by_household_size.csv"
TABLE_TWO_MARKDOWN = TABLES / "table2_proxy_error_by_household_size.md"

_SCRIPT = "src/kdu/final/task_tables_coverage.py"

# The three linkage groups Table 2 always shows together (D7).
_REPORTED_GROUPS: tuple[LinkageGroup, ...] = (
    LinkageGroup.ALL,
    LinkageGroup.EXCLUDING_WOGG_LINKED,
    LinkageGroup.WOGG_LINKED_ONLY,
)

_GROUP_LABELS = {
    str(LinkageGroup.ALL): "All Gemeinden",
    str(LinkageGroup.EXCLUDING_WOGG_LINKED): "Excluding WoGG-linked",
    str(LinkageGroup.WOGG_LINKED_ONLY): "WoGG-linked only",
}

_TABLE_ONE_COLUMNS: dict[str, str] = {
    "bundesland": "Bundesland",
    "n_gemeinden_total": "Gemeinden",
    "n_gemeinden_main_sample": "In main sample",
    "share_gemeinden_main_sample": "Share of Gemeinden (%)",
    "share_population_covered": "Population covered (%)",
    "n_policy_regions_main_sample": "Policy regions",
    "share_quality_a": "Quality A (%)",
    "share_quality_b": "Quality B (%)",
    "share_quality_c": "Quality C (%)",
    "share_published_gross_cold": "Published Bruttokaltmiete (%)",
    "n_without_wogg_benchmark": "No Wohngeld benchmark",
}

_TABLE_TWO_COLUMNS: dict[str, str] = {
    "household_size": "Household size",
    "group_label": "Group",
    "n_gemeinden": "Gemeinden",
    "median_eur": "Median D (€)",
    "mean_eur": "Mean D (€)",
    "median_log": "Median L (log points)",
    "mean_absolute_eur": "Mean |D| (€)",
    "p10_eur": "P10 D (€)",
    "p90_eur": "P90 D (€)",
    "share_abs_gt_50": "|D| > 50 € (%)",
    "share_abs_gt_100": "|D| > 100 € (%)",
    "share_at_safety_markup_pct": "At 10 % markup (%)",
}


def task_tables_coverage(
    sample_main_file: Path = _ANALYSIS_SAMPLE_MAIN,
    crosswalk_file: Path = _MUNICIPALITY_CROSSWALK,
    proxy_error_file: Path = PROXY_ERROR_FRAME,
    table_one_csv: Annotated[Path, Product] = TABLE_ONE_CSV,
    table_one_markdown: Annotated[Path, Product] = TABLE_ONE_MARKDOWN,
    table_two_csv: Annotated[Path, Product] = TABLE_TWO_CSV,
    table_two_markdown: Annotated[Path, Product] = TABLE_TWO_MARKDOWN,
) -> None:
    """Write Tables 1 and 2 as CSV and Markdown, and register both."""
    table_one = coverage_by_state(
        sample=pd.read_parquet(sample_main_file),
        crosswalk=pd.read_parquet(crosswalk_file),
    )
    frame = pd.read_parquet(proxy_error_file)
    stocks = (
        load_bedarfsgemeinschaft_stocks(pd.read_parquet(BA_WOHNKOSTEN))
        if BA_WOHNKOSTEN.exists()
        else None
    )
    table_two = build_table_two(frame, stocks)

    table_one_csv.parent.mkdir(parents=True, exist_ok=True)
    table_one.to_csv(table_one_csv, index=False)
    table_one_markdown.write_text(
        render_table_one(table_one),
        encoding="utf-8",
    )
    table_two.to_csv(table_two_csv, index=False)
    table_two_markdown.write_text(
        render_table_two(table_two, linkage_overlap(frame)),
        encoding="utf-8",
    )

    _register(table_one, table_two)


def build_table_two(
    frame: pd.DataFrame,
    bedarfsgemeinschaft_stocks: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Assemble Table 2 across household sizes, weightings, and linkage groups.

    The primary benchmark of D6 carries the headline; the base-plus-Klima rows
    travel with it as the mandated §18 robustness rather than in a separate
    file, so a reader cannot see one without the other.
    """
    pieces = []
    for variant in BenchmarkVariant:
        variant_name = str(variant)
        cell = frame.loc[frame["benchmark_variant"] == variant_name]
        for scheme in WeightingScheme:
            if (
                scheme is WeightingScheme.BEDARFSGEMEINSCHAFT
                and bedarfsgemeinschaft_stocks is None
            ):
                continue
            piece = proxy_error_by_household_size(
                cell,
                weighting=scheme,
                bedarfsgemeinschaft_stocks=bedarfsgemeinschaft_stocks,
            )
            piece.insert(0, "benchmark_variant", variant_name)
            pieces.append(piece)
    table = pd.concat(pieces, ignore_index=True)
    table["group_label"] = table["group"].map(_GROUP_LABELS).fillna(table["group"])
    return table.sort_values(
        ["benchmark_variant", "weighting", "household_size", "group"],
        kind="stable",
    ).reset_index(drop=True)


def render_table_one(table: pd.DataFrame) -> str:
    """Render Table 1 as Markdown with its coverage note."""
    body = table.loc[:, list(_TABLE_ONE_COLUMNS)].rename(columns=_TABLE_ONE_COLUMNS)
    total = table["n_gemeinden_total"].sum()
    in_sample = table["n_gemeinden_main_sample"].sum()
    without_benchmark = table["n_without_wogg_benchmark"].sum()
    lines = [
        "# Table 1 — Data coverage and quality by Bundesland",
        "",
        to_markdown(body),
        "",
        (
            f"Denominator is every Gemeinde in Germany ({total:,}); "
            f"{in_sample:,} are in the main sample, balanced over household "
            f"sizes 1 to 4 (D3). Of those, {without_benchmark:,} have no "
            "statutory Mietenstufe and therefore no Wohngeld benchmark, so "
            f"every K−W comparison runs on {in_sample - without_benchmark:,} "
            "Gemeinden (A2)."
        ),
        (
            "A Gemeinde's quality tier is the worst tier over its household "
            "sizes. D3, not §6.4, defines the main sample, so tier-C Gemeinden "
            "sit inside it and the tier-A-only robustness row of §18 stays "
            "mandatory (A8)."
        ),
    ]
    return "\n".join(lines) + "\n"


def render_table_two(table: pd.DataFrame, overlap: pd.DataFrame) -> str:
    """Render the primary, unweighted panel of Table 2 as Markdown.

    Args:
        table: The full Table 2, every benchmark variant and weighting.
        overlap: `linkage_overlap` of the proxy-error frame, which supplies the
            note's counts so it names the group the rows actually use.

    """
    panel = table.loc[
        (table["benchmark_variant"] == str(PRIMARY_BENCHMARK))
        & (table["weighting"] == str(WeightingScheme.GEMEINDE_UNWEIGHTED))
        & table["group"].isin([str(group) for group in _REPORTED_GROUPS])
    ]
    body = panel.loc[:, list(_TABLE_TWO_COLUMNS)].rename(columns=_TABLE_TWO_COLUMNS)
    lines = [
        "# Table 2 — Proxy error by household size",
        "",
        (
            "`D = K − W` in euro per month, `L = 100 (log K − log W)` in log "
            "points. `K` is the local maximum recognisable Bruttokaltmiete, `W` "
            "the base Wohngeld Höchstbetrag of § 12 WoGG (D6). Unweighted "
            "Gemeinden; the population, policy-region, and Bedarfsgemeinschaft "
            "weightings are in the CSV alongside this rendering."
        ),
        "",
        to_markdown(body),
        "",
        _linkage_note(overlap),
        (
            "Household size 5 is computed on the Gemeinden balanced over sizes "
            "1 to 5 and carries its own N; sizes 1 to 4 are the fixed main "
            "sample (D3)."
        ),
    ]
    return "\n".join(lines) + "\n"


def _linkage_note(overlap: pd.DataFrame) -> str:
    """Spell out which WoGG-linkage group the `Excluding WoGG-linked` row drops.

    Two groups are in play and they are not the same Gemeinden (A12, A22), so
    the note names the one the row uses, gives its count, and attributes the
    `K = 1.10 × W` identity to the group that identity actually defines.
    """
    row = overlap.loc[overlap["household_size"] == 1].iloc[0]
    return (
        "Every household size appears three times because D7 forbids reading "
        "the pooled row as an empirical regularity. The `Excluding WoGG-linked` "
        "row drops `linked_union` — `wogg_linked_flag`, the union of D7's "
        "notes-regex and ratio detectors, "
        f"{row['n_linked_union']:,.0f} Gemeinden at household size 1. The "
        "`K = 1.10 × W` identity of the BSG case law belongs to a different "
        "group, `exact_ratio`: the "
        f"{row['n_exact_ratio']:,.0f} Gemeinden whose `K/W` sits exactly on the "
        "10 % Sicherheitszuschlag at this household size, whose share the "
        "`At 10 % markup (%)` column gives. The two are broader than, and not a "
        f"superset of, one another: {row['n_both']:,.0f} Gemeinden are in both, "
        f"{row['n_union_only']:,.0f} in `linked_union` only, and "
        f"{row['n_exact_only']:,.0f} in `exact_ratio` only."
    )


def to_markdown(table: pd.DataFrame, *, decimals: int = 1) -> str:
    """Render `table` as a GitHub-flavoured Markdown table.

    Written out rather than delegated so the build needs no extra dependency
    for what is three lines of string joining.
    """
    rendered = (
        table.round(decimals)
        .astype("string")
        .fillna("")
        .map(lambda cell: cell.replace("|", r"\|"))
    )
    columns = [str(column).replace("|", r"\|") for column in rendered.columns]
    header = f"| {' | '.join(columns)} |"
    rule = f"| {' | '.join('---' for _ in rendered.columns)} |"
    rows = [f"| {' | '.join(row)} |" for row in rendered.to_numpy().tolist()]
    return "\n".join([header, rule, *rows])


def _register(table_one: pd.DataFrame, table_two: pd.DataFrame) -> None:
    covered = table_one["share_population_covered"]
    lowest = table_one.loc[covered.idxmin()]
    register_result(
        filename=TABLE_ONE_CSV.name,
        analysis_module="P0.3",
        dataset="analysis_sample_main.parquet",
        script=_SCRIPT,
        interpretation=(
            f"The main sample holds {table_one['n_gemeinden_main_sample'].sum():,} "
            f"of {table_one['n_gemeinden_total'].sum():,} Gemeinden and "
            f"{_population_share(table_one):.1%} of the population, but "
            "coverage ranges from "
            f"{covered.min():.1f} % in {lowest['bundesland']} to 100 % in "
            "several Bundesländer."
        ),
        limitation=(
            "Coverage is uneven by Bundesland, so any nationwide figure is a "
            "weighted statement about the Kreise that publish a Bruttokaltmiete "
            "cap, not about Germany as a whole."
        ),
    )

    headline = _headline_row(table_two, LinkageGroup.ALL, household_size=1)
    without = _headline_row(
        table_two,
        LinkageGroup.EXCLUDING_WOGG_LINKED,
        household_size=1,
    )
    register_result(
        filename=TABLE_TWO_CSV.name,
        analysis_module="P0.3",
        dataset="proxy_error_gemeinde_household.parquet",
        script=_SCRIPT,
        interpretation=(
            f"For a single-person household the local cap sits a median "
            f"{headline['median_eur']:.0f} € above the Wohngeld Höchstbetrag "
            f"across all {headline['n_gemeinden']:,.0f} comparable Gemeinden, "
            f"and {without['median_eur']:.0f} € above it once the "
            f"{without['n_gemeinden']:,.0f} Gemeinden that are not WoGG-linked "
            "are looked at alone."
        ),
        limitation=(
            f"{headline['share_at_safety_markup_pct']:.1f} % of Gemeinden sit "
            "exactly on the 10 % Sicherheitszuschlag at this household size, "
            "where the gap is a definitional identity rather than an empirical "
            "finding (D7)."
        ),
    )

    register_result(
        filename=TABLE_ONE_MARKDOWN.name,
        analysis_module="P0.3",
        dataset="analysis_sample_main.parquet",
        script=_SCRIPT,
        interpretation=(
            "The reading rendering of Table 1, carrying the coverage note that "
            "states the two denominators: every Gemeinde in Germany, and the "
            "smaller set that has a Wohngeld benchmark to be compared against."
        ),
        limitation=(
            "Rendered from the same frame as the CSV but rounded to one "
            "decimal, so it is for reading and quotation and never the source "
            "for a recomputation."
        ),
    )
    register_result(
        filename=TABLE_TWO_MARKDOWN.name,
        analysis_module="P0.3",
        dataset="proxy_error_gemeinde_household.parquet",
        script=_SCRIPT,
        interpretation=(
            "The reading rendering of Table 2: one panel of household size by "
            "linkage group, with the note that spells out why the pooled row "
            "may not be read as an empirical regularity (D7)."
        ),
        limitation=(
            "Shows only the primary D6 benchmark under Gemeinde-unweighted "
            "weighting; the Klimakomponente variant and the other three §8.2 "
            "weightings exist only in the CSV beside it."
        ),
    )


def _population_share(table_one: pd.DataFrame) -> float:
    return float(
        table_one["population_main_sample"].sum() / table_one["population_total"].sum(),
    )


def _headline_row(
    table: pd.DataFrame,
    group: LinkageGroup,
    *,
    household_size: int,
) -> pd.Series:
    return table.loc[
        (table["benchmark_variant"] == str(PRIMARY_BENCHMARK))
        & (table["weighting"] == str(WeightingScheme.GEMEINDE_UNWEIGHTED))
        & (table["group"] == str(group))
        & (table["household_size"] == household_size)
    ].iloc[0]
