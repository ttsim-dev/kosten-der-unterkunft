"""P1.2 — validate the local KdU caps against the BA Wohnkostendaten (§14).

The BA publishes, per Jobcenter and household size, the mean *actual* and the
mean *recognised* Bruttokaltmiete of Bedarfsgemeinschaften living in
Mietunterkünfte. The difference between the two is an administrative fact
observed in the field, and §14 asks whether it moves with the local KdU cap `K`
that this project collected from the Richtlinien.

The public surface is:

- `build_validation_frame` — one row per Jobcenter × household size, carrying
  `K`, the Wohngeld benchmark `W`, the Zensus market rent `M`, the three §14.2
  BA outcomes and the BG stock
- `aggregate_kdu_to_kreis`, `aggregate_kreis_to_jobcenter`,
  `aggregate_market_rent_to_kreis` — the §14.3 spatial aggregation, with the
  §14.3 within-Jobcenter dispersion for the extended sample
- `kreis_coverage` and `fail_if_unexpected_kreis_absent` — what happened to
  every BA Kreis, Hanau included
- `fit_specification` and `specification_table` — the three §14.4 descriptive
  specifications, clustered on the Jobcenter
- `regressor_variation` — how much identifying variation each linkage group
  actually contributes
- `nationally_weighted_relevance` — the §14.5 `D̄^BG_h`
- `select_linkage_rows` — draw one linkage group, sample and household range
- `binscatter`, `recognition_rate_by_decile`, `weighted_error_distributions` —
  the three §14 figures
- `table_5` and `interpretation` — the §19 table and the §21 reading

Four properties govern everything here.

**It is descriptive, and the language says so.** §14.4 states outright that the
focus is effect sizes, binscatters and robustness rather than causal
interpretation, and §20 forbids "causal effect", "generosity" and
"restrictiveness" in any language. Every coefficient below is an *association*
between two administrative parameters measured on the same territory, and the
local cap is itself endogenous to the local housing market.

**Standard errors cluster on the Jobcenter.** §14.4 is explicit about this
because several household sizes appear per Jobcenter and their residuals are
not independent draws. The classical standard error is reported beside the
clustered one only to show how much the clustering matters.

**The policy region is the Kreis (D1), and the Jobcenter is not.** The KdU cap
is set by the Kreis, so aggregation runs Gemeinde → Kreis → Jobcenter. For the
398 main-sample Jobcenter the second step is an identity; for the 6 that span
several Kreise it is a population-weighted mean whose min, max and within-
Jobcenter standard deviation are reported alongside, and §14.3 admits those
results as robustness only. Berlin runs the other way — twelve Jobcenter share
Kreis 11000 — so all twelve inherit that one Kreis's cap.

**The two linkage groups are both reported (D7, A12).** Where a Kreis adopted
the § 12 WoGG table plus the 10 % Sicherheitszuschlag, `K/W` is a constant by
construction, so specification 1's regressor carries no identifying variation
there. `regressor_variation` measures that directly rather than leaving it to
be assumed, and every specification and figure is produced for the `exact_ratio`
group and for the broader `linked_union` group.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import cast

import numpy as np
import pandas as pd

from kdu.config import (
    LEGAL_VINTAGE,
    WOGG_SAFETY_MARKUP,
    WOGG_SAFETY_MARKUP_TOLERANCE,
)

# The local KdU cap `K`, the maximal recognised Bruttokaltmiete, in euro.
CAP_COLUMN = "kdu_cap_eur"

# The primary Wohngeld benchmark `W`, the base Höchstbetrag alone (D6).
BENCHMARK_COLUMN = "wogg_cap_eur"

# The Zensus market rent `M^market`, in euro per month for the local Wohnfläche.
MARKET_RENT_COLUMN = "market_rent_eur"

# The §14.2 non-recognised cost share `N^BA`.
NON_RECOGNISED_COLUMN = "ba_non_recognised_share"

# The §14.2 recognition rate `R^BA`.
RECOGNITION_COLUMN = "ba_recognition_rate"

# The §14.2 euro difference `G^BA`, actual minus recognised Bruttokaltmiete.
GAP_COLUMN = "ba_gap_eur"

# The unit §14.4 clusters standard errors on.
CLUSTER_COLUMN = "jobcenter_id"

# `log(K/W)`, the regressor of specification 1.
LOG_CAP_RATIO_COLUMN = "log_cap_over_benchmark"

# `log(M/K)`, the market–KdU pressure indicator and regressor of specification 2.
LOG_MARKET_PRESSURE_COLUMN = "log_market_over_cap"

# BA cost concept the validation runs on: §14.1 point 5's Bruttokaltmiete,
# measured per Bedarfsgemeinschaft rather than per square metre.
BA_COST_COMPONENT = "bruttokaltmiete"
BA_BASIS = "per_bg"

# Zensus measure carrying the mean Bestandsmiete. Never an Angebotsmiete (A10).
ZENSUS_RENT_MEASURE = "bestandsmiete_nettokalt_eur_per_sqm_mean"

# Kreise the BA reports that `data/kdu_gemeinden.csv` does not contain, with the
# reason each is missing. Every one of them is reported rather than dropped, and
# `fail_if_unexpected_kreis_absent` refuses any Kreis not listed here (A10).
KREISE_ABSENT_FROM_KDU_TABLE: MappingProxyType[str, str] = MappingProxyType(
    {
        "06415": (
            "Hanau is a 401st Kreis the BA reports from 2026-01 onwards. It is "
            "absent from data/kdu_gemeinden.csv, which was collected on the "
            "400-Kreis boundary set, so no local cap exists for it."
        ),
    },
)

# Share of a Jobcenter's population that must fall in flagged Gemeinden before
# the Jobcenter itself counts as WoGG-linked. A Jobcenter is one BA reporting
# unit, so the group it belongs to has to be decided for the unit as a whole.
LINKAGE_MAJORITY_SHARE = 0.5

# Household sizes the §14.4 specifications are fitted on. D3 balances
# `analysis_sample_main` over h = 1…4, so no h = 5 cap exists to fit.
SPECIFICATION_HOUSEHOLD_SIZES: tuple[int, ...] = (1, 2, 3, 4)

# Household sizes the frame admits from either side. It reaches only h = 4 in
# practice, because D3 balances `analysis_sample_main` over h = 1…4 and the
# frame is keyed on the KdU side; h = 5 is carried here so that an h = 5 cap
# would flow through without a code change.
FRAME_HOUSEHOLD_SIZES: tuple[int, ...] = (1, 2, 3, 4, 5)

# Value the `household_sizes` column carries for the h = 1…4 grid, so a reader
# of the specification table can tell which household range a row was fitted on.
MAIN_HOUSEHOLD_SIZES_LABEL = "+".join(str(h) for h in SPECIFICATION_HOUSEHOLD_SIZES)

# Number of bins the §14 binscatter and the decile figure use.
BINSCATTER_BINS = 20
DECILE_BINS = 10


class Specification(StrEnum):
    """The three descriptive specifications of §14.4."""

    CAP_VS_BENCHMARK = "cap_vs_benchmark"
    """`N^BA = alpha_h + β·log(K/W) + λ_Bundesland + ε`."""
    MARKET_VS_CAP = "market_vs_cap"
    """`N^BA = alpha_h + β·log(M^market/K) + λ_Bundesland + ε`."""
    GAP_ON_LEVELS = "gap_on_levels"
    """`G^BA = alpha_h + β₁·K + β₂·M^market + λ_Bundesland + ε`."""


class LinkageGroup(StrEnum):
    """How a result treats the WoGG-linked Kreise, under both A12 definitions."""

    ALL = "all"
    """Every Jobcenter; never to be read as an empirical regularity on its own."""
    EXCLUDING_EXACT_RATIO = "excluding_exact_ratio"
    """Drops Jobcenter whose population mostly sits at `K/W = 1.100` (5e-4)."""
    EXACT_RATIO_ONLY = "exact_ratio_only"
    """Only those Jobcenter — the group D7's quoted table describes."""
    EXCLUDING_LINKED_UNION = "excluding_linked_union"
    """Drops Jobcenter flagged by the union of D7's two detectors (A8 item 2)."""
    LINKED_UNION_ONLY = "linked_union_only"
    """Only those — the right group when asking who leans on the WoGG table."""


class ValidationSample(StrEnum):
    """The two §14.3 samples, decided per Jobcenter and never per row."""

    MAIN = "main"
    """Jobcenter serving exactly one Kreis; 398 of them, covering 387 Kreise."""
    EXTENDED = "extended"
    """Jobcenter spanning several Kreise; 6 of them, covering 14 Kreise."""


class KreisStatus(StrEnum):
    """What became of a Kreis the BA reports, once the KdU table is joined."""

    MAIN_SAMPLE_CAP = "main_sample_cap"
    """A Bruttokaltmiete cap from `analysis_sample_main` is available."""
    NO_MAIN_SAMPLE_CAP = "no_main_sample_cap"
    """The Kreis is in the KdU table but contributes no main-sample cap (D3)."""
    ABSENT_FROM_KDU_TABLE = "absent_from_kdu_table"
    """The Kreis is not in `data/kdu_gemeinden.csv` at all; Hanau (A10)."""


