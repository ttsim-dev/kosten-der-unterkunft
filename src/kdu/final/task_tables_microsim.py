"""Table 4 of §19, the §11.3 need table, and the §21 result interpretations.

Table 4 is reported three ways: on all Gemeinden, excluding the WoGG-linked
group, and on that group alone. The group is `wogg_linked_flag`, which A12 names
`linked_union`: the union of the two D7 detectors, the notes regex and the `K/W`
ratio across household sizes. It covers 1,752 of the 9,323 comparable Gemeinden,
18.8 %.

`linked_union` is not the `exact_ratio` group. `exact_ratio` is the 1,203
Gemeinden whose `K/W` is 1.100 within 5e-4 at household size 1, and it is the
group for which `Δ` is a definitional +10 % of `W`. The two overlap without
either containing the other, so a Table 4 row that excludes `linked_union`
excludes a broader and slightly different set. Every row therefore names its
group in the `linkage_group` and `note` columns, as A12 requires.

The §21 interpretation text is generated from the same frames as the tables, so
no number in it can be a placeholder or drift out of date.
"""

from pathlib import Path
from typing import Annotated, cast

import numpy as np
import pandas as pd
from pytask import Product

from kdu.config import BLD, MODEL_HOUSEHOLDS, TABLES
from kdu.final.manifest import register_result
from kdu.simulation.kdu_cap import round_currency_m, round_ratio
from kdu.simulation.microsim import MINDESTLOHN_EUR_PER_HOUR
from kdu.simulation.needs_level import NEEDS_MEASURE_LABEL

# Quantiles Table 4 reports alongside the median (§19).
TABLE_QUANTILES: tuple[float, float] = (0.10, 0.90)

_MODULE = "src/kdu/final/task_tables_microsim.py"

# The three linkage groups Table 4 is always reported under. The flagged group
# is `wogg_linked_flag`, which A12 names `linked_union`.
LINKAGE_GROUP_ALL = "all"
LINKAGE_GROUP_EXCLUDING = "excluding_linked_union"
LINKAGE_GROUP_ONLY = "linked_union_only"

# Row labels kept as prose for the §21 text, which reads them back by name.
TABLE_4_SAMPLE_LABELS: dict[str, str] = {
    LINKAGE_GROUP_ALL: "all Gemeinden",
    LINKAGE_GROUP_EXCLUDING: "excluding WoGG-linked Gemeinden",
    LINKAGE_GROUP_ONLY: "WoGG-linked Gemeinden only",
}

# The table note A12 requires: which group the row holds, spelled out in the
# table itself rather than left to the reader to infer from the label.
_LINKED_UNION_DEFINITION = (
    "linked_union (A12) is wogg_linked_flag, the union of the D7 notes-regex "
    "and K/W-ratio detectors. It is broader than and not a superset of "
    "exact_ratio, the Gemeinden whose K/W is 1.100 within 5e-4, for which the "
    "difference is a definitional +10 % of W."
)
TABLE_4_GROUP_NOTES: dict[str, str] = {
    LINKAGE_GROUP_ALL: (
        f"All comparable Gemeinden, linked and unlinked together. "
        f"{_LINKED_UNION_DEFINITION}"
    ),
    LINKAGE_GROUP_EXCLUDING: (
        f"Excludes the linked_union group, not exact_ratio. {_LINKED_UNION_DEFINITION}"
    ),
    LINKAGE_GROUP_ONLY: (
        f"The linked_union group alone, not exact_ratio. {_LINKED_UNION_DEFINITION}"
    ),
}

_TABLE_4_LIMITATION = (
    "Δ are conditional on the cap being in force: inside the § 22 Abs. 1 SGB II "
    "Karenzzeit actual Unterkunftskosten are recognised in full and the proxy "
    "error is identically zero. The Vorrangprüfung assumes WTHH = BG, which "
    "matters most for the couple household."
)


