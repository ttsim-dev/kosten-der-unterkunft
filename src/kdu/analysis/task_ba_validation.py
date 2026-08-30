"""Build the P1.2 external-validation frame and its §14 tables.

The task reads the BA outcomes, the KdU main sample, the two crosswalks and the
Zensus rents, assembles the one Jobcenter-by-household-size frame §14 works on,
and writes the §14.3 coverage report, the §14.4 specification grid, the
regressor-variation check the D7 obligation rests on, the §14.3 within-Jobcenter
dispersion of the extended sample, and the §14.5 nationally weighted relevance.

§18's household-size robustness stops at h = 4 here: D3 balances
`analysis_sample_main` over h = 1…4, so it carries no h = 5 cap and no h = 5
specification can be fitted from it. The frame is keyed on the KdU side, so it
holds h = 1…4 only; the BA's own h = 5 outcomes remain available in
`ba_validation_outcomes.parquet` for whoever brings an h = 5 cap.

Gate 4 requires the spatial crosswalk, the cost concepts, the sample definition
and the main-versus-extended comparison to be documented before any BA result is
used. `ba_validation_coverage.csv` and `ba_validation_extended_dispersion.csv`
are those documents, and `fail_if_unexpected_kreis_absent` makes the coverage
check a hard stop rather than a note.
"""

from pathlib import Path
from typing import Annotated, cast

import pandas as pd
from pytask import Product

from kdu.analysis.ba_validation import (
    CAP_COLUMN,
    CLUSTER_COLUMN,
    ValidationSample,
    build_validation_frame,
    fail_if_unexpected_kreis_absent,
    kreis_coverage,
    nationally_weighted_relevance,
    non_recognised_identity_deviation,
    read_bedarfsgemeinschaft_stocks,
    regressor_variation,
    specification_table,
    weighted_error_distributions,
)
from kdu.analysis.proxy_error import PRIMARY_BENCHMARK
from kdu.config import BLD, DATA_CATALOG, TABLES
from kdu.final.manifest import register_result

_ANALYSIS_SAMPLE_MAIN = cast("Path", DATA_CATALOG["analysis_sample_main"])
_MUNICIPALITY_CROSSWALK = cast("Path", DATA_CATALOG["municipality_crosswalk"])

# Written by the P1.2 acquisition layer in `data_management/task_ba.py`.
BA_OUTCOMES = BLD / "ba_validation_outcomes.parquet"
BA_WOHNKOSTEN = BLD / "ba_wohnkosten_long.parquet"
JOBCENTER_CROSSWALK = BLD / "jobcenter_kreis_crosswalk.parquet"
ZENSUS_RENTS = BLD / "zensus_rents_gemeinden.parquet"
PROXY_ERROR_FRAME = BLD / "proxy_error_gemeinde_household.parquet"

BA_VALIDATION_FRAME = BLD / "ba_validation_jobcenter_household.parquet"
COVERAGE_TABLE = TABLES / "ba_validation_coverage.csv"
SPECIFICATIONS_TABLE = TABLES / "ba_validation_specifications.csv"
VARIATION_TABLE = TABLES / "ba_validation_regressor_variation.csv"
EXTENDED_DISPERSION_TABLE = TABLES / "ba_validation_extended_dispersion.csv"
RELEVANCE_TABLE = TABLES / "ba_validation_national_relevance.csv"
WEIGHTED_DISTRIBUTION_TABLE = TABLES / "ba_validation_weighted_distributions.csv"


# Largest `|N^BA − (1 − R^BA)|` the §14.2 identity may show before the outcomes
# are treated as inconsistently built.
_IDENTITY_TOLERANCE = 1e-9