@dataclass(frozen=True)
class LeastSquaresFit:
    """One fitted linear specification with classical and clustered errors."""

    names: tuple[str, ...]
    """Column names of the design matrix, in order."""
    estimates: np.ndarray = field(repr=False)
    """Point estimates, aligned with `names`."""
    classical_standard_errors: np.ndarray = field(repr=False)
    """Homoskedastic standard errors, reported only for comparison."""
    cluster_standard_errors: np.ndarray = field(repr=False)
    """Standard errors clustered on the Jobcenter, as §14.4 requires."""
    residuals: np.ndarray = field(repr=False)
    """Residuals, in the units of the outcome."""
    n_obs: int
    """Jobcenter-by-household-size rows entering the fit."""
    n_clusters: int
    """Distinct Jobcenter, which are the clusters."""
    rank: int
    """Rank of the design matrix, used as the parameter count."""
    r_squared: float
    """Share of the outcome variation the specification accounts for."""

    def _index(self, name: str) -> int:
        if name not in self.names:
            msg = f"No coefficient named {name!r}; the design holds {self.names}"
            raise KeyError(msg)
        return self.names.index(name)

    def estimate(self, name: str) -> float:
        """Return the point estimate on `name`."""
        return float(self.estimates[self._index(name)])

    def classical_se(self, name: str) -> float:
        """Return the homoskedastic standard error on `name`."""
        return float(self.classical_standard_errors[self._index(name)])

    def cluster_se(self, name: str) -> float:
        """Return the Jobcenter-clustered standard error on `name`."""
        return float(self.cluster_standard_errors[self._index(name)])


@dataclass(frozen=True)
class DescriptiveFit:
    """One §14.4 specification, fitted on one linkage group and one sample."""

    specification: Specification
    """Which of the three specifications was fitted."""
    linkage_group: LinkageGroup
    """Which WoGG-linkage group the rows were drawn from (A12)."""
    validation_sample: ValidationSample
    """Whether the §14.3 main or extended Jobcenter sample was used."""
    household_sizes: tuple[int, ...]
    """Household sizes admitted; `alpha_h` is a fixed effect over them."""
    fit: LeastSquaresFit = field(repr=False)
    """The underlying least-squares fit."""
    regressors: tuple[str, ...]
    """The regressors of interest, excluding the fixed effects and intercept."""
    regressor_sd: MappingProxyType[str, float]
    """Standard deviation of each regressor on the rows that were fitted."""

    @property
    def beta(self) -> float:
        """Point estimate on the first regressor of interest."""
        return self.fit.estimate(self.regressors[0])

    @property
    def n_obs(self) -> int:
        """Jobcenter-by-household-size rows entering the fit."""
        return self.fit.n_obs

    @property
    def n_clusters(self) -> int:
        """Distinct Jobcenter the standard errors cluster on."""
        return self.fit.n_clusters

    def as_rows(self) -> list[dict[str, object]]:
        """Render one table row per regressor of interest."""
        return [
            {
                "specification": self.specification.value,
                "linkage_group": self.linkage_group.value,
                "validation_sample": self.validation_sample.value,
                "household_sizes": "+".join(str(h) for h in self.household_sizes),
                "regressor": name,
                "estimate": self.fit.estimate(name),
                "cluster_se": self.fit.cluster_se(name),
                "classical_se": self.fit.classical_se(name),
                "t_clustered": _safe_ratio(
                    self.fit.estimate(name),
                    self.fit.cluster_se(name),
                ),
                "regressor_sd": self.regressor_sd[name],
                "n_obs": self.fit.n_obs,
                "n_clusters": self.fit.n_clusters,
                "n_parameters": self.fit.rank,
                "r_squared": self.fit.r_squared,
                "spatial_unit": "jobcenter",
            }
            for name in self.regressors
        ]


def build_validation_frame(
    analysis_sample: pd.DataFrame,
    municipality_crosswalk: pd.DataFrame,
    jobcenter_crosswalk: pd.DataFrame,
    ba_outcomes: pd.DataFrame,
    ba_long: pd.DataFrame,
    zensus_rents: pd.DataFrame,
) -> pd.DataFrame:
    """Assemble the one §14 analysis frame, keyed Jobcenter × household size.

    Aggregation runs Gemeinde → Kreis → Jobcenter, because D1 makes the Kreis
    the policy region while the BA reports on the Jobcenter. The Zensus market
    rent enters as `€/m² × A^max`, so `M^market` is comparable in level with
    `K`; because the Zensus figure is a Nettokaltmiete and `K` a
    Bruttokaltmiete, `M/K` understates market pressure by the kalte
    Betriebskosten and must be read as an indicator, not as a level statement.

    Args:
        analysis_sample: `analysis_sample_main.parquet`.
        municipality_crosswalk: `municipality_crosswalk.parquet`.
        jobcenter_crosswalk: `jobcenter_kreis_crosswalk.parquet`.
        ba_outcomes: `ba_validation_outcomes.parquet`.
        ba_long: `ba_wohnkosten_long.parquet`, for the BG stocks.
        zensus_rents: `zensus_rents_gemeinden.parquet`.

    Returns:
        One row per Jobcenter and household size in `FRAME_HOUSEHOLD_SIZES`.

    """
    kreis = aggregate_kdu_to_kreis(analysis_sample, municipality_crosswalk)
    market = aggregate_market_rent_to_kreis(zensus_rents, municipality_crosswalk)
    jobcenter = aggregate_kreis_to_jobcenter(
        kreis.merge(market, on="ags_kreis", how="left"),
        jobcenter_crosswalk,
    )
    frame = jobcenter.merge(
        read_ba_outcomes(ba_outcomes),
        on=[CLUSTER_COLUMN, "household_size"],
        how="left",
    ).merge(
        read_bedarfsgemeinschaft_stocks(ba_long, region_level="jobcenter"),
        on=[CLUSTER_COLUMN, "household_size"],
        how="left",
    )
    return stamp_regressors(frame)


def aggregate_kdu_to_kreis(
    analysis_sample: pd.DataFrame,
    municipality_crosswalk: pd.DataFrame,
) -> pd.DataFrame:
    """Collapse the Gemeinde-level caps to the Kreis, weighted by population.

    D1 makes the Kreis the policy region, but 210 of 400 Kreise define
    Vergleichsräume internally and so carry more than one cap. The
    population-weighted mean is what a Kreis-level model would use; the min,
    max and within-Kreis standard deviation travel with it so the dispersion
    the mean hides stays visible.

    Args:
        analysis_sample: `analysis_sample_main.parquet`.
        municipality_crosswalk: Supplies the Gemeinde population (D8).

    Returns:
        `ags_kreis × household_size` with `K`, `W`, `A^max` and the dispersion.

    """
    frame = analysis_sample.loc[
        analysis_sample["household_size"].isin(FRAME_HOUSEHOLD_SIZES),
        [
            "ags",
            "household_size",
            "kdu_bkc_cap",
            "wogg_base_cap",
            "max_area_sqm",
            "wogg_linked_flag",
            "district_ags",
            "state_name",
        ],
    ].merge(
        municipality_crosswalk[["ags", "population"]],
        on="ags",
        how="left",
    )
    frame = frame.rename(columns={"district_ags": "ags_kreis"})
    frame["at_exact_ratio"] = _at_exact_ratio(frame).astype(float)
    frame["in_linked_union"] = (
        frame["wogg_linked_flag"].astype("boolean").fillna(value=False).astype(float)
    )
    means = weighted_mean_by(
        frame,
        keys=("ags_kreis", "household_size"),
        value_columns=(
            "kdu_bkc_cap",
            "wogg_base_cap",
            "max_area_sqm",
            "at_exact_ratio",
            "in_linked_union",
        ),
        weight_column="population",
    ).rename(
        columns={
            "kdu_bkc_cap": CAP_COLUMN,
            "wogg_base_cap": BENCHMARK_COLUMN,
            "max_area_sqm": "max_area_sqm",
            "at_exact_ratio": "share_at_exact_ratio",
            "in_linked_union": "share_linked_union",
        },
    )
    dispersion = (
        frame.groupby(["ags_kreis", "household_size"], as_index=False)
        .agg(
            kdu_cap_min=("kdu_bkc_cap", "min"),
            kdu_cap_max=("kdu_bkc_cap", "max"),
            kdu_cap_sd_within_kreis=("kdu_bkc_cap", _population_free_sd),
            kreis_population=("population", "sum"),
            n_gemeinden=("ags", "nunique"),
            state_name=("state_name", "first"),
        )
        .astype({"kreis_population": float})
    )
    return means.merge(dispersion, on=["ags_kreis", "household_size"], how="left")