def task_tables_microsim(
    gemeinde_results: Path = BLD / "microsim_gemeinde.parquet",
    heating_sensitivity: Path = BLD / "microsim_heating_sensitivity.parquet",
    rent_grid: Path = BLD / "microsim_rent_grid.parquet",
    needs_summary: Path = BLD / "needs_level_summary.parquet",
    needs_components: Path = BLD / "needs_level_components.parquet",
    needs_gemeinde: Path = BLD / "needs_level_gemeinde.parquet",
    table_4_path: Annotated[Path, Product] = TABLES / "table4_microsim.csv",
    heating_table_path: Annotated[Path, Product] = (
        TABLES / "table4_microsim_heating_sensitivity.csv"
    ),
    rent_table_path: Annotated[Path, Product] = (
        TABLES / "table4_microsim_rent_grid.csv"
    ),
    needs_table_path: Annotated[Path, Product] = TABLES / "table_needs_level.csv",
    interpretation_path: Annotated[Path, Product] = (
        TABLES / "microsim_interpretation.md"
    ),
) -> None:
    """Write Table 4 and its robustness tables, the §11.3 table, and the §21 text."""
    results = pd.read_parquet(gemeinde_results)
    table_4 = build_table_4(results)
    _write_csv(table_4, table_4_path)
    _write_csv(
        build_heating_table(pd.read_parquet(heating_sensitivity)),
        heating_table_path,
    )
    _write_csv(build_rent_grid_table(pd.read_parquet(rent_grid)), rent_table_path)
    needs_table = build_needs_table(
        pd.read_parquet(needs_summary),
        pd.read_parquet(needs_components),
    )
    _write_csv(needs_table, needs_table_path)
    interpretation_path.parent.mkdir(parents=True, exist_ok=True)
    interpretation_path.write_text(
        build_interpretation(
            table_4=table_4,
            need=pd.read_parquet(needs_gemeinde),
            components=pd.read_parquet(needs_components),
        ),
        encoding="utf-8",
    )
    _register(table_4)


def build_table_4(results: pd.DataFrame) -> pd.DataFrame:
    """Table 4 of §19 on all Gemeinden, without the D7 group, and on it alone.

    Each block carries the `linkage_group` and `note` columns that name which
    group it holds, because A12 requires every table to state that in its own
    note rather than leave it to be inferred from a label.
    """
    flagged = results["wogg_linked_flag"].fillna(value=False)
    blocks = (
        (LINKAGE_GROUP_ALL, results),
        (LINKAGE_GROUP_EXCLUDING, results.loc[~flagged]),
        (LINKAGE_GROUP_ONLY, results.loc[flagged]),
    )
    frames = [
        _summarise(rows, sample_label=TABLE_4_SAMPLE_LABELS[group]).assign(
            linkage_group=group,
            note=TABLE_4_GROUP_NOTES[group],
        )
        for group, rows in blocks
    ]
    return pd.concat(frames, ignore_index=True)


def build_heating_table(sensitivity: pd.DataFrame) -> pd.DataFrame:
    """§12.3: how the 75 % and 125 % heating variants move `ΔT(0)` and `Δy*`.

    Every statistic is weighted by the number of Gemeinden a cell stands for, so
    it is directly comparable with Table 4 rather than being a distribution over
    the simulation grid.
    """
    rows = []
    grouped = sensitivity.groupby(["household_key", "heating_factor"])
    for keys, group in grouped:
        key, factor = cast("tuple[str, float]", keys)
        weights = group["n_gemeinden"].to_numpy(dtype=float)
        rows.append(
            {
                "household_key": key,
                "heating_factor": factor,
                "n_cells": len(group),
                "n_gemeinden": int(weights.sum()),
                "heizkosten_m": float(group["heizkosten_m"].iloc[0]),
                "delta_transfer_zero_median_m": _weighted_quantile(
                    group["delta_transfer_zero_m"],
                    weights,
                    0.50,
                ),
                "delta_exit_threshold_median_m": _weighted_quantile(
                    group["delta_exit_threshold_m"],
                    weights,
                    0.50,
                ),
                "delta_hours_median": _weighted_quantile(
                    group["delta_hours_per_week"],
                    weights,
                    0.50,
                ),
            },
        )
    return _label_households(pd.DataFrame(rows))


