"""Project paths and every legal and temporal parameter of the analysis.

This module is the single place where a year, a Rechtsstand, a statutory
threshold, a model-household assumption, or a grid parameter may appear.
Analysis modules import from here; they never hard-code such a value.

This module exports:

- paths — `SRC`, `ROOT`, `DATA`, `BLD`, the per-package result directories,
  and `corpus_root`
- vintages — `ANALYSIS_DATE` and `LEGAL_VINTAGE`
- the benchmark — `WOHNGELD_FALLBACK_MARKUP`
- populations of interest — `HOUSEHOLD_SIZES` and `MODEL_HOUSEHOLDS`
- analysis parameters — `INCOME_GRID`, `WeightingScheme`
- `DATA_CATALOG` — every committed input and every generated artefact
"""

import os
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import cast

from pytask import DataCatalog, PathNode

# The importable package root, `src/kdu`.
SRC = Path(__file__).parent.resolve()
# The repository root.
ROOT = SRC.parent.parent
# All generated artefacts; gitignored wholesale and safe to delete entirely.
BLD = ROOT / "bld"
# Committed inputs in open text or columnar formats. The pytask graph reads
# only from here, never from the network; `scripts/fetch_*.py` refresh these
# outside the graph and their output is committed.
DATA = ROOT / "data"

# The cleaned tables every analysis package reads.
CLEAN_DATA = BLD / "data"
# Results, one directory per analysis package.
KDU_VS_WOHNGELD = BLD / "kdu_vs_wohngeld"
MARKET_RENT_COMPARISON = BLD / "market_rent_comparison"
ELIGIBILITY = BLD / "eligibility"
VALIDATION = BLD / "validation"
MAP = BLD / "map"

# Where the KdU source corpus lives when `KDU_CORPUS` is unset. The corpus of
# scanned Richtlinien is stored in Sciebo and is never committed; no task in
# the pytask graph reads it.
DEFAULT_CORPUS_ROOT = Path("/Users/marvin/sciebo/RA-SOPHIA/KdU")
# Environment variable overriding `DEFAULT_CORPUS_ROOT`.
CORPUS_ENV_VAR = "KDU_CORPUS"

# Named members of the corpus, relative to `corpus_root`.
CORPUS_PATHS: MappingProxyType[str, str] = MappingProxyType(
    {
        "pdfs_thome": "kdu_pdfs/thome",
        "pdfs_own_research": "kdu_pdfs/own_research",
        "converted_text": "kdu_pdfs/converted_text",
        "ocr_searchable": "kdu_pdfs/ocr_searchable",
        "manifest": "kdu_manifest.csv",
        "validity_index": "kdu_validity_index.md",
        "region_to_kreis": "kdu_region_to_kreis.csv",
        "extract_per_kreis": "kdu_extract_per_kreis",
    },
)

# The Analysestichtag: every region contributes the rule in force here.
ANALYSIS_DATE = date(2026, 8, 31)


@dataclass(frozen=True)
class LegalVintage:
    """The Rechtsstand and Gebietsstand every module is pinned to."""

    wohngeld_rechtsstand: int
    """Year of the WoGG Anlage 1 Höchstbeträge and Mietenstufen in use."""
    sgb_rechtsstand: int
    """Year of the SGB II / SGB XII parameters the simulation applies."""
    gebietsstand: date
    """Territorial status of the Gemeinde geometry and population."""
    wohnkostenstatistik_reference_month: str
    """Reporting month of the Bundesagentur statistic used, as `YYYY-MM`.

    The series runs about four months behind, so 2026-04 is the latest
    published month at or before {data}`ANALYSIS_DATE`.
    """
    wohngeld_hoechstbetrag_in_force_from: date
    """When the Anlage 1 Höchstbeträge in use took effect (BGBl. 2024 I Nr. 314)."""
    wohngeld_components_in_force_from: date
    """When § 12 Abs. 6 and 7 WoGG took their current Fassung (BGBl. 2022 I S. 2160)."""