def aggregate_market_rent_to_kreis(
    zensus_rents: pd.DataFrame,
    municipality_crosswalk: pd.DataFrame,
) -> pd.DataFrame:
    """Collapse the Zensus Bestandsmiete per square metre to the Kreis.

    The Zensus publishes the mean Nettokaltmiete per square metre per Gemeinde;
    §14.4's `M^market` is a Kreis-level figure, so the Gemeinde values are
    averaged with population weights. A11 records what is *not* available: the
    mean rent *within a floor-area class*, which would let small dwellings carry
    their higher per-square-metre price. Without it the single-person market
    rent is understated, in a known direction.

    Args:
        zensus_rents: `zensus_rents_gemeinden.parquet`.
        municipality_crosswalk: Supplies the Gemeinde population and Kreis.

    Returns:
        `ags_kreis` with `market_rent_eur_per_sqm` and its population coverage.

    """
    rents = zensus_rents.loc[
        zensus_rents["measure"] == ZENSUS_RENT_MEASURE,
        ["ags_gemeinde", "value"],
    ].rename(columns={"ags_gemeinde": "ags", "value": "market_rent_eur_per_sqm"})
    joined = municipality_crosswalk[["ags", "ags_kreis", "population"]].merge(
        rents,
        on="ags",
        how="left",
    )
    means = weighted_mean_by(
        joined,
        keys=("ags_kreis",),
        value_columns=("market_rent_eur_per_sqm",),
        weight_column="population",
    )
    covered = (
        joined.loc[joined["market_rent_eur_per_sqm"].notna()]
        .groupby("ags_kreis", as_index=False)["population"]
        .sum()
        .rename(columns={"population": "market_rent_population_covered"})
        .astype({"market_rent_population_covered": float})
    )
    return means.merge(covered, on="ags_kreis", how="left")


def aggregate_kreis_to_jobcenter(
    kreis_frame: pd.DataFrame,
    jobcenter_crosswalk: pd.DataFrame,
) -> pd.DataFrame:
    """Map the Kreis-level caps onto the Jobcenter the BA reports on (§14.3).

    For the 398 main-sample Jobcenter this is an identity: one Jobcenter, one
    Kreis, one policy region. For the 6 that span several Kreise it is a
    population-weighted mean, and §14.3's min, max and within-Jobcenter standard
    deviation travel with it so that those rows can be read as the robustness
    they are. Berlin's 12 Bezirks-Jobcenter each inherit Kreis 11000, which is
    one policy region and therefore one cap.

    Args:
        kreis_frame: Output of `aggregate_kdu_to_kreis`, market rent joined on.
        jobcenter_crosswalk: `jobcenter_kreis_crosswalk.parquet`.

    Returns:
        `jobcenter_id × household_size` with the aggregated levels.

    """
    joined = jobcenter_crosswalk[
        [CLUSTER_COLUMN, "jobcenter_label", "ags_kreis", "sample", "is_kreisfrei"]
    ].merge(kreis_frame, on="ags_kreis", how="left")
    usable = joined.loc[joined["household_size"].notna()].copy()
    usable["household_size"] = usable["household_size"].astype(int)
    means = weighted_mean_by(
        usable,
        keys=(CLUSTER_COLUMN, "household_size"),
        value_columns=(
            CAP_COLUMN,
            BENCHMARK_COLUMN,
            "max_area_sqm",
            "market_rent_eur_per_sqm",
            "share_at_exact_ratio",
            "share_linked_union",
        ),
        weight_column="kreis_population",
    )
    metadata = usable.groupby([CLUSTER_COLUMN, "household_size"], as_index=False).agg(
        jobcenter_label=("jobcenter_label", "first"),
        validation_sample=("sample", "first"),
        is_kreisfrei=("is_kreisfrei", "first"),
        state_name=("state_name", "first"),
        n_kreise=("ags_kreis", "nunique"),
        n_gemeinden=("n_gemeinden", "sum"),
        population=("kreis_population", "sum"),
        kdu_cap_min=(CAP_COLUMN, "min"),
        kdu_cap_max=(CAP_COLUMN, "max"),
        kdu_cap_sd_within_jobcenter=(CAP_COLUMN, _population_free_sd),
    )
    return means.merge(metadata, on=[CLUSTER_COLUMN, "household_size"], how="left")


def read_ba_outcomes(ba_outcomes: pd.DataFrame) -> pd.DataFrame:
    """Reduce the §14.2 outcomes to Jobcenter × household size, wide over outcome.

    Args:
        ba_outcomes: `ba_validation_outcomes.parquet`.

    Returns:
        `jobcenter_id`, `household_size`, `N^BA`, `R^BA`, `G^BA`.

    """
    selected = ba_outcomes.loc[
        (ba_outcomes["region_level"] == "jobcenter")
        & (ba_outcomes["breakdown"] == "household_size")
        & (ba_outcomes["cost_component"] == BA_COST_COMPONENT)
        & (ba_outcomes["basis"] == BA_BASIS),
        ["region_code", "category", "outcome", "value"],
    ].copy()
    selected["household_size"] = _household_size_from_category(selected["category"])
    selected = selected.loc[selected["household_size"].isin(FRAME_HOUSEHOLD_SIZES)]
    wide = selected.pivot_table(
        index=["region_code", "household_size"],
        columns="outcome",
        values="value",
        aggfunc="mean",
    ).reset_index()
    wide.columns.name = None
    return wide.rename(columns={"region_code": CLUSTER_COLUMN})


def read_bedarfsgemeinschaft_stocks(
    ba_long: pd.DataFrame,
    region_level: str,
) -> pd.DataFrame:
    """Reduce the BA table to the BG stock by region and household size.

    Args:
        ba_long: `bld/ba_wohnkosten_long.parquet`.
        region_level: `"jobcenter"` or `"kreis"`.

    Returns:
        The region code, `household_size` and `bg_stock`.

    """
    stocks = ba_long.loc[
        (ba_long["measure"] == "bg_stock")
        & (ba_long["region_level"] == region_level)
        & (ba_long["breakdown"] == "household_size"),
        ["region_code", "category", "value"],
    ].copy()
    stocks["household_size"] = _household_size_from_category(stocks["category"])
    stocks = stocks.loc[stocks["household_size"].isin(FRAME_HOUSEHOLD_SIZES)]
    key = CLUSTER_COLUMN if region_level == "jobcenter" else "policy_region_id"
    return (
        stocks.groupby(["region_code", "household_size"], as_index=False)["value"]
        .sum()
        .rename(columns={"region_code": key, "value": "bg_stock"})
        .astype({"bg_stock": float})
    )


def kreis_coverage(
    jobcenter_crosswalk: pd.DataFrame,
    municipality_crosswalk: pd.DataFrame,
    kdu_kreise: frozenset[str],
) -> pd.DataFrame:
    """Report what became of every Kreis the BA publishes (§14.3, Gate 4).

    Three outcomes are possible, and each is named rather than left to a silent
    join: the Kreis contributes a main-sample cap; it is in the KdU table but
    D3's completeness rule leaves it without one; or it is not in the KdU table
    at all, which is Hanau and only Hanau.

    Args:
        jobcenter_crosswalk: `jobcenter_kreis_crosswalk.parquet`.
        municipality_crosswalk: The 400-Kreis KdU universe.
        kdu_kreise: Kreise contributing at least one main-sample cap.

    Returns:
        One row per Kreis with `status`, `reason` and its Jobcenter.

    """
    known = set(municipality_crosswalk["ags_kreis"].astype(str))
    coverage = jobcenter_crosswalk[[CLUSTER_COLUMN, "ags_kreis", "sample"]].copy()
    coverage["ags_kreis"] = coverage["ags_kreis"].astype(str)
    in_table = coverage["ags_kreis"].isin(known)
    has_cap = coverage["ags_kreis"].isin(set(kdu_kreise))
    coverage["status"] = np.select(
        [~in_table, has_cap],
        [KreisStatus.ABSENT_FROM_KDU_TABLE.value, KreisStatus.MAIN_SAMPLE_CAP.value],
        default=KreisStatus.NO_MAIN_SAMPLE_CAP.value,
    )
    coverage["reason"] = coverage["ags_kreis"].map(dict(KREISE_ABSENT_FROM_KDU_TABLE))
    coverage["reason"] = coverage["reason"].fillna(
        pd.Series(
            np.where(
                coverage["status"] == KreisStatus.NO_MAIN_SAMPLE_CAP.value,
                "No Bruttokaltmiete cap balanced over h = 1…4 (D3).",
                "",
            ),
            index=coverage.index,
        ),
    )
    return coverage.sort_values(["status", "ags_kreis"]).reset_index(drop=True)


def fail_if_unexpected_kreis_absent(coverage: pd.DataFrame) -> None:
    """Raise unless every Kreis missing from the KdU table is a documented one.

    A future boundary reform would otherwise add a Kreis the BA reports and this
    project has no cap for, and the join would drop it without a word.

    Args:
        coverage: Output of `kreis_coverage`.

    Raises:
        ValueError: If an undocumented Kreis is absent from the KdU table.

    """
    absent = set(
        coverage.loc[
            coverage["status"] == KreisStatus.ABSENT_FROM_KDU_TABLE.value,
            "ags_kreis",
        ].astype(str),
    )
    unexpected = sorted(absent - set(KREISE_ABSENT_FROM_KDU_TABLE))
    if unexpected:
        msg = (
            f"Kreise {unexpected} are reported by the BA but absent from the KdU "
            f"table, and are not in KREISE_ABSENT_FROM_KDU_TABLE. Add them there "
            f"with a reason, or fix the crosswalk; do not let them drop silently."
        )
        raise ValueError(msg)


