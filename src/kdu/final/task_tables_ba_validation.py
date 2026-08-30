"""Write §19 Table 5, the external-validation summary, as CSV and Markdown.

§19 asks Table 5 for the BA recognition rate, the market-stress indicator, the
descriptive regression coefficients, the sample size and the spatial unit used.
Each row is one linkage group under A12, so a reader never has to work out which
of the two WoGG-linked definitions a number belongs to; the note under the table
says which one the headline row rests on.
"""

from pathlib import Path
from typing import Annotated

import pandas as pd
from pytask import Product

from kdu.analysis.ba_validation import (
    LinkageGroup,
    table_5,
)
from kdu.analysis.task_ba_validation import (
    BA_VALIDATION_FRAME,
    RELEVANCE_TABLE,
    SPECIFICATIONS_TABLE,
)
from kdu.config import LEGAL_VINTAGE, TABLES
from kdu.final.manifest import register_result
from kdu.final.task_tables_coverage import to_markdown

TABLE_5 = TABLES / "table5_external_validation.csv"
TABLE_5_MARKDOWN = TABLES / "table5_external_validation.md"

_MODULE = "P1.2"
_DATASET = "ba_validation_jobcenter_household.parquet"
_SCRIPT = "src/kdu/final/task_tables_ba_validation.py"

# Column order and header of Table 5, in the order §19 lists the contents.
_COLUMNS: tuple[tuple[str, str], ...] = (
    ("linkage_group", "Linkage group"),
    ("spatial_unit", "Spatial unit"),
    ("n_obs", "N (Jobcenter × h)"),
    ("n_jobcenter", "Jobcenter"),
    ("median_recognition_rate", "Median R^BA"),
    ("median_non_recognised_share", "Median N^BA"),
    ("median_gap_eur", "Median G^BA (€)"),
    ("median_market_stress", "Median M^market / K"),
    ("median_cap_over_benchmark", "Median K / W"),
    ("beta_log_cap_ratio", "β on log(K/W)"),
    ("beta_log_cap_ratio_cluster_se", "SE (Jobcenter-clustered)"),
    ("beta_log_market", "β on log(M/K)"),
    ("beta_log_market_cluster_se", "SE (Jobcenter-clustered)"),
    ("beta_gap_on_cap", "β₁ on K (G^BA, €/€)"),
    ("beta_gap_on_cap_cluster_se", "SE (Jobcenter-clustered)"),
    ("beta_gap_on_market", "β₂ on M^market (G^BA, €/€)"),
    ("beta_gap_on_market_cluster_se", "SE (Jobcenter-clustered)"),
    ("bg_weighted_proxy_error_eur_h1", "D̄^BG, h=1 (€)"),
    ("bg_weighted_proxy_error_eur_h4", "D̄^BG, h=4 (€)"),
)

# Readable labels for the five A12 linkage groups.
_GROUP_LABELS: dict[str, str] = {
    LinkageGroup.ALL.value: "All Jobcenter",
    LinkageGroup.EXCLUDING_EXACT_RATIO.value: "Excluding exact_ratio",
    LinkageGroup.EXACT_RATIO_ONLY.value: "exact_ratio only",
    LinkageGroup.EXCLUDING_LINKED_UNION.value: "Excluding linked_union",
    LinkageGroup.LINKED_UNION_ONLY.value: "linked_union only",
}


def task_tables_ba_validation(
    frame_file: Path = BA_VALIDATION_FRAME,
    specifications_file: Path = SPECIFICATIONS_TABLE,
    relevance_file: Path = RELEVANCE_TABLE,
    table_file: Annotated[Path, Product] = TABLE_5,
    markdown_file: Annotated[Path, Product] = TABLE_5_MARKDOWN,
) -> None:
    """Build Table 5 from the P1.2 outputs and register it."""
    frame = pd.read_parquet(frame_file)
    specifications = pd.read_csv(specifications_file)
    relevance = pd.read_csv(relevance_file)

    table = table_5(frame, specifications, relevance)
    table_file.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(table_file, index=False)
    markdown_file.write_text(render_markdown(table), encoding="utf-8")

    _register_output(table)