# The one vintage the whole project is computed at. The two WoGG dates differ
# because Anlage 1 was last fortgeschrieben in 2025 while the Klimakomponente
# and the Heizkostenentlastung still carry their Wohngeld-Plus wording of 2023;
# both are the Fassung in force on the Analysestichtag, so the benchmark rests
# on one consistent Rechtsstand.
LEGAL_VINTAGE = LegalVintage(
    wohngeld_rechtsstand=2026,
    sgb_rechtsstand=2026,
    gebietsstand=date(2023, 12, 31),
    wohnkostenstatistik_reference_month="2026-04",
    wohngeld_hoechstbetrag_in_force_from=date(2025, 1, 1),
    wohngeld_components_in_force_from=date(2023, 1, 1),
)

# Household sizes carried in every long table, keyed `ags` by `household_size`.
HOUSEHOLD_SIZES: tuple[int, ...] = (1, 2, 3, 4, 5)

# The statutory Mietenstufen I to VII of § 12 WoGG, as integers.
MIETENSTUFEN: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7)

# The markup on the Anlage 1 Höchstbetrag that defines the project's benchmark.
#
# Where a Kreis publishes no schlüssiges Konzept, BSG case law fixes the
# Angemessenheitsgrenze at the Wohngeld table plus a Sicherheitszuschlag of
# 10 %. That fallback, not the bare Höchstbetrag, is the single benchmark every
# result is measured against: it is the figure a Träger is legally required to
# apply when it has nothing of its own, so it is the standard a local rule
# departs from.
WOHNGELD_FALLBACK_MARKUP = 1.10


class MemberRole(StrEnum):
    """What a model-household member is, for benefit purposes."""

    ADULT_EMPLOYABLE = "adult_employable"
    """Erwerbsfähige leistungsberechtigte Person under SGB II."""
    ADULT_PENSIONER = "adult_pensioner"
    """Person at Regelaltersgrenze, so SGB XII rather than SGB II."""
    CHILD = "child"
    """Minor in the Bedarfsgemeinschaft, drawing Kindergeld."""


@dataclass(frozen=True)
class HouseholdMember:
    """One person in a Modellhaushalt, with an explicit age."""

    age: int
    """Age in completed years at `ANALYSIS_DATE`."""
    role: MemberRole
    """Benefit-relevant status of this member."""


@dataclass(frozen=True)
class ModelHousehold:
    """A Modellhaushalt with every age and assumption made explicit."""

    key: str
    """Stable identifier used as a column value and a filename fragment."""
    label: str
    """Human-readable English label for figures and tables."""
    members: tuple[HouseholdMember, ...]
    """Every member, in the order adults first, then children by age."""
    is_single_parent: bool
    """Whether the Alleinerziehenden-Mehrbedarf applies."""
    karenzzeit_elapsed: bool = True
    """Declared beyond month 12, so the KdU cap is in force."""
    has_earnings: bool = True
    """Whether the income grid varies Bruttoerwerbseinkommen."""

    @property
    def household_size(self) -> int:
        """The household size at which this household reads the KdU cap table."""
        return len(self.members)

    @property
    def n_adults(self) -> int:
        """Number of adult members."""
        return sum(member.role is not MemberRole.CHILD for member in self.members)

    @property
    def n_children(self) -> int:
        """Number of child members."""
        return sum(member.role is MemberRole.CHILD for member in self.members)

    @property
    def child_ages(self) -> tuple[int, ...]:
        """Ages of the child members, ascending."""
        return tuple(
            sorted(m.age for m in self.members if m.role is MemberRole.CHILD),
        )


# The four Modellhaushalte, keyed by `ModelHousehold.key`.
#
# The adult age of 35 in the single-parent and couple households matches
# Modellhaushalt 1, so that differences across households come from composition
# alone.
MODEL_HOUSEHOLDS: MappingProxyType[str, ModelHousehold] = MappingProxyType(
    {
        household.key: household
        for household in (
            ModelHousehold(
                key="single_35",
                label="Single adult, age 35",
                members=(HouseholdMember(35, MemberRole.ADULT_EMPLOYABLE),),
                is_single_parent=False,
            ),
            ModelHousehold(
                key="single_parent_child_8",
                label="Single parent (35) with one child, age 8",
                members=(
                    HouseholdMember(35, MemberRole.ADULT_EMPLOYABLE),
                    HouseholdMember(8, MemberRole.CHILD),
                ),
                is_single_parent=True,
            ),
            ModelHousehold(
                key="couple_children_8_14",
                label="Couple (35, 35) with children aged 8 and 14",
                members=(
                    HouseholdMember(35, MemberRole.ADULT_EMPLOYABLE),
                    HouseholdMember(35, MemberRole.ADULT_EMPLOYABLE),
                    HouseholdMember(8, MemberRole.CHILD),
                    HouseholdMember(14, MemberRole.CHILD),
                ),
                is_single_parent=False,
            ),
            ModelHousehold(
                key="pensioner_70",
                label="Single pensioner, age 70",
                members=(HouseholdMember(70, MemberRole.ADULT_PENSIONER),),
                is_single_parent=False,
                has_earnings=False,
            ),
        )
    },
)