def non_recognised_identity_deviation(ba_outcomes: pd.DataFrame) -> float:
    """Return the largest `|N^BA − (1 − R^BA)|` across every published cell.

    §14.2 defines the two as complements, so anything above floating tolerance
    means the outcomes were built inconsistently.

    Args:
        ba_outcomes: `ba_validation_outcomes.parquet`.

    Returns:
        The maximum absolute deviation, or `0.0` if no cell carries both.

    """
    keys = [
        "region_level",
        "region_code",
        "breakdown",
        "category",
        "cost_component",
        "basis",
    ]
    rate = ba_outcomes.loc[ba_outcomes["outcome"] == RECOGNITION_COLUMN]
    share = ba_outcomes.loc[ba_outcomes["outcome"] == NON_RECOGNISED_COLUMN]
    paired = (
        rate.set_index(keys)["value"]
        .rename("rate")
        .to_frame()
        .join(
            share.set_index(keys)["value"].rename("share"),
            how="inner",
        )
    )
    paired = paired.dropna()
    if paired.empty:
        return 0.0
    return float((paired["share"] - (1.0 - paired["rate"])).abs().max())


def fit_specification(
    frame: pd.DataFrame,
    specification: Specification,
    linkage_group: LinkageGroup,
    validation_sample: ValidationSample = ValidationSample.MAIN,
    household_sizes: Sequence[int] = SPECIFICATION_HOUSEHOLD_SIZES,
    weight_column: str | None = None,
) -> DescriptiveFit | None:
    """Fit one §14.4 specification with Bundesland fixed effects.

    `alpha_h` enters as a household-size fixed effect and `λ_Bundesland` as a state
    fixed effect. Standard errors cluster on the Jobcenter, because several
    household sizes appear per Jobcenter (§14.4).

    Args:
        frame: Output of `build_validation_frame`.
        specification: Which of the three §14.4 specifications to fit.
        linkage_group: Which WoGG-linkage group to draw rows from (A12).
        validation_sample: Main or extended §14.3 Jobcenter sample.
        household_sizes: Sizes admitted; `alpha_h` runs over them.
        weight_column: Optional Berichtsgewicht, for example `"bg_stock"`.

    Returns:
        The fit, or `None` where the group holds too few rows to fit at all.

    """
    outcome_column, regressors = _specification_terms(specification)
    rows = select_linkage_rows(frame, linkage_group, validation_sample, household_sizes)
    needed = [outcome_column, *regressors, "state_name", "household_size"]
    rows = rows.dropna(subset=needed)
    rows = rows.loc[np.isfinite(rows[[*regressors]].to_numpy(dtype=float)).all(axis=1)]
    design = _design_matrix(rows, regressors)
    if len(rows) <= design.shape[1]:
        return None
    fit = fit_least_squares(
        design=design.to_numpy(dtype=float),
        outcome=rows[outcome_column].to_numpy(dtype=float),
        clusters=rows[CLUSTER_COLUMN].to_numpy(),
        names=tuple(str(name) for name in design.columns),
        weights=_weights(rows, weight_column),
    )
    return DescriptiveFit(
        specification=specification,
        linkage_group=linkage_group,
        validation_sample=validation_sample,
        household_sizes=tuple(household_sizes),
        fit=fit,
        regressors=regressors,
        regressor_sd=MappingProxyType(
            {name: float(rows[name].std(ddof=1)) for name in regressors},
        ),
    )


def specification_table(
    frame: pd.DataFrame,
    household_sizes: Sequence[int] = SPECIFICATION_HOUSEHOLD_SIZES,
) -> pd.DataFrame:
    """Fit every §14.4 specification on every linkage group and both samples.

    A12 obliges every specification to be reported for both linkage definitions,
    so the grid runs over all five `LinkageGroup` values. The extended-sample
    rows are produced because §14.3 asks for them and are labelled so they can
    only be read as the robustness they are.

    Args:
        frame: Output of `build_validation_frame`.
        household_sizes: Sizes `alpha_h` runs over.

    Returns:
        One row per specification × linkage group × sample × regressor.

    """
    rows: list[dict[str, object]] = []
    for validation_sample in ValidationSample:
        for specification in Specification:
            for group in LinkageGroup:
                fit = fit_specification(
                    frame,
                    specification=specification,
                    linkage_group=group,
                    validation_sample=validation_sample,
                    household_sizes=household_sizes,
                )
                if fit is not None:
                    rows.extend(fit.as_rows())
    return pd.DataFrame(rows)


def regressor_variation(
    frame: pd.DataFrame,
    validation_sample: ValidationSample = ValidationSample.MAIN,
    household_sizes: Sequence[int] = SPECIFICATION_HOUSEHOLD_SIZES,
) -> pd.DataFrame:
    """Measure how much identifying variation each linkage group contributes.

    Where a Kreis adopted the § 12 WoGG table plus the 10 % Sicherheitszuschlag,
    `K/W` is 1.100 by construction, so `log(K/W)` is a constant and
    specification 1 has nothing to identify `β` from. This reports the spread of
    each regressor per group rather than leaving that to be assumed.

    Args:
        frame: Output of `build_validation_frame`.
        validation_sample: Main or extended §14.3 Jobcenter sample.
        household_sizes: Sizes admitted.

    Returns:
        One row per linkage group and regressor with `sd`, `iqr` and `n_obs`.

    """
    rows: list[dict[str, object]] = []
    for group in LinkageGroup:
        selected = select_linkage_rows(frame, group, validation_sample, household_sizes)
        for name in (LOG_CAP_RATIO_COLUMN, LOG_MARKET_PRESSURE_COLUMN):
            values = pd.to_numeric(selected[name], errors="coerce").replace(
                [np.inf, -np.inf],
                np.nan,
            )
            values = values.dropna()
            rows.append(
                {
                    "linkage_group": group.value,
                    "validation_sample": validation_sample.value,
                    "regressor": name,
                    "n_obs": len(values),
                    "n_jobcenter": int(selected[CLUSTER_COLUMN].nunique()),
                    "sd": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
                    "iqr": (
                        float(values.quantile(0.75) - values.quantile(0.25))
                        if len(values)
                        else np.nan
                    ),
                },
            )
    return pd.DataFrame(rows)


def nationally_weighted_relevance(
    proxy_error: pd.DataFrame,
    stocks: pd.DataFrame,
    measure: str = "proxy_error_eur",
) -> pd.DataFrame:
    """Compute the §14.5 nationally weighted proxy error `D̄^BG_h`.

    `D̄^BG_h = Σ_j BG_jh·D_jh / Σ_j BG_jh`, with `j` the Kreis. The Kreis is
    the right `j` here for two reasons: D1 makes it the policy region, and
    §14.5 restricts BG weighting to the clearly documented extended variant
    wherever a Jobcenter spans several KdU regimes. Because `D_jh` is the
    population-weighted Kreis mean, this reproduces exactly the BG-weighted
    proxy error P0.3 already computes by spreading each Kreis's BG stock over
    its Gemeinden in proportion to population — the two are the same weighted
    average written two ways.

    Args:
        proxy_error: `proxy_error_gemeinde_household.parquet`, already filtered
            to one benchmark variant and to comparable rows.
        stocks: `policy_region_id × household_size × bg_stock`.
        measure: Proxy-error column to average.

    Returns:
        One row per household size with the unweighted, population-weighted and
        BG-weighted means, plus the weight totals each rests on.

    """
    region_means = weighted_mean_by(
        proxy_error.rename(columns={measure: "district_mean"}),
        keys=("policy_region_id", "household_size"),
        value_columns=("district_mean",),
        weight_column="population",
    )
    population = (
        proxy_error.groupby(["policy_region_id", "household_size"], as_index=False)[
            "population"
        ]
        .sum()
        .astype({"population": float})
    )
    joined = region_means.merge(
        population,
        on=["policy_region_id", "household_size"],
        how="left",
    ).merge(
        stocks.astype({"policy_region_id": str, "household_size": int}),
        on=["policy_region_id", "household_size"],
        how="left",
    )
    rows: list[dict[str, object]] = []
    for household_size, group in joined.groupby("household_size", sort=True):
        with_stock = group.dropna(subset=["bg_stock", "district_mean"])
        with_population = group.dropna(subset=["district_mean"])
        rows.append(
            {
                "household_size": cast("int", household_size),
                "measure": measure,
                "unweighted_mean": float(with_population["district_mean"].mean()),
                "population_weighted_mean": _weighted_average(
                    with_population["district_mean"],
                    with_population["population"],
                ),
                "bg_weighted_mean": _weighted_average(
                    with_stock["district_mean"],
                    with_stock["bg_stock"],
                ),
                "n_policy_regions": int(with_population["policy_region_id"].nunique()),
                "n_policy_regions_with_stock": int(
                    with_stock["policy_region_id"].nunique(),
                ),
                "bg_total": float(with_stock["bg_stock"].sum()),
                "population_total": float(with_population["population"].sum()),
            },
        )
    return pd.DataFrame(rows)