def render_markdown(table: pd.DataFrame) -> str:
    """Render Table 5 as Markdown with the note §19 and A12 require.

    Args:
        table: Output of `table_5`.

    Returns:
        The rendered table and its note.

    """
    rendered = table.copy()
    rendered["linkage_group"] = rendered["linkage_group"].map(_GROUP_LABELS)
    rendered = rendered.loc[:, [name for name, _ in _COLUMNS]].rename(
        columns=dict(_COLUMNS),
    )
    body = to_markdown(rendered, decimals=4)
    return f"{_TITLE}\n\n{body}\n\n{_NOTE}\n"


_TITLE = "# Table 5 — external validation against the BA Wohnkostendaten (§14)"

_NOTE = f"""**Note.** Outcomes are the §14.2 quantities on the Bruttokaltmiete per
Bedarfsgemeinschaft, Mietunterkünfte only, BA reference month
{LEGAL_VINTAGE.ba_reference_month}. The spatial unit is the Jobcenter, §14.3
main sample: 398 Jobcenter serving exactly one Kreis, of which those with a
Bruttokaltmiete cap balanced over h = 1…4 enter here. The 6 Jobcenter spanning
several Kreise are robustness only and are reported in
`ba_validation_extended_dispersion.csv`. `06415` Hanau, a 401st Kreis the BA
reports and `data/kdu_gemeinden.csv` does not contain, is listed in
`ba_validation_coverage.csv` rather than dropped.

`K` is the local maximal recognised Bruttokaltmiete, aggregated Gemeinde → Kreis
→ Jobcenter with population weights. `W` is the Wohngeld base Höchstbetrag alone
(D6), Anlage 1 in force 2025-01-01. `M^market` is the Zensus 2022 mean
Nettokaltmiete per square metre — a **Bestandsmiete** — times the locally
admissible Wohnfläche; `M^market / K` is a market-stress indicator, not a
statement about housing availability, and it sets a Nettokaltmiete against a
Bruttokaltmiete cap.

All regressions carry household-size and Bundesland fixed effects over
h = 1…4 and cluster their standard errors on the Jobcenter (§14.4). They are
**descriptive**: the local cap is endogenous to the local housing market and to
administrative practice, so no coefficient identifies a causal relationship.

Two linkage definitions are reported, and they are different groups (A12).
`exact_ratio` is `K/W = 1.100` within 5e-4 — 12.9 % of Gemeinden at h = 1 — and
is the group D7's quoted table describes. `linked_union` is the union of D7's
two detectors, 18.8 %. In both, `K/W` is fixed by construction, so the β on
log(K/W) in the two "only" rows rests on almost no variation and is not
evidence either way. The headline row is **Excluding linked_union**.

`D̄^BG_h` is a national figure and is therefore identical in every row of the
table; it is the §14.5 nationally weighted mechanical proxy error `K − W`,
weighted by the BA Kreis stock of Bedarfsgemeinschaften. It reproduces P0.3's
Bedarfsgemeinschaft-weighted proxy error exactly, because the two are the same
weighted average written two ways.
"""


def _register_output(table: pd.DataFrame) -> None:
    headline = table.loc[
        table["linkage_group"] == LinkageGroup.EXCLUDING_LINKED_UNION.value
    ]
    beta = float(headline["beta_log_cap_ratio"].iloc[0])
    standard_error = float(headline["beta_log_cap_ratio_cluster_se"].iloc[0])
    n_jobcenter = int(headline["n_jobcenter"].iloc[0])
    register_result(
        filename=TABLE_5_MARKDOWN.name,
        analysis_module=_MODULE,
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            "The reading rendering of Table 5, carrying the note that names "
            "which WoGG-linkage group each row uses and states that the "
            "association is conditional on the Bundesland fixed effects."
        ),
        limitation=(
            "Prose around the same numbers as the CSV; it adds no result and "
            "must not be cited as a second source for one."
        ),
    )
    register_result(
        filename=TABLE_5.name,
        analysis_module=_MODULE,
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"Across {n_jobcenter} Jobcenter outside the WoGG-linked group, a "
            f"cap standing higher relative to the Wohngeld benchmark is "
            f"associated with less of the actual Bruttokaltmiete going "
            f"unrecognised: β = {beta:+.4f} on log(K/W), Jobcenter-clustered "
            f"SE {standard_error:.4f}."
        ),
        limitation=(
            "Descriptive only: the local cap is endogenous to the local housing "
            "market and to how a Kreis draws its Vergleichsräume, so no "
            "coefficient here identifies a causal relationship."
        ),
    )