@dataclass(frozen=True)
class IncomeGrid:
    """The gross monthly income grid for the standard-case simulation."""

    start_eur: int = 0
    """First grid point: zero monthly gross income."""
    step_eur: int = 25
    """Grid spacing, in euro per month."""
    ceiling_eur: int = 8_000
    """Technical upper bound on monthly gross income."""
    stop_after_consecutive_empty_points: int = 12
    """Stop once both scenarios show no Grundsicherung claim this often in a row."""
    bisection_tolerance_eur: int = 1
    """The income at transfer exit is located by bisection to this precision."""

    def points(self) -> tuple[int, ...]:
        """Return every grid point from `start_eur` to `ceiling_eur`."""
        return tuple(range(self.start_eur, self.ceiling_eur + 1, self.step_eur))


# The one income grid every simulation module uses.
INCOME_GRID = IncomeGrid()


class WeightingScheme(StrEnum):
    """The two weights a distribution is reported under.

    Which one applies is decided per result rather than by a standing rule:
    a claim about how administrative rules differ takes the Gemeinde weight, a
    claim about what claimants face takes the Bedarfsgemeinschaft weight.
    """

    GEMEINDE_UNWEIGHTED = "gemeinde_unweighted"
    """One Gemeinde, one weight: what the administrative landscape looks like."""
    BEDARFSGEMEINSCHAFT = "bedarfsgemeinschaft"
    """Weighted by SGB II Bedarfsgemeinschaften at the household size in question."""


def corpus_root() -> Path:
    """Return the KdU source corpus root, or fail with an actionable message.

    Reads the `KDU_CORPUS` environment variable and falls back to
    `DEFAULT_CORPUS_ROOT`. The corpus is never copied into the repository, so a
    missing directory is an installation error the caller must fix rather than
    something to work around.

    Raises:
        FileNotFoundError: If the resolved directory does not exist.

    """
    root = Path(os.environ.get(CORPUS_ENV_VAR, DEFAULT_CORPUS_ROOT))
    if not root.is_dir():
        msg = (
            f"KdU source corpus not found at {root}. The corpus is stored in Sciebo "
            f"and is never committed. Either mount it at that path or point the "
            f"{CORPUS_ENV_VAR} environment variable at your local copy, for "
            f"example: export {CORPUS_ENV_VAR}=/path/to/KdU"
        )
        raise FileNotFoundError(msg)
    return root


def corpus_path(name: str) -> Path:
    """Return the corpus member registered under `name` in `CORPUS_PATHS`.

    Args:
        name: A key of `CORPUS_PATHS`, for example `"converted_text"`.

    Raises:
        KeyError: If `name` is not a registered corpus member.
        FileNotFoundError: If the corpus root does not exist.

    """
    if name not in CORPUS_PATHS:
        msg = (
            f"Unknown corpus member {name!r}; "
            f"registered members are {sorted(CORPUS_PATHS)}"
        )
        raise KeyError(msg)
    return corpus_root() / CORPUS_PATHS[name]


DATA_CATALOG = DataCatalog(name="kdu")

# Committed inputs.
DATA_CATALOG.add("gemeinden_geojson", DATA / "gemeinden.geo.json")
DATA_CATALOG.add("gemeinde_lookup", DATA / "gemeinde_lookup.arrow")
DATA_CATALOG.add("gemeinde_population", DATA / "gemeinde_population.arrow")
DATA_CATALOG.add("kdu_gemeinden", DATA / "kdu_gemeinden.csv")
DATA_CATALOG.add("wohngeld_parameters", DATA / "wogg_parameters.csv")