def binscatter(
    frame: pd.DataFrame,
    x_column: str,
    y_column: str,
    n_bins: int = BINSCATTER_BINS,
) -> pd.DataFrame:
    """Bin `x_column` into equal-count bins and average both axes inside each.

    Args:
        frame: Rows to bin.
        x_column: Regressor on the horizontal axis.
        y_column: Outcome on the vertical axis.
        n_bins: Number of equal-count bins.

    Returns:
        One row per bin with the two means, the bin edges and its row count.

    """
    usable = frame[[x_column, y_column]].replace([np.inf, -np.inf], np.nan).dropna()
    if usable.empty:
        return pd.DataFrame(
            columns=["bin", x_column, y_column, "x_min", "x_max", "n_obs"],
        )
    bins = min(n_bins, usable[x_column].nunique())
    labels = pd.qcut(usable[x_column].rank(method="first"), q=bins, labels=False)
    grouped = usable.groupby(labels, observed=True)
    return pd.DataFrame(
        {
            "bin": grouped[x_column].mean().index.astype(int),
            x_column: grouped[x_column].mean().to_numpy(),
            y_column: grouped[y_column].mean().to_numpy(),
            "x_min": grouped[x_column].min().to_numpy(),
            "x_max": grouped[x_column].max().to_numpy(),
            "n_obs": grouped[x_column].size().to_numpy(),
        },
    ).reset_index(drop=True)


def recognition_rate_by_decile(
    frame: pd.DataFrame,
    linkage_group: LinkageGroup = LinkageGroup.ALL,
    validation_sample: ValidationSample = ValidationSample.MAIN,
    household_sizes: Sequence[int] = SPECIFICATION_HOUSEHOLD_SIZES,
) -> pd.DataFrame:
    """Average `R^BA` inside each decile of `K/W` (§14 figure 2).

    Args:
        frame: Output of `build_validation_frame`.
        linkage_group: Which WoGG-linkage group to draw rows from.
        validation_sample: Main or extended §14.3 Jobcenter sample.
        household_sizes: Sizes admitted.

    Returns:
        One row per decile with the mean cap ratio, `R^BA` and `N^BA`.

    """
    rows = select_linkage_rows(frame, linkage_group, validation_sample, household_sizes)
    columns = ["cap_over_benchmark", RECOGNITION_COLUMN, NON_RECOGNISED_COLUMN]
    usable = rows[columns].replace([np.inf, -np.inf], np.nan).dropna()
    if usable.empty:
        return pd.DataFrame(columns=["decile", *columns, "n_obs"])
    bins = min(DECILE_BINS, usable["cap_over_benchmark"].nunique())
    labels = pd.qcut(
        usable["cap_over_benchmark"].rank(method="first"),
        q=bins,
        labels=False,
    )
    grouped = usable.groupby(labels, observed=True)
    table = grouped.mean()
    table["n_obs"] = grouped.size()
    table = table.reset_index(names="decile")
    table["decile"] = table["decile"].astype(int) + 1
    table["linkage_group"] = linkage_group.value
    return table


def weighted_error_distributions(
    proxy_error: pd.DataFrame,
    stocks: pd.DataFrame,
    measure: str = "proxy_error_eur",
    quantiles: Sequence[float] = (0.1, 0.25, 0.5, 0.75, 0.9),
) -> pd.DataFrame:
    """Compare the unweighted, population- and BG-weighted proxy-error spread.

    This is §14's third figure. The three weightings answer three different
    questions — what the administrative landscape looks like, what the
    population is exposed to, and what potentially affected households face —
    and the point of showing them together is that they do not coincide.

    Args:
        proxy_error: Kreis-level rows from `nationally_weighted_relevance`'s
            input, already filtered to one benchmark variant.
        stocks: `policy_region_id × household_size × bg_stock`.
        measure: Proxy-error column to describe.
        quantiles: Quantiles to report per weighting.

    Returns:
        One row per household size, weighting and quantile.

    """
    region_means = weighted_mean_by(
        proxy_error.rename(columns={measure: "district_mean"}),
        keys=("policy_region_id", "household_size"),
        value_columns=("district_mean",),
        weight_column="population",
    )
    population = proxy_error.groupby(
        ["policy_region_id", "household_size"],
        as_index=False,
    )["population"].sum()
    joined = region_means.merge(
        population,
        on=["policy_region_id", "household_size"],
        how="left",
    ).merge(
        stocks.astype({"policy_region_id": str, "household_size": int}),
        on=["policy_region_id", "household_size"],
        how="left",
    )
    rows: list[dict[str, object]] = []
    for household_size, group in joined.groupby("household_size", sort=True):
        usable = group.dropna(subset=["district_mean"])
        weightings = {
            "unweighted": pd.Series(1.0, index=usable.index),
            "population": usable["population"].astype(float),
            "bedarfsgemeinschaft": usable["bg_stock"].astype(float).fillna(0.0),
        }
        for name, weights in weightings.items():
            for quantile in quantiles:
                rows.append(  # noqa: PERF401
                    {
                        "household_size": cast("int", household_size),
                        "measure": measure,
                        "weighting": name,
                        "quantile": quantile,
                        "value": weighted_quantile(
                            usable["district_mean"].to_numpy(dtype=float),
                            weights.to_numpy(dtype=float),
                            quantile,
                        ),
                        "n_policy_regions": int(usable["policy_region_id"].nunique()),
                    },
                )
    return pd.DataFrame(rows)


def table_5(
    frame: pd.DataFrame,
    specifications: pd.DataFrame,
    relevance: pd.DataFrame,
    household_sizes: Sequence[int] = SPECIFICATION_HOUSEHOLD_SIZES,
) -> pd.DataFrame:
    """Assemble §19 Table 5, the external-validation summary.

    §19 asks for the BA recognition rate, the market-stress indicator, the
    descriptive regression coefficients, the sample size and the spatial unit
    used. Each linkage group gets its own row so a reader never has to work out
    which group a number belongs to (A12).

    Args:
        frame: Output of `build_validation_frame`.
        specifications: Output of `specification_table`.
        relevance: Output of `nationally_weighted_relevance`.
        household_sizes: Sizes the rows are computed on.

    Returns:
        One row per linkage group, plus a national relevance block.

    """
    rows: list[dict[str, object]] = []
    for group in LinkageGroup:
        selected = select_linkage_rows(
            frame,
            group,
            ValidationSample.MAIN,
            household_sizes,
        ).dropna(subset=[NON_RECOGNISED_COLUMN])
        if selected.empty:
            continue
        rows.append(
            {
                "linkage_group": group.value,
                "validation_sample": ValidationSample.MAIN.value,
                "spatial_unit": "jobcenter",
                "n_obs": len(selected),
                "n_jobcenter": int(selected[CLUSTER_COLUMN].nunique()),
                "median_recognition_rate": float(
                    selected[RECOGNITION_COLUMN].median(),
                ),
                "median_non_recognised_share": float(
                    selected[NON_RECOGNISED_COLUMN].median(),
                ),
                "median_gap_eur": float(selected[GAP_COLUMN].median()),
                "median_market_stress": float(
                    (selected[MARKET_RENT_COLUMN] / selected[CAP_COLUMN]).median(),
                ),
                "median_cap_over_benchmark": float(
                    selected["cap_over_benchmark"].median(),
                ),
                **_coefficient_columns(specifications, group),
                "bg_weighted_proxy_error_eur_h1": _relevance_value(relevance, 1),
                "bg_weighted_proxy_error_eur_h4": _relevance_value(relevance, 4),
            },
        )
    return pd.DataFrame(rows)


def interpretation(
    frame: pd.DataFrame,
    specifications: pd.DataFrame,
    relevance: pd.DataFrame,
    variation: pd.DataFrame,
    coverage: pd.DataFrame,
) -> str:
    """Write the §21 four-part reading of the P1.2 results, with real numbers.

    Args:
        frame: Output of `build_validation_frame`.
        specifications: Output of `specification_table`.
        relevance: Output of `nationally_weighted_relevance`.
        variation: Output of `regressor_variation`.
        coverage: Output of `kreis_coverage`.

    Returns:
        The interpretation as Markdown.

    """
    facts = _interpretation_facts(
        frame,
        specifications,
        relevance,
        variation,
        coverage,
    )
    return _INTERPRETATION_TEMPLATE.format(**facts)