def task_ba_validation(
    analysis_sample_file: Path = _ANALYSIS_SAMPLE_MAIN,
    municipality_crosswalk_file: Path = _MUNICIPALITY_CROSSWALK,
    jobcenter_crosswalk_file: Path = JOBCENTER_CROSSWALK,
    ba_outcomes_file: Path = BA_OUTCOMES,
    ba_wohnkosten_file: Path = BA_WOHNKOSTEN,
    zensus_rents_file: Path = ZENSUS_RENTS,
    proxy_error_file: Path = PROXY_ERROR_FRAME,
    validation_frame_file: Annotated[Path, Product] = BA_VALIDATION_FRAME,
    coverage_file: Annotated[Path, Product] = COVERAGE_TABLE,
    specifications_file: Annotated[Path, Product] = SPECIFICATIONS_TABLE,
    variation_file: Annotated[Path, Product] = VARIATION_TABLE,
    extended_dispersion_file: Annotated[Path, Product] = EXTENDED_DISPERSION_TABLE,
    relevance_file: Annotated[Path, Product] = RELEVANCE_TABLE,
    weighted_distribution_file: Annotated[
        Path,
        Product,
    ] = WEIGHTED_DISTRIBUTION_TABLE,
) -> None:
    """Assemble the §14 frame and write every P1.2 dataset and table."""
    analysis_sample = pd.read_parquet(analysis_sample_file)
    municipality_crosswalk = pd.read_parquet(municipality_crosswalk_file)
    jobcenter_crosswalk = pd.read_parquet(jobcenter_crosswalk_file)
    ba_outcomes = pd.read_parquet(ba_outcomes_file)
    ba_long = pd.read_parquet(ba_wohnkosten_file)
    zensus_rents = pd.read_parquet(zensus_rents_file)
    proxy_error = pd.read_parquet(proxy_error_file)

    _fail_if_identity_broken(ba_outcomes)

    coverage = kreis_coverage(
        jobcenter_crosswalk,
        municipality_crosswalk,
        kdu_kreise=frozenset(analysis_sample["district_ags"].astype(str)),
    )
    fail_if_unexpected_kreis_absent(coverage)

    frame = build_validation_frame(
        analysis_sample=analysis_sample,
        municipality_crosswalk=municipality_crosswalk,
        jobcenter_crosswalk=jobcenter_crosswalk,
        ba_outcomes=ba_outcomes,
        ba_long=ba_long,
        zensus_rents=zensus_rents,
    )
    stocks = read_bedarfsgemeinschaft_stocks(ba_long, region_level="kreis")
    comparable = proxy_error.loc[
        (proxy_error["benchmark_variant"] == str(PRIMARY_BENCHMARK))
        & proxy_error["comparable"].astype(bool)
    ]
    relevance = nationally_weighted_relevance(comparable, stocks)

    validation_frame_file.parent.mkdir(parents=True, exist_ok=True)
    coverage_file.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(validation_frame_file, index=False)
    coverage.to_csv(coverage_file, index=False)
    specification_table(frame).to_csv(specifications_file, index=False)
    regressor_variation(frame).to_csv(variation_file, index=False)
    extended_sample_dispersion(frame).to_csv(extended_dispersion_file, index=False)
    relevance.to_csv(relevance_file, index=False)
    weighted_error_distributions(comparable, stocks).to_csv(
        weighted_distribution_file,
        index=False,
    )
    _register_tables(coverage, relevance)


