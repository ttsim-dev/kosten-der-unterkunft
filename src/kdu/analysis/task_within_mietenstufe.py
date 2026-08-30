"""Compute the P0.4 within-Mietenstufe descriptives, decomposition and tables.

Reads the main sample and the crosswalk, writes the prepared analysis frame the
figure task reads, and the four §9 / §18 / §19 tables. Every table carries the
`sample` column D7 requires, so no number in this module is ever shown only
with the WoGG-linked Gemeinden folded in.
"""

from pathlib import Path
from typing import Annotated, cast

import pandas as pd
from pytask import Product

from kdu.analysis.within_mietenstufe import (
    CAP_COLUMN,
    RATIO_COLUMN,
    Sample,
    Specification,
    fit_variance_decomposition,
    prepare_analysis_frame,
    robustness_table,
    stratified_dispersion,
    table_3,
    variance_decomposition_table,
)
from kdu.config import BLD, DATA_CATALOG, TABLES
from kdu.final.manifest import register_result

_ANALYSIS_SAMPLE_MAIN = cast("Path", DATA_CATALOG["analysis_sample_main"])
_MUNICIPALITY_CROSSWALK = cast("Path", DATA_CATALOG["municipality_crosswalk"])

WITHIN_MIETENSTUFE_FRAME = BLD / "within_mietenstufe_frame.parquet"
DISPERSION_TABLE = TABLES / "within_mietenstufe_dispersion.csv"
DECOMPOSITION_TABLE = TABLES / "within_mietenstufe_variance_decomposition.csv"
COEFFICIENT_TABLE = TABLES / "within_mietenstufe_coefficients.csv"
TABLE_3 = TABLES / "table3_within_mietenstufe.csv"
ROBUSTNESS_TABLE = TABLES / "within_mietenstufe_robustness.csv"

_SCRIPT = "src/kdu/analysis/task_within_mietenstufe.py"
_DATASET = "within_mietenstufe_frame.parquet"


def task_within_mietenstufe(
    analysis_sample_main_file: Path = _ANALYSIS_SAMPLE_MAIN,
    municipality_crosswalk_file: Path = _MUNICIPALITY_CROSSWALK,
    frame_file: Annotated[Path, Product] = WITHIN_MIETENSTUFE_FRAME,
    dispersion_file: Annotated[Path, Product] = DISPERSION_TABLE,
    decomposition_file: Annotated[Path, Product] = DECOMPOSITION_TABLE,
    coefficient_file: Annotated[Path, Product] = COEFFICIENT_TABLE,
    table_3_file: Annotated[Path, Product] = TABLE_3,
    robustness_file: Annotated[Path, Product] = ROBUSTNESS_TABLE,
) -> None:
    """Read the P0.4 inputs, compute every §9 output, and write them."""
    frame = prepare_analysis_frame(
        pd.read_parquet(analysis_sample_main_file),
        pd.read_parquet(municipality_crosswalk_file),
    )
    for path in (frame_file, dispersion_file):
        path.parent.mkdir(parents=True, exist_ok=True)

    frame.to_parquet(frame_file, index=False)
    dispersion = build_dispersion(frame)
    decomposition = variance_decomposition_table(frame)
    coefficients = build_coefficients(frame)
    robustness = robustness_table(frame)

    dispersion.to_csv(dispersion_file, index=False)
    decomposition.to_csv(decomposition_file, index=False)
    coefficients.to_csv(coefficient_file, index=False)
    table_3(frame).to_csv(table_3_file, index=False)
    robustness.to_csv(robustness_file, index=False)

    _register(dispersion, decomposition, coefficients, robustness)