def fit_least_squares(
    design: np.ndarray,
    outcome: np.ndarray,
    clusters: np.ndarray,
    names: tuple[str, ...],
    weights: np.ndarray | None = None,
) -> LeastSquaresFit:
    """Fit weighted least squares with classical and cluster-robust errors.

    The cluster-robust covariance is the usual sandwich with the finite-sample
    correction `G/(G−1) · (n−1)/(n−k)`.

    Args:
        design: `n × k` design matrix, intercept included.
        outcome: `n` outcome values.
        clusters: `n` cluster labels; standard errors cluster on these.
        names: Column names of `design`, in order.
        weights: Optional `n` weights, scaled internally to mean one.

    Returns:
        The fit.

    """
    root = np.sqrt(np.ones(len(outcome)) if weights is None else weights)
    weighted_design = design * root[:, None]
    weighted_outcome = outcome * root
    gram_inverse = np.linalg.pinv(weighted_design.T @ weighted_design)
    estimates = gram_inverse @ (weighted_design.T @ weighted_outcome)
    residuals = outcome - design @ estimates
    rank = int(np.linalg.matrix_rank(weighted_design))
    n_obs = len(outcome)
    degrees_of_freedom = max(n_obs - rank, 1)
    weight_values = root**2
    sigma_squared = float(np.sum(weight_values * residuals**2)) / degrees_of_freedom
    classical = _standard_errors(sigma_squared * gram_inverse)
    scores = weighted_design * (root * residuals)[:, None]
    _, cluster_index = np.unique(clusters, return_inverse=True)
    n_clusters = int(cluster_index.max()) + 1
    meat = np.zeros_like(gram_inverse)
    for index in range(n_clusters):
        cluster_score = scores[cluster_index == index].sum(axis=0)
        meat += np.outer(cluster_score, cluster_score)
    correction = n_clusters / max(n_clusters - 1, 1) * (n_obs - 1) / degrees_of_freedom
    clustered = _standard_errors(correction * gram_inverse @ meat @ gram_inverse)
    total = float(np.sum(weight_values * (outcome - np.mean(outcome)) ** 2))
    explained = float(np.sum(weight_values * residuals**2))
    return LeastSquaresFit(
        names=names,
        estimates=estimates,
        classical_standard_errors=classical,
        cluster_standard_errors=clustered,
        residuals=residuals,
        n_obs=n_obs,
        n_clusters=n_clusters,
        rank=rank,
        r_squared=1.0 - explained / total if total > 0 else np.nan,
    )


def weighted_mean_by(
    frame: pd.DataFrame,
    keys: Sequence[str],
    value_columns: Sequence[str],
    weight_column: str,
) -> pd.DataFrame:
    """Average each value column within `keys`, weighted by `weight_column`.

    A missing value drops its own weight rather than the whole cell, so a
    Gemeinde with no admissible Wohnfläche does not remove its Kreis's cap.

    Args:
        frame: Rows to aggregate.
        keys: Grouping columns.
        value_columns: Columns to average.
        weight_column: Column supplying the weights.

    Returns:
        One row per key combination, with one column per value column.

    """
    keys = list(keys)
    grouping = [frame[key] for key in keys]
    weights = (
        pd.to_numeric(frame[weight_column], errors="coerce").fillna(0.0).clip(lower=0.0)
    )
    result = frame[keys].drop_duplicates().set_index(keys)
    for column in value_columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        usable = weights.where(values.notna(), 0.0)
        numerator = (values.fillna(0.0) * usable).groupby(grouping).sum()
        denominator = usable.groupby(grouping).sum()
        result[column] = (numerator / denominator.where(denominator > 0)).reindex(
            result.index,
        )
    return result.reset_index()


def weighted_quantile(
    values: np.ndarray,
    weights: np.ndarray,
    quantile: float,
) -> float:
    """Return the weighted `quantile` of `values`, or `nan` if no weight is left."""
    usable = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not usable.any():
        return float("nan")
    order = np.argsort(values[usable])
    sorted_values = values[usable][order]
    sorted_weights = weights[usable][order]
    cumulative = np.cumsum(sorted_weights) - 0.5 * sorted_weights
    cumulative /= np.sum(sorted_weights)
    return float(np.interp(quantile, cumulative, sorted_values))


def stamp_regressors(frame: pd.DataFrame) -> pd.DataFrame:
    """Derive `M^market`, `K/W` and the two log regressors of §14.4.

    `M^market` is the Zensus Bestandsmiete per square metre times the locally
    admissible Wohnfläche, so it is a monthly euro figure comparable in level
    with `K`.

    Args:
        frame: Rows carrying `K`, `W`, `max_area_sqm` and the Zensus rent.

    Returns:
        The frame with the derived columns added.

    """
    stamped = frame.copy()
    cap = pd.to_numeric(stamped[CAP_COLUMN], errors="coerce")
    benchmark = pd.to_numeric(stamped[BENCHMARK_COLUMN], errors="coerce")
    area = pd.to_numeric(stamped["max_area_sqm"], errors="coerce")
    rent_per_sqm = pd.to_numeric(stamped["market_rent_eur_per_sqm"], errors="coerce")
    stamped[MARKET_RENT_COLUMN] = rent_per_sqm.where(rent_per_sqm > 0) * area.where(
        area > 0,
    )
    stamped["cap_over_benchmark"] = cap.where(cap > 0) / benchmark.where(benchmark > 0)
    stamped[LOG_CAP_RATIO_COLUMN] = np.log(stamped["cap_over_benchmark"])
    stamped[LOG_MARKET_PRESSURE_COLUMN] = np.log(
        stamped[MARKET_RENT_COLUMN] / cap.where(cap > 0),
    )
    return stamped


def _specification_terms(
    specification: Specification,
) -> tuple[str, tuple[str, ...]]:
    if specification is Specification.CAP_VS_BENCHMARK:
        return NON_RECOGNISED_COLUMN, (LOG_CAP_RATIO_COLUMN,)
    if specification is Specification.MARKET_VS_CAP:
        return NON_RECOGNISED_COLUMN, (LOG_MARKET_PRESSURE_COLUMN,)
    return GAP_COLUMN, (CAP_COLUMN, MARKET_RENT_COLUMN)


def select_linkage_rows(
    frame: pd.DataFrame,
    linkage_group: LinkageGroup,
    validation_sample: ValidationSample = ValidationSample.MAIN,
    household_sizes: Sequence[int] = SPECIFICATION_HOUSEHOLD_SIZES,
) -> pd.DataFrame:
    """Return the rows of one linkage group, §14.3 sample and household range.

    A Jobcenter is one BA reporting unit, so its linkage group is decided for
    the unit as a whole: it counts as WoGG-linked when more than
    `LINKAGE_MAJORITY_SHARE` of its population falls in flagged Gemeinden.

    Args:
        frame: Output of `build_validation_frame`.
        linkage_group: Which group to draw (A12).
        validation_sample: Main or extended §14.3 Jobcenter sample.
        household_sizes: Sizes admitted.

    Returns:
        The selected rows.

    """
    rows = frame.loc[
        (frame["validation_sample"] == validation_sample.value)
        & (frame["household_size"].isin(list(household_sizes)))
    ]
    exact = pd.to_numeric(rows["share_at_exact_ratio"], errors="coerce").fillna(0.0)
    union = pd.to_numeric(rows["share_linked_union"], errors="coerce").fillna(0.0)
    masks = {
        LinkageGroup.ALL: pd.Series(data=True, index=rows.index),
        LinkageGroup.EXCLUDING_EXACT_RATIO: exact <= LINKAGE_MAJORITY_SHARE,
        LinkageGroup.EXACT_RATIO_ONLY: exact > LINKAGE_MAJORITY_SHARE,
        LinkageGroup.EXCLUDING_LINKED_UNION: union <= LINKAGE_MAJORITY_SHARE,
        LinkageGroup.LINKED_UNION_ONLY: union > LINKAGE_MAJORITY_SHARE,
    }
    return rows.loc[masks[linkage_group]]


def _design_matrix(rows: pd.DataFrame, regressors: Sequence[str]) -> pd.DataFrame:
    columns: dict[str, np.ndarray] = {"intercept": np.ones(len(rows))}
    for name in regressors:
        columns[name] = rows[name].to_numpy(dtype=float)
    factors = (
        ("household_size", rows["household_size"].astype(int).astype(str)),
        ("bundesland", rows["state_name"].astype(str)),
    )
    for prefix, series in factors:
        dummies = pd.get_dummies(series, prefix=prefix, drop_first=True)
        for name in dummies.columns:
            columns[str(name)] = dummies[name].to_numpy(dtype=float)
    return pd.DataFrame(columns, index=rows.index)


def _weights(rows: pd.DataFrame, weight_column: str | None) -> np.ndarray | None:
    if weight_column is None:
        return None
    raw = pd.to_numeric(rows[weight_column], errors="coerce").to_numpy(dtype=float)
    usable = np.where(np.isfinite(raw) & (raw > 0), raw, 0.0)
    total = usable.sum()
    if total <= 0:
        return None
    return usable * (len(rows) / total)


def _standard_errors(covariance: np.ndarray) -> np.ndarray:
    return np.sqrt(np.clip(np.diag(covariance), 0.0, None))


def _at_exact_ratio(frame: pd.DataFrame) -> pd.Series:
    cap = pd.to_numeric(frame["kdu_bkc_cap"], errors="coerce")
    benchmark = pd.to_numeric(frame["wogg_base_cap"], errors="coerce")
    ratio = cap / benchmark.where(benchmark > 0)
    return ((ratio - WOGG_SAFETY_MARKUP).abs() <= WOGG_SAFETY_MARKUP_TOLERANCE).fillna(
        value=False,
    )