def _register_tables(coverage: pd.DataFrame, relevance: pd.DataFrame) -> None:
    """Record the six §14 tables the results text reads its numbers from."""
    absent = int((coverage["status"] == "absent_from_kdu_table").sum())
    h1 = relevance.loc[relevance["household_size"] == 1].iloc[0]
    entries = (
        (
            COVERAGE_TABLE,
            f"Every Kreis the BA reports, labelled by whether it carries a "
            f"main-sample cap; {absent} is absent from the KdU table "
            f"altogether and is reported as such rather than dropped.",
            "A coverage ledger, not a result: it says which Kreise can be "
            "compared, never how well any of them performs.",
        ),
        (
            SPECIFICATIONS_TABLE,
            "One row per §14.4 regression, with the Jobcenter-clustered and "
            "the classical standard error side by side, so the cost of "
            "ignoring the clustering is visible.",
            "Every coefficient is an association under Bundesland and "
            "household-size fixed effects; none is a causal effect, and the "
            "`exact_ratio` rows rest on a degenerate regressor (D7, §20).",
        ),
        (
            VARIATION_TABLE,
            "The standard deviation and IQR of each regressor inside each "
            "linkage group, which is what shows the `exact_ratio` group has no "
            "identifying variation in log(K/W) at all.",
            "A statement about the regressor, not about the outcome: low "
            "variation means no evidence either way, never evidence of no "
            "association.",
        ),
        (
            EXTENDED_DISPERSION_TABLE,
            "The within-Jobcenter spread of the cap for the six Jobcenter that "
            "span several Kreise, beside the main sample where it collapses to "
            "one Jobcenter, one Kreis, one cap.",
            "The extended sample is robustness only: six clusters cannot "
            "support a coefficient, and its estimates are indistinguishable "
            "from zero.",
        ),
        (
            RELEVANCE_TABLE,
            f"The nationally weighted proxy error: weighting Kreise by their "
            f"Bedarfsgemeinschaft stock gives {h1['bg_weighted_mean']:.2f} € "
            f"per month at household size 1 against an unweighted Kreis mean "
            f"of {h1['unweighted_mean']:.2f} €.",
            "The BG weights are Kreis-level, so the figure is what the "
            "caseload is exposed to on average, not what any Bedarfsgemeinschaft "
            "receives; a cap is not an actual KdU payment.",
        ),
        (
            WEIGHTED_DISTRIBUTION_TABLE,
            "The quantiles of the proxy error under each §8.2 weighting, which "
            "is where the three weightings visibly diverge rather than agree.",
            "Quantiles of an administrative difference across Kreise; they "
            "describe the distribution of a parameter gap and say nothing "
            "about housing markets.",
        ),
    )
    for path, interpretation, limitation in entries:
        register_result(
            filename=path.name,
            analysis_module="P1.2",
            dataset="ba_validation_jobcenter_household.parquet",
            script="src/kdu/analysis/task_ba_validation.py",
            interpretation=interpretation,
            limitation=limitation,
        )


def extended_sample_dispersion(frame: pd.DataFrame) -> pd.DataFrame:
    """Report the §14.3 within-Jobcenter spread of the extended sample.

    §14.3 asks for the population-weighted KdU mean, the minimum, the maximum
    and the standard deviation inside every Jobcenter that spans several policy
    regions, and it treats the results as robustness. The same columns are
    written for the main sample so a reader can see that they collapse there:
    one Jobcenter, one Kreis, one cap.

    Args:
        frame: Output of `build_validation_frame`.

    Returns:
        One row per Jobcenter and household size, extended sample first.

    """
    columns = [
        CLUSTER_COLUMN,
        "jobcenter_label",
        "validation_sample",
        "household_size",
        "n_kreise",
        "n_gemeinden",
        "population",
        CAP_COLUMN,
        "kdu_cap_min",
        "kdu_cap_max",
        "kdu_cap_sd_within_jobcenter",
    ]
    table = frame.loc[:, columns].copy()
    table["is_robustness_only"] = (
        table["validation_sample"] == ValidationSample.EXTENDED.value
    )
    return table.sort_values(
        ["is_robustness_only", CLUSTER_COLUMN, "household_size"],
        ascending=[False, True, True],
    ).reset_index(drop=True)


def _fail_if_identity_broken(ba_outcomes: pd.DataFrame) -> None:
    deviation = non_recognised_identity_deviation(ba_outcomes)
    if deviation > _IDENTITY_TOLERANCE:
        msg = (
            f"N^BA and R^BA are not complements: the largest |N − (1 − R)| is "
            f"{deviation:.3e}, above the tolerance {_IDENTITY_TOLERANCE:.1e}. "
            f"§14.2 defines them as complements, so the outcomes were built "
            f"inconsistently and must be rebuilt before any §14 result is used."
        )
        raise ValueError(msg)