def build_rent_grid_table(rent_grid: pd.DataFrame) -> pd.DataFrame:
    """§12.2 Variante 2: `ΔT(0)` as the assumed rent moves from 50 % to 130 %."""
    rows = []
    for keys, group in rent_grid.groupby(["household_key", "rent_factor"]):
        key, factor = cast("tuple[str, float]", keys)
        weights = group["n_gemeinden"].to_numpy(dtype=float)
        values = group["delta_transfer_zero_m"]
        rows.append(
            {
                "household_key": key,
                "rent_factor": factor,
                "n_cells": len(group),
                "n_gemeinden": int(weights.sum()),
                "delta_transfer_zero_median_m": _weighted_quantile(
                    values, weights, 0.5
                ),
                "delta_transfer_zero_p10_m": _weighted_quantile(values, weights, 0.10),
                "delta_transfer_zero_p90_m": _weighted_quantile(values, weights, 0.90),
                "share_with_no_difference": float(
                    weights[np.isclose(values.to_numpy(dtype=float), 0.0)].sum()
                    / weights.sum(),
                ),
            },
        )
    return _label_households(pd.DataFrame(rows))


def _weighted_quantile(
    values: pd.Series,
    weights: np.ndarray,
    quantile: float,
) -> float:
    """Quantile of `values` weighted by `weights`, both aligned and non-empty."""
    order = np.argsort(values.to_numpy(dtype=float))
    sorted_values = values.to_numpy(dtype=float)[order]
    sorted_weights = weights[order]
    cumulative = np.cumsum(sorted_weights) / sorted_weights.sum()
    position = int(np.searchsorted(cumulative, quantile))
    return float(sorted_values[min(position, len(sorted_values) - 1)])


def build_needs_table(
    summary: pd.DataFrame,
    components: pd.DataFrame,
) -> pd.DataFrame:
    """§11.3: the administrative Bruttokaltbedarf table, with `R + M` alongside."""
    merged = summary.merge(
        components.loc[
            :,
            ["household_key", "household_label", "regelbedarf_m", "mehrbedarf_m"],
        ],
        on="household_key",
        how="left",
        validate="many_to_one",
    )
    return merged.assign(measure=NEEDS_MEASURE_LABEL)


def build_interpretation(
    table_4: pd.DataFrame,
    need: pd.DataFrame,
    components: pd.DataFrame,
) -> str:
    """Write the §21 interpretation of the P0.6 and P0.7 results, in real numbers."""
    lines = [
        "# Result interpretation — P0.6 and P0.7",
        "",
        "Written to the four-question pattern of §21. Every figure is computed from",
        "`bld/microsim_gemeinde.parquet` and `bld/needs_level_gemeinde.parquet`; none",
        "is a placeholder.",
        "",
        f"## The {NEEDS_MEASURE_LABEL}",
        "",
    ]
    lines.extend(_needs_paragraph(need, components))
    lines.extend(
        [
            "",
            "## The Standardfall microsimulation",
            "",
            f"The with/without pair below excludes the `linked_union` group of "
            f"A12 — `wogg_linked_flag`, the union of the two D7 detectors, "
            f"{_group_size(table_4, LINKAGE_GROUP_ONLY):,} of the "
            f"{_group_size(table_4, LINKAGE_GROUP_ALL):,} comparable Gemeinden. "
            f"That is not the narrower `exact_ratio` group whose `K/W` is 1.100 "
            f"within 5e-4, which is the group for which the difference is a "
            f"definitional +10 % of `W`.",
            "",
        ],
    )
    lines.extend(_simulation_paragraphs(table_4))
    lines.extend(
        [
            "",
            "## What these numbers do not say",
            "",
            "- They are not a causal effect. A Kreis with a high Obergrenze may",
            "  face an expensive housing market; the Obergrenze is endogenous to that",
            "  market, to administrative practice and to how Vergleichsräume are cut.",
            "- They are not an actual KdU payment. `K` is the maximum recognisable",
            "  Bruttokaltmiete, not what any Bedarfsgemeinschaft receives.",
            "- The need measure excludes heating, so it is not a full Existenzminimum.",
            "- Every Δ is conditional on the cap being in force. Inside the § 22 Abs. 1",
            "  SGB II Karenzzeit the actual Unterkunftskosten are recognised in full,",
            "  so the proxy error is identically zero there.",
            "- The Vorrangprüfung that decides between SGB II, Wohngeld and",
            "  Kinderzuschlag assumes the wohngeldrechtlicher Teilhaushalt coincides",
            "  with the Bedarfsgemeinschaft. That assumption bites hardest for the",
            "  couple household with two children.",
            "",
        ],
    )
    return "\n".join(lines)