def _register(
    dispersion: pd.DataFrame,
    decomposition: pd.DataFrame,
    coefficients: pd.DataFrame,
    robustness: pd.DataFrame,
) -> None:
    """Record the four §5.2 tables this module writes beside Table 3."""
    cap_column = CAP_COLUMN
    caps = dispersion.query(
        "measure == @cap_column and stratum == 'all' and household_size == 1",
    )
    register_result(
        filename=DISPERSION_TABLE.name,
        analysis_module="P0.4",
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"Inside a single Mietenstufe the single-person cap still spans a "
            f"median P90−P10 of {caps['p90_minus_p10'].median():,.0f} €, and "
            f"{caps['share_abs_dev_above_50_eur'].median():.0%} of Gemeinden "
            f"sit more than 50 € from their own Mietenstufe's median, in every "
            f"stratum the plan asks for."
        ),
        limitation=(
            "210 of 400 Kreise cut Vergleichsräume inside their own territory "
            "(D1), so part of this spread is within-Kreis by design and is not "
            "disagreement between Träger."
        ),
    )

    pooled = decomposition.query("specification == 'pooled' and sample == 'all'").iloc[
        0
    ]
    by_size = decomposition.query(
        "specification == 'mietenstufe' and sample == 'all'",
    )
    register_result(
        filename=DECOMPOSITION_TABLE.name,
        analysis_module="P0.4",
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"The statutory Mietenstufe accounts for "
            f"{by_size['r_squared'].min():.0%} to "
            f"{by_size['r_squared'].max():.0%} of the variation in log K by "
            f"household size and {pooled['r_squared']:.0%} pooled, so most of "
            f"the dispersion in local caps lies within Mietenstufen."
        ),
        limitation=(
            "A descriptive variance decomposition, not a model of how caps are "
            "set: the Mietenstufe is a statutory classification correlated with "
            "the housing market, and no R² here identifies an effect."
        ),
    )

    se_ratio = (coefficients["cluster_se"] / coefficients["classical_se"]).median()
    steps = coefficients.query(
        "specification == 'mietenstufe' and sample == 'all' "
        "and household_size == 1 and name != 'intercept'",
    )
    register_result(
        filename=COEFFICIENT_TABLE.name,
        analysis_module="P0.4",
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"The fitted Mietenstufe steps in log K run from "
            f"{steps['estimate'].min():.2f} to {steps['estimate'].max():.2f} at "
            f"household size 1, and the Kreis-clustered standard errors are a "
            f"median {se_ratio:.1f} times the classical ones."
        ),
        limitation=(
            "Descriptive by construction: §9.2 asks for the size of the steps "
            "and how imprecisely the Kreis clustering of D1 pins them down, so "
            "no p-value or significance marker is computed anywhere."
        ),
    )

    fits = robustness["r_squared"].dropna()
    register_result(
        filename=ROBUSTNESS_TABLE.name,
        analysis_module="P0.4",
        dataset=_DATASET,
        script=_SCRIPT,
        interpretation=(
            f"Across every §18 variation — benchmark, weighting, spatial unit, "
            f"quality tier and Regionstyp — the pooled R² stays between "
            f"{fits.min():.2f} and {fits.max():.2f}, so the within-Mietenstufe "
            f"residual spread is not an artefact of any one choice."
        ),
        limitation=(
            "A robustness grid: each row is a separate fit on a different "
            "subset, the Bedarfsgemeinschaft rows are empty until the P1.2 BA "
            "extract exists, and none of these rows replaces Table 3."
        ),
    )


def build_dispersion(frame: pd.DataFrame) -> pd.DataFrame:
    """Stack the §9.1 descriptives for the euro cap and for the `K/W` ratio.

    The euro distances from the own-Mietenstufe median are meaningful only for
    the cap, so the ratio block carries the spread and the log standard
    deviation and leaves those two shares empty.

    Args:
        frame: Prepared analysis frame.

    Returns:
        One row per measure, stratum, household size and Mietenstufe.

    """
    cap = stratified_dispersion(frame, value_column=CAP_COLUMN)
    ratio = stratified_dispersion(
        frame,
        value_column=RATIO_COLUMN,
        deviation_thresholds=(),
    )
    cap.insert(0, "measure", CAP_COLUMN)
    ratio.insert(0, "measure", RATIO_COLUMN)
    return pd.concat([cap, ratio], ignore_index=True)


def build_coefficients(frame: pd.DataFrame) -> pd.DataFrame:
    """Collect the fitted Mietenstufe effects with their Kreis-clustered errors.

    §9.2 is a descriptive variance decomposition, so the point of this table is
    the size of the Mietenstufe steps and how imprecisely they are pinned down
    once the Kreis clustering D1 implies is respected — not a hypothesis test.
    No p-value or significance marker is computed anywhere.

    Args:
        frame: Prepared analysis frame.

    Returns:
        One row per specification, sample, household size and coefficient.

    """
    rows = []
    for sample in Sample:
        subset = (
            frame
            if sample is Sample.ALL
            else frame.loc[~frame["wogg_linked_flag"].astype(bool)]
        )
        fits = [
            fit_variance_decomposition(
                subset.loc[subset["household_size"] == household_size],
                specification=Specification.MIETENSTUFE,
                sample=sample,
            )
            for household_size in sorted(subset["household_size"].unique())
        ]
        fits.extend(
            fit_variance_decomposition(
                subset,
                specification=specification,
                sample=sample,
            )
            for specification in (
                Specification.POOLED,
                Specification.POOLED_WITH_STATE,
            )
        )
        rows.extend(
            fit.coefficients.assign(
                specification=fit.specification.value,
                sample=fit.sample.value,
                household_size=fit.household_size,
            )
            for fit in fits
        )
    combined = pd.concat(rows, ignore_index=True)
    ordered = ["specification", "sample", "household_size", "name"]
    return combined.loc[
        :,
        [*ordered, "estimate", "classical_se", "cluster_se"],
    ]