def _household_size_from_category(category: pd.Series) -> pd.Series:
    digits = category.astype(str).str.extract(r"^(\d+)_person", expand=False)
    return pd.to_numeric(digits, errors="coerce").astype("Int64")


def _population_free_sd(values: pd.Series) -> float:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return float("nan")
    return float(np.std(numeric.to_numpy(dtype=float)))


def _weighted_average(values: pd.Series, weights: pd.Series) -> float:
    numeric = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    weight_values = pd.to_numeric(weights, errors="coerce").to_numpy(dtype=float)
    usable = np.isfinite(numeric) & np.isfinite(weight_values) & (weight_values > 0)
    if not usable.any():
        return float("nan")
    return float(
        np.sum(numeric[usable] * weight_values[usable]) / np.sum(weight_values[usable]),
    )


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0 else float("nan")


def _coefficient_columns(
    specifications: pd.DataFrame,
    group: LinkageGroup,
) -> dict[str, object]:
    selected = specifications.loc[
        (specifications["linkage_group"] == group.value)
        & (specifications["validation_sample"] == ValidationSample.MAIN.value)
        & _is_main_household_grid(specifications)
    ]
    columns: dict[str, object] = {}
    for specification, regressor, label in (
        (Specification.CAP_VS_BENCHMARK, LOG_CAP_RATIO_COLUMN, "beta_log_cap_ratio"),
        (Specification.MARKET_VS_CAP, LOG_MARKET_PRESSURE_COLUMN, "beta_log_market"),
        (Specification.GAP_ON_LEVELS, CAP_COLUMN, "beta_gap_on_cap"),
        (Specification.GAP_ON_LEVELS, MARKET_RENT_COLUMN, "beta_gap_on_market"),
    ):
        row = selected.loc[
            (selected["specification"] == specification.value)
            & (selected["regressor"] == regressor)
        ]
        columns[label] = float(row["estimate"].iloc[0]) if len(row) else np.nan
        columns[f"{label}_cluster_se"] = (
            float(row["cluster_se"].iloc[0]) if len(row) else np.nan
        )
    return columns


def _is_main_household_grid(specifications: pd.DataFrame) -> pd.Series:
    """Select the h = 1…4 rows, so the §18 h = 1…5 robustness never leaks in."""
    if "household_sizes" not in specifications.columns:
        return pd.Series(data=True, index=specifications.index)
    return specifications["household_sizes"].astype(str) == MAIN_HOUSEHOLD_SIZES_LABEL


def _relevance_value(relevance: pd.DataFrame, household_size: int) -> float:
    row = relevance.loc[relevance["household_size"] == household_size]
    return float(row["bg_weighted_mean"].iloc[0]) if len(row) else np.nan


_INTERPRETATION_TEMPLATE = """\
# P1.2 — external validation against the BA Wohnkostendaten (§14)

## 1. What is measured

For every Jobcenter `j` and household size `h` the Statistik der Bundesagentur
für Arbeit publishes the mean **actual** and the mean **recognised**
Bruttokaltmiete of Bedarfsgemeinschaften in Mietunterkünfte, reference month
{reference_month}. §14.2 turns those into three outcomes: the euro difference
`G^BA`, the recognition rate `R^BA`, and the non-recognised cost share
`N^BA = 1 − R^BA`. Against them stand two administrative parameters measured on
the same territory: the local KdU cap `K`, collected from the Richtlinien and
aggregated Gemeinde → Kreis → Jobcenter with population weights, and the
Wohngeld-Höchstbetrag `W` (base only, D6). `M^market` is the Zensus 2022
Bestandsmiete per square metre times the locally admissible Wohnfläche.

The three §14.4 specifications are descriptive, carry household-size and
Bundesland fixed effects, and cluster their standard errors on the Jobcenter.

## 2. The central quantitative finding

Across {n_obs_all:,} Jobcenter-by-household-size observations covering
{n_jobcenter_all} Jobcenter of the §14.3 main sample, the median non-recognised
share of the Bruttokaltmiete is {median_non_recognised:.1f} % and the median
euro gap {median_gap:.2f} € per Bedarfsgemeinschaft per month.

- **Specification 1.** `N^BA = alpha_h + β·log(K/W) + λ_Bundesland + ε` gives
  β = {beta1_all:+.4f} (Jobcenter-clustered SE {beta1_all_se:.4f}, classical
  {beta1_all_classical:.4f}; R² = {r2_1_all:.3f}). A cap 10 % higher relative to
  the Wohngeld benchmark goes together with a non-recognised share lower by
  {beta1_pp_per_ten:.2f} percentage points — against a median of
  {median_non_recognised:.1f} %, a difference of about
  {beta1_relative:.0f} % of the typical shortfall.
- **Specification 2.** `N^BA = alpha_h + β·log(M^market/K) + λ_Bundesland + ε` gives
  β = {beta2_all:+.4f} (clustered SE {beta2_all_se:.4f}; R² = {r2_2_all:.3f}) on
  {n_obs_market:,} observations: where the local Bestandsmiete stands high
  relative to the cap, more of the actual cost goes unrecognised.
- **Specification 3.** `G^BA = alpha_h + β₁·K + β₂·M^market + λ_Bundesland + ε`
  gives β₁ = {beta3_cap:+.4f} €/€ (clustered SE {beta3_cap_se:.4f}) and
  β₂ = {beta3_market:+.4f} €/€ (clustered SE {beta3_market_se:.4f}).

Both linkage groups are reported, and the difference between them is itself the
finding A12 predicts. Excluding the `exact_ratio` group leaves
β = {beta1_excl_exact:+.4f} ({beta1_excl_exact_se:.4f}); excluding the broader
`linked_union` group leaves β = {beta1_excl_union:+.4f}
({beta1_excl_union_se:.4f}). Inside those groups the regressor is degenerate by
construction: the standard deviation of `log(K/W)` is {sd_all:.4f} over all
Jobcenter but only {sd_exact:.4f} in the `exact_ratio` group and
{sd_union:.4f} in the `linked_union` group, so `β` there is estimated at
{beta1_exact_only:+.4f} with a clustered standard error of
{beta1_exact_only_se:.4f} — no identifying variation, and no evidence either
way. This is exactly what D7 says it is: for those Kreise `K/W` is a
definitional identity, not an empirical fact.

**The Bundesland fixed effects do most of the work, and that must be said.**
Without them the gradient nearly vanishes: across deciles of `K/W` the mean
ratio rises from {decile_low_ratio:.3f} to {decile_high_ratio:.3f} — a log
distance of {decile_log_distance:.2f} — while the mean recognition rate rises
only from {decile_low_rate:.2f} % to {decile_high_rate:.2f} %, that is
{decile_rate_gap:.2f} percentage points. The fitted β implies
{implied_rate_gap:.2f} points over the same distance. The difference is what
holding the Bundesland and the household size fixed removes: Kreise with a high
cap are disproportionately Kreise with expensive housing, and the two pull
`N^BA` in opposite directions. Read the raw decile figure and the coefficient
together, never one without the other.

Nationally weighted (§14.5, `D̄^BG_h = Σ_j BG_jh·D_jh / Σ_j BG_jh`, `j` the
Kreis), the mechanical proxy error a model makes by substituting `W` for `K` is
{relevance_h1:.2f} € per month at h = 1 and {relevance_h4:.2f} € at h = 4,
against unweighted Kreis means of {relevance_h1_unweighted:.2f} € and
{relevance_h4_unweighted:.2f} €. The BG-weighted figures reproduce P0.3's
Bedarfsgemeinschaft-weighted proxy error exactly, because both are the same
weighted average written two ways.

Coverage: of the {n_kreise_ba} Kreise the BA reports, {n_kreise_capped} carry a
main-sample cap, {n_kreise_no_cap} are in the KdU table without one under D3's
completeness rule, and {n_kreise_absent} — Hanau, 06415 — is absent from the KdU
table altogether and is reported as such rather than dropped.

## 3. Why this matters for tax-transfer simulation

A microsimulation that substitutes the Wohngeld-Höchstbetrag for the local KdU
cap does not merely pick a different number: the parameter it drops is
associated with an administrative outcome measured in the field. The direction
is consistent across all three specifications and both linkage groups that
carry variation — where the cap stands higher relative to the benchmark and
lower relative to the local Bestandsmiete, a smaller share of actual housing
cost goes unrecognised. The expected core statement of §14 therefore holds in
this data: the local caps are not only a formal legal parameter but show a
systematic **association** with observed differences between actual and
recognised housing costs.

## 4. What may not be concluded

- Not a causal effect. The local cap is endogenous to the local housing market,
  to administrative practice and to how a Kreis draws its Vergleichsräume. A
  high cap may reflect a high-priced market. §14.4 and §20 both say so.
- Not a statement about the level of local social policy. §20 forbids reading
  either parameter as a measure of how much a Kreis grants.
- Not a statement about housing availability. `M^market` is a **Bestandsmiete**
  covering long-standing tenancies, not an Angebotsmiete, and it is a
  Nettokaltmiete set against a Bruttokaltmiete cap, so `M/K` understates market
  pressure by the kalte Betriebskosten. It is a market-stress indicator.
- Not comparable across the two linkage groups as if both carried information.
  Inside the WoGG-linked groups `K/W` is fixed by construction.
- Not applicable inside the Karenzzeit. Under § 22 Abs. 1 S. 2–3 SGB II actual
  Unterkunftskosten are recognised in full for the first 12 months, so the
  proxy error is identically zero there (D11).
- The {n_extended_jobcenter} Jobcenter spanning several Kreise are robustness
  only (§14.3), because their `K` is a population-weighted mean over more than
  one KdU regime.
"""