def _linkage_block(table_4: pd.DataFrame, linkage_group: str) -> pd.DataFrame:
    """The Table 4 rows of one linkage group, indexed by household."""
    rows = table_4.loc[table_4["linkage_group"] == linkage_group]
    return rows.set_index("household_key")


def _group_size(table_4: pd.DataFrame, linkage_group: str) -> int:
    """How many Gemeinden one Table 4 linkage group holds."""
    rows = table_4.loc[table_4["linkage_group"] == linkage_group, "n_gemeinden"]
    return int(rows.max())


def _needs_paragraph(need: pd.DataFrame, components: pd.DataFrame) -> list[str]:
    lines = []
    for key, household in MODEL_HOUSEHOLDS.items():
        rows = need.query("household_key == @key")
        component = components.query("household_key == @key").iloc[0]
        kdu_need = rows["need_kdu_m"].dropna()
        share = rows["kdu_share_of_need"].dropna()
        difference = rows["need_difference_m"].dropna()
        lines.extend(
            [
                f"**{household.label}.** Regelbedarfe and Mehrbedarfe come to "
                f"{component['regelbedarf_m']:,.2f} € plus "
                f"{component['mehrbedarf_m']:,.2f} € per month, the same figure "
                f"everywhere in Germany. Adding the local KdU-Obergrenze gives an "
                f"{NEEDS_MEASURE_LABEL} with a median of "
                f"{kdu_need.median():,.0f} €, a P10–P90 span of "
                f"{kdu_need.quantile(0.10):,.0f} € to "
                f"{kdu_need.quantile(0.90):,.0f} €, and a full regional range of "
                f"{kdu_need.max() - kdu_need.min():,.0f} €. The housing component "
                f"accounts for a median {100 * share.median():.1f} % of it. "
                f"Substituting the Wohngeld-Höchstbetrag moves the measure by a "
                f"median of {difference.median():,.0f} € "
                f"(P10 {difference.quantile(0.10):,.0f} €, "
                f"P90 {difference.quantile(0.90):,.0f} €).",
                "",
            ],
        )
    return lines


def _simulation_paragraphs(table_4: pd.DataFrame) -> list[str]:
    lines = []
    for key, household in MODEL_HOUSEHOLDS.items():
        rows = table_4.query("household_key == @key").set_index("sample")
        pooled = rows.loc[TABLE_4_SAMPLE_LABELS[LINKAGE_GROUP_ALL]]
        clean = rows.loc[TABLE_4_SAMPLE_LABELS[LINKAGE_GROUP_EXCLUDING]]
        lines.extend(
            [
                f"**{household.label}.** Measured across "
                f"{int(pooled['n_gemeinden']):,} Gemeinden, replacing the local "
                f"KdU-Obergrenze by the Wohngeld-Höchstbetrag changes the simulated "
                f"claim at zero earnings by a median of "
                f"{pooled['delta_transfer_zero_median_m']:,.0f} € per month "
                f"(P10 {pooled['delta_transfer_zero_p10_m']:,.0f} €, "
                f"P90 {pooled['delta_transfer_zero_p90_m']:,.0f} €) and moves the "
                f"Transfer-Ausstiegsschwelle by a median of "
                f"{pooled['delta_exit_threshold_median_m']:,.0f} € "
                f"(P10 {pooled['delta_exit_threshold_p10_m']:,.0f} €, "
                f"P90 {pooled['delta_exit_threshold_p90_m']:,.0f} €), which is "
                f"{pooled['delta_hours_median']:,.1f} weekly working hours at the "
                f"2026 Mindestlohn of {MINDESTLOHN_EUR_PER_HOUR:.2f} €/h. In "
                f"{pooled['share_abs_delta_exit_over_100_eur'] * 100:.1f} % of "
                f"Gemeinden the exit threshold moves by more than 100 € per month. "
                f"Excluding the `linked_union` group of A12 — the union of the "
                f"two D7 detectors, and broader than the 1,203 Gemeinden whose "
                f"`K/W` is exactly 1.100 — the median shift is "
                f"{clean['delta_exit_threshold_median_m']:,.0f} € across "
                f"{int(clean['n_gemeinden']):,} Gemeinden. A tax-transfer model that "
                f"substitutes the Wohngeld value therefore mismeasures not only the "
                f"level of the simulated claim but the income range over which it is "
                f"paid at all.",
                "",
            ],
        )
    return lines