# The cleaned tables every analysis package reads.
DATA_CATALOG.add("kdu_caps", CLEAN_DATA / "kdu_caps.parquet")
DATA_CATALOG.add("kdu_sources", CLEAN_DATA / "kdu_sources.parquet")
DATA_CATALOG.add("wohngeld_fallback", CLEAN_DATA / "wohngeld_fallback.parquet")
DATA_CATALOG.add("gemeinden", CLEAN_DATA / "gemeinden.parquet")
DATA_CATALOG.add("wohnkostenstatistik", CLEAN_DATA / "wohnkostenstatistik.parquet")
DATA_CATALOG.add("zensus_rents", CLEAN_DATA / "zensus_rents.parquet")

# The seven measures the map offers, each also exported as its own file.
MAP_MEASURES: tuple[str, ...] = (
    "mietenstufe",
    "kdu_cap",
    "kdu_cap_per_sqm",
    "wohngeld_fallback_cap",
    "cap_ratio",
    "max_wohnflaeche",
    "share_of_stock_above_cap",
)

# How far a local cap departs from the statutory fallback, and how much
# variation the Mietenstufe leaves unaccounted for.
DATA_CATALOG.add(
    "cap_comparison_distribution",
    KDU_VS_WOHNGELD / "cap_comparison_distribution.html",
)
DATA_CATALOG.add(
    "cap_ratio_spread_distribution",
    KDU_VS_WOHNGELD / "cap_ratio_spread_distribution.html",
)
DATA_CATALOG.add(
    "mietenstufe_dispersion_figure",
    KDU_VS_WOHNGELD / "mietenstufe_dispersion.html",
)
DATA_CATALOG.add("cap_comparison_table", KDU_VS_WOHNGELD / "cap_comparison.csv")
DATA_CATALOG.add(
    "mietenstufe_variance_shares",
    KDU_VS_WOHNGELD / "mietenstufe_variance_shares.csv",
)

# Whether local caps track local market rents, and how much of the local
# rented stock each cap prices above itself.
DATA_CATALOG.add(
    "market_rent_correlation_figure",
    MARKET_RENT_COMPARISON / "market_rent_correlation.html",
)
DATA_CATALOG.add(
    "market_rent_correlation_table",
    MARKET_RENT_COMPARISON / "market_rent_correlation.csv",
)
DATA_CATALOG.add(
    "share_of_stock_above_cap_figure",
    MARKET_RENT_COMPARISON / "share_of_stock_above_cap.html",
)
DATA_CATALOG.add(
    "share_of_stock_above_cap_table",
    MARKET_RENT_COMPARISON / "share_of_stock_above_cap.csv",
)
DATA_CATALOG.add(
    "share_of_stock_above_cap_gemeinde",
    MARKET_RENT_COMPARISON / "share_of_stock_above_cap_gemeinde.parquet",
)

# How far the choice of cap moves the gross income at which a household
# leaves the transfer system.
DATA_CATALOG.add(
    "exit_threshold_distribution",
    ELIGIBILITY / "exit_threshold_distribution.html",
)
DATA_CATALOG.add("exit_threshold_table", ELIGIBILITY / "exit_threshold.csv")
DATA_CATALOG.add(
    "exit_threshold_gemeinde",
    ELIGIBILITY / "exit_threshold_gemeinde.parquet",
)

# Whether the collected caps agree with what Jobcenter actually recognise.
DATA_CATALOG.add(
    "wohnkostenstatistik_validation",
    VALIDATION / "wohnkostenstatistik_validation.csv",
)

# The map, once with every measure in one dropdown and once per measure.
DATA_CATALOG.add("germany_map", MAP / "germany_map.html")
for _measure in MAP_MEASURES:
    DATA_CATALOG.add(
        f"germany_map_{_measure}",
        MAP / f"germany_map_{_measure}.html",
    )


def catalog_path(name: str) -> Path:
    """Return the filesystem path registered in `DATA_CATALOG` under `name`.

    Task signatures take the catalog entry itself, so that pytask can track the
    dependency. Everything else — tests, scripts, ad-hoc analysis — wants the
    plain path, and this is the typed way to get it.
    """
    return Path(str(cast("PathNode", DATA_CATALOG[name]).path))