def _interpretation_facts(
    frame: pd.DataFrame,
    specifications: pd.DataFrame,
    relevance: pd.DataFrame,
    variation: pd.DataFrame,
    coverage: pd.DataFrame,
) -> dict[str, object]:
    def coefficient(
        specification: Specification,
        group: LinkageGroup,
        regressor: str,
        column: str,
    ) -> float:
        row = specifications.loc[
            (specifications["specification"] == specification.value)
            & (specifications["linkage_group"] == group.value)
            & (specifications["validation_sample"] == ValidationSample.MAIN.value)
            & (specifications["regressor"] == regressor)
            & _is_main_household_grid(specifications)
        ]
        return float(row[column].iloc[0]) if len(row) else float("nan")

    def spread(group: LinkageGroup) -> float:
        row = variation.loc[
            (variation["linkage_group"] == group.value)
            & (variation["regressor"] == LOG_CAP_RATIO_COLUMN)
        ]
        return float(row["sd"].iloc[0]) if len(row) else float("nan")

    def relevance_value(household_size: int, column: str) -> float:
        row = relevance.loc[relevance["household_size"] == household_size]
        return float(row[column].iloc[0]) if len(row) else float("nan")

    main = select_linkage_rows(
        frame,
        LinkageGroup.ALL,
        ValidationSample.MAIN,
        SPECIFICATION_HOUSEHOLD_SIZES,
    ).dropna(subset=[NON_RECOGNISED_COLUMN])
    beta1 = coefficient(
        Specification.CAP_VS_BENCHMARK,
        LinkageGroup.ALL,
        LOG_CAP_RATIO_COLUMN,
        "estimate",
    )
    median_non_recognised = float(main[NON_RECOGNISED_COLUMN].median())
    beta1_pp_per_ten = abs(beta1) * np.log(1.10) * 100.0
    deciles = recognition_rate_by_decile(frame, LinkageGroup.ALL)
    decile_low_ratio = float(deciles["cap_over_benchmark"].iloc[0])
    decile_high_ratio = float(deciles["cap_over_benchmark"].iloc[-1])
    decile_low_rate = float(deciles[RECOGNITION_COLUMN].iloc[0]) * 100.0
    decile_high_rate = float(deciles[RECOGNITION_COLUMN].iloc[-1]) * 100.0
    decile_log_distance = float(np.log(decile_high_ratio / decile_low_ratio))
    kreise_by_status = coverage.groupby("status")["ags_kreis"].nunique()

    def kreis_count(status: KreisStatus) -> int:
        return int(kreise_by_status.get(status.value, 0))

    return {
        "reference_month": LEGAL_VINTAGE.ba_reference_month,
        "n_obs_all": len(main),
        "n_jobcenter_all": int(main[CLUSTER_COLUMN].nunique()),
        "median_non_recognised": median_non_recognised * 100.0,
        "median_gap": float(main[GAP_COLUMN].median()),
        "beta1_all": beta1,
        "beta1_all_se": coefficient(
            Specification.CAP_VS_BENCHMARK,
            LinkageGroup.ALL,
            LOG_CAP_RATIO_COLUMN,
            "cluster_se",
        ),
        "beta1_all_classical": coefficient(
            Specification.CAP_VS_BENCHMARK,
            LinkageGroup.ALL,
            LOG_CAP_RATIO_COLUMN,
            "classical_se",
        ),
        "r2_1_all": coefficient(
            Specification.CAP_VS_BENCHMARK,
            LinkageGroup.ALL,
            LOG_CAP_RATIO_COLUMN,
            "r_squared",
        ),
        "beta1_pp_per_ten": beta1_pp_per_ten,
        "decile_low_ratio": decile_low_ratio,
        "decile_high_ratio": decile_high_ratio,
        "decile_low_rate": decile_low_rate,
        "decile_high_rate": decile_high_rate,
        "decile_log_distance": decile_log_distance,
        "decile_rate_gap": decile_high_rate - decile_low_rate,
        "implied_rate_gap": abs(beta1) * decile_log_distance * 100.0,
        "beta1_relative": 100.0 * beta1_pp_per_ten / (median_non_recognised * 100.0),
        "beta2_all": coefficient(
            Specification.MARKET_VS_CAP,
            LinkageGroup.ALL,
            LOG_MARKET_PRESSURE_COLUMN,
            "estimate",
        ),
        "beta2_all_se": coefficient(
            Specification.MARKET_VS_CAP,
            LinkageGroup.ALL,
            LOG_MARKET_PRESSURE_COLUMN,
            "cluster_se",
        ),
        "r2_2_all": coefficient(
            Specification.MARKET_VS_CAP,
            LinkageGroup.ALL,
            LOG_MARKET_PRESSURE_COLUMN,
            "r_squared",
        ),
        "n_obs_market": int(
            coefficient(
                Specification.MARKET_VS_CAP,
                LinkageGroup.ALL,
                LOG_MARKET_PRESSURE_COLUMN,
                "n_obs",
            ),
        ),
        "beta3_cap": coefficient(
            Specification.GAP_ON_LEVELS,
            LinkageGroup.ALL,
            CAP_COLUMN,
            "estimate",
        ),
        "beta3_cap_se": coefficient(
            Specification.GAP_ON_LEVELS,
            LinkageGroup.ALL,
            CAP_COLUMN,
            "cluster_se",
        ),
        "beta3_market": coefficient(
            Specification.GAP_ON_LEVELS,
            LinkageGroup.ALL,
            MARKET_RENT_COLUMN,
            "estimate",
        ),
        "beta3_market_se": coefficient(
            Specification.GAP_ON_LEVELS,
            LinkageGroup.ALL,
            MARKET_RENT_COLUMN,
            "cluster_se",
        ),
        "beta1_excl_exact": coefficient(
            Specification.CAP_VS_BENCHMARK,
            LinkageGroup.EXCLUDING_EXACT_RATIO,
            LOG_CAP_RATIO_COLUMN,
            "estimate",
        ),
        "beta1_excl_exact_se": coefficient(
            Specification.CAP_VS_BENCHMARK,
            LinkageGroup.EXCLUDING_EXACT_RATIO,
            LOG_CAP_RATIO_COLUMN,
            "cluster_se",
        ),
        "beta1_excl_union": coefficient(
            Specification.CAP_VS_BENCHMARK,
            LinkageGroup.EXCLUDING_LINKED_UNION,
            LOG_CAP_RATIO_COLUMN,
            "estimate",
        ),
        "beta1_excl_union_se": coefficient(
            Specification.CAP_VS_BENCHMARK,
            LinkageGroup.EXCLUDING_LINKED_UNION,
            LOG_CAP_RATIO_COLUMN,
            "cluster_se",
        ),
        "beta1_exact_only": coefficient(
            Specification.CAP_VS_BENCHMARK,
            LinkageGroup.EXACT_RATIO_ONLY,
            LOG_CAP_RATIO_COLUMN,
            "estimate",
        ),
        "beta1_exact_only_se": coefficient(
            Specification.CAP_VS_BENCHMARK,
            LinkageGroup.EXACT_RATIO_ONLY,
            LOG_CAP_RATIO_COLUMN,
            "cluster_se",
        ),
        "sd_all": spread(LinkageGroup.ALL),
        "sd_exact": spread(LinkageGroup.EXACT_RATIO_ONLY),
        "sd_union": spread(LinkageGroup.LINKED_UNION_ONLY),
        "relevance_h1": relevance_value(1, "bg_weighted_mean"),
        "relevance_h4": relevance_value(4, "bg_weighted_mean"),
        "relevance_h1_unweighted": relevance_value(1, "unweighted_mean"),
        "relevance_h4_unweighted": relevance_value(4, "unweighted_mean"),
        "n_kreise_ba": int(coverage["ags_kreis"].nunique()),
        "n_kreise_capped": kreis_count(KreisStatus.MAIN_SAMPLE_CAP),
        "n_kreise_no_cap": kreis_count(KreisStatus.NO_MAIN_SAMPLE_CAP),
        "n_kreise_absent": kreis_count(KreisStatus.ABSENT_FROM_KDU_TABLE),
        "n_extended_jobcenter": int(
            frame.loc[
                frame["validation_sample"] == ValidationSample.EXTENDED.value,
                CLUSTER_COLUMN,
            ].nunique(),
        ),
    }