def _summarise(results: pd.DataFrame, sample_label: str) -> pd.DataFrame:
    rows = results.dropna(subset=["delta_exit_threshold_m"])
    grouped = rows.groupby("household_key", as_index=False)
    summary = grouped.agg(
        n_gemeinden=("ags", "nunique"),
        n_cells=("cell_id", "nunique"),
        delta_transfer_zero_median_m=("delta_transfer_zero_m", "median"),
        delta_transfer_zero_p10_m=(
            "delta_transfer_zero_m",
            lambda values: values.quantile(TABLE_QUANTILES[0]),
        ),
        delta_transfer_zero_p90_m=(
            "delta_transfer_zero_m",
            lambda values: values.quantile(TABLE_QUANTILES[1]),
        ),
        delta_transfer_max_median_m=("delta_transfer_max_m", "median"),
        delta_transfer_max_p90_m=(
            "delta_transfer_max_m",
            lambda values: values.quantile(TABLE_QUANTILES[1]),
        ),
        delta_exit_threshold_median_m=("delta_exit_threshold_m", "median"),
        delta_exit_threshold_p10_m=(
            "delta_exit_threshold_m",
            lambda values: values.quantile(TABLE_QUANTILES[0]),
        ),
        delta_exit_threshold_p90_m=(
            "delta_exit_threshold_m",
            lambda values: values.quantile(TABLE_QUANTILES[1]),
        ),
        delta_hours_median=("delta_hours_per_week", "median"),
        delta_hours_p10=(
            "delta_hours_per_week",
            lambda values: values.quantile(TABLE_QUANTILES[0]),
        ),
        delta_hours_p90=(
            "delta_hours_per_week",
            lambda values: values.quantile(TABLE_QUANTILES[1]),
        ),
        share_abs_delta_exit_over_100_eur=(
            "delta_exit_threshold_m",
            lambda values: float((values.abs() > 100.0).mean()),
        ),
        delta_sgb_regime_end_median_m=("delta_sgb_regime_end_m", "median"),
    )
    summary["delta_exit_threshold_population_weighted_median_m"] = (
        _population_weighted_medians(rows)
    )
    amounts = [column for column in summary.columns if column.endswith("_m")]
    for column in amounts:
        summary[column] = round_currency_m(summary[column].astype(float))
    for column in ("delta_hours_median", "delta_hours_p10", "delta_hours_p90"):
        summary[column] = round_ratio(summary[column].astype(float))
    summary["share_abs_delta_exit_over_100_eur"] = round_ratio(
        summary["share_abs_delta_exit_over_100_eur"].astype(float),
    )
    return _label_households(summary).assign(sample=sample_label)


def _population_weighted_medians(rows: pd.DataFrame) -> pd.Series:
    """§8.2 weighting scheme 2: what the population, not the map, is exposed to."""
    medians = {}
    for key, group in rows.groupby("household_key"):
        ordered = group.sort_values("delta_exit_threshold_m")
        weights = ordered["population"].fillna(value=0.0).to_numpy(dtype=float)
        if weights.sum() <= 0.0:
            medians[key] = float("nan")
            continue
        cumulative = np.cumsum(weights) / weights.sum()
        position = int(np.searchsorted(cumulative, 0.5))
        medians[key] = float(
            ordered["delta_exit_threshold_m"].to_numpy()[
                min(position, len(ordered) - 1)
            ],
        )
    return pd.Series(medians).reindex(sorted(medians)).reset_index(drop=True)


def _label_households(summary: pd.DataFrame) -> pd.DataFrame:
    labels = {key: household.label for key, household in MODEL_HOUSEHOLDS.items()}
    sizes = {
        key: household.household_size for key, household in MODEL_HOUSEHOLDS.items()
    }
    return summary.assign(
        household_label=summary["household_key"].map(labels),
        household_size=summary["household_key"].map(sizes),
    )


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _register(table_4: pd.DataFrame) -> None:
    pooled = _linkage_block(table_4, LINKAGE_GROUP_ALL)
    clean = _linkage_block(table_4, LINKAGE_GROUP_EXCLUDING)
    single_pooled = pooled.loc["single_35"]
    single_clean = clean.loc["single_35"]
    register_result(
        filename="table4_microsim.csv",
        analysis_module="P0.7",
        dataset="microsim_gemeinde.parquet",
        script=_MODULE,
        interpretation=(
            f"For a single adult the Wohngeld proxy moves the simulated exit "
            f"threshold by a median of "
            f"{single_pooled['delta_exit_threshold_median_m']:,.0f} € per month "
            f"across all {_group_size(table_4, LINKAGE_GROUP_ALL):,} Gemeinden "
            f"and {single_clean['delta_exit_threshold_median_m']:,.0f} € once "
            f"the {_group_size(table_4, LINKAGE_GROUP_ONLY):,} Gemeinden of the "
            f"`linked_union` group are excluded."
        ),
        limitation=_TABLE_4_LIMITATION,
    )
    register_result(
        filename="microsim_interpretation.md",
        analysis_module="P0.6 and P0.7",
        dataset="microsim_gemeinde.parquet",
        script=_MODULE,
        interpretation=(
            f"The §21 four-part reading of the need level and the "
            f"microsimulation: for the single adult the Wohngeld proxy moves "
            f"the Transfer-Ausstiegsschwelle by a median of "
            f"{single_pooled['delta_exit_threshold_median_m']:,.0f} € per "
            f"month, {single_pooled['delta_hours_median']:,.1f} weekly working "
            f"hours at the 2026 Mindestlohn."
        ),
        limitation=(
            "Its with/without pair excludes the `linked_union` group of A12, "
            "not the narrower `exact_ratio` group for which the difference is a "
            f"definitional +10 % of W. {_TABLE_4_LIMITATION}"
        ),
    )
    register_result(
        filename="table4_microsim_heating_sensitivity.csv",
        analysis_module="P0.7",
        dataset="microsim_heating_sensitivity.parquet",
        script=_MODULE,
        interpretation=(
            "Heating is held constant across the two scenarios, so the 75 % and "
            "125 % variants leave ΔT(0) untouched and move Δy* only through the "
            "income-offsetting schedule."
        ),
        limitation=(
            "The BA heating figure is a stock-weighted mean over Kreise for "
            "Bedarfsgemeinschaften under SGB II; applying it to the SGB XII "
            "pensioner household is an approximation."
        ),
    )
    register_result(
        filename="table4_microsim_rent_grid.csv",
        analysis_module="P0.7",
        dataset="microsim_rent_grid.parquet",
        script=_MODULE,
        interpretation=(
            "Below roughly 80 % of max(K, W) neither cap binds and the two "
            "parameters give identical results; the difference emerges only once "
            "the rent reaches the lower of the two caps."
        ),
        limitation=(
            "The rent grid is anchored on max(K, W), an administrative quantity. "
            "It is not a distribution of observed market rents; §12.2 Variante 3 "
            "supplies that once the Zensus module lands."
        ),
    )
    register_result(
        filename="table_needs_level.csv",
        analysis_module="P0.6",
        dataset="needs_level_gemeinde.parquet",
        script=_MODULE,
        interpretation=(
            f"The {NEEDS_MEASURE_LABEL} varies across Gemeinden entirely through "
            f"its housing component, since Regelbedarfe and Mehrbedarfe are "
            f"national."
        ),
        limitation=(
            "Heating is excluded from the measure, so it must never be called a "
            "full Existenzminimum."
        ),
    )
