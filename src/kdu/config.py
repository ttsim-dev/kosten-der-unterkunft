"""Project paths and every legal and temporal parameter of the analysis.

This module is the single place where a year, a Rechtsstand, a statutory
threshold, a model-household assumption, or a grid parameter may appear.
Analysis modules import from here; they never hard-code such a value
(decision log D5, plan §5.3).

The public surface is:

- paths — `SRC`, `ROOT`, `DATA`, `BLD`,
  `FIGURES`, `TABLES`, and `corpus_root`
- vintages — `ANALYSIS_DATE` and `LEGAL_VINTAGE`
- populations of interest — `HOUSEHOLD_SIZES` and
  `MODEL_HOUSEHOLDS`
- analysis parameters — `INCOME_GRID`, `WeightingScheme`,
  `ExclusionReason`, `GEMEINDE_SIZE_CLASS_BREAKS`,
  `SMALL_GEMEINDE_THRESHOLD`
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
# All generated artefacts; gitignored wholesale (D5).
BLD = ROOT / "bld"
# Committed inputs, `.csv` and `.arrow` only (D5).
DATA = ROOT / "data"
# Generated figures.
FIGURES = BLD / "figures"
# Generated tables.
TABLES = BLD / "tables"

# Where the KdU source corpus lives when `KDU_CORPUS` is unset (D4).
DEFAULT_CORPUS_ROOT = Path("/Users/marvin/sciebo/RA-SOPHIA/KdU")
# Environment variable overriding `DEFAULT_CORPUS_ROOT`.
CORPUS_ENV_VAR = "KDU_CORPUS"

# Named members of the corpus, relative to `corpus_root` (D4).
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

# The Analysestichtag: every region contributes the rule in force here (D2).
ANALYSIS_DATE = date(2026, 8, 31)


@dataclass(frozen=True)
class LegalVintage:
    """The Rechtsstand and Gebietsstand every module is pinned to."""

    wogg_rechtsstand: int
    """Year of the WoGG Anlage 1 Höchstbeträge and Mietenstufen in use (D2, D6)."""
    sgb_rechtsstand: int
    """Year of the SGB II / SGB XII parameters the simulation applies (D2)."""
    gebietsstand: date
    """Territorial status of the Gemeinde geometry and population (D8)."""
    ba_reference_month: str
    """BA reporting month actually used, as `YYYY-MM` (D2, A10).

    The BA series runs about four months behind, so 2026-04 is the latest
    published month at or before {data}`ANALYSIS_DATE`.
    """
    wogg_hoechstbetrag_in_force_from: date
    """When the Anlage 1 Höchstbeträge in use took effect (BGBl. 2024 I Nr. 314)."""
    wogg_components_in_force_from: date
    """When § 12 Abs. 6 and 7 WoGG took their current Fassung (BGBl. 2022 I S. 2160)."""


# The one vintage the whole project is computed at. The two WoGG dates differ
# because Anlage 1 was last fortgeschrieben in 2025 while the Klimakomponente
# and the Heizkostenentlastung still carry their Wohngeld-Plus wording of 2023;
# both are the Fassung in force on the Analysestichtag, so the benchmark rests
# on one consistent Rechtsstand.
LEGAL_VINTAGE = LegalVintage(
    wogg_rechtsstand=2026,
    sgb_rechtsstand=2026,
    gebietsstand=date(2023, 12, 31),
    ba_reference_month="2026-04",
    wogg_hoechstbetrag_in_force_from=date(2025, 1, 1),
    wogg_components_in_force_from=date(2023, 1, 1),
)

# Household sizes `h` carried in the long table, keyed `ags` by `household_size`.
HOUSEHOLD_SIZES: tuple[int, ...] = (1, 2, 3, 4, 5)

# Sizes over which `analysis_sample_main` is balanced (D3).
MAIN_SAMPLE_HOUSEHOLD_SIZES: tuple[int, ...] = (1, 2, 3, 4)

# The statutory Mietenstufen I to VII of § 12 WoGG, as integers.
MIETENSTUFEN: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7)


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
    """One person in a Modellhaushalt, with the age the plan fixes."""

    age: int
    """Age in completed years at `ANALYSIS_DATE`."""
    role: MemberRole
    """Benefit-relevant status of this member."""


@dataclass(frozen=True)
class ModelHousehold:
    """A §11.1 Modellhaushalt with every age and assumption made explicit.

    The plan requires all age and household assumptions to be documented, so
    they live here rather than in the simulation modules.
    """

    key: str
    """Stable identifier used as a column value and a filename fragment."""
    label: str
    """Human-readable English label for figures and tables."""
    members: tuple[HouseholdMember, ...]
    """Every member, in the order adults first, then children by age."""
    is_single_parent: bool
    """Whether the Alleinerziehenden-Mehrbedarf applies."""
    karenzzeit_elapsed: bool = True
    """Declared beyond month 12, so the KdU cap is in force (D11)."""
    has_earnings: bool = True
    """Whether the income grid varies Bruttoerwerbseinkommen (§12.4)."""

    @property
    def household_size(self) -> int:
        """The `h` at which this household reads the KdU cap table."""
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


# The four §11.1 Modellhaushalte, keyed by `ModelHousehold.key`.
#
# The adult age of 35 in the single-parent and couple households is not stated
# in §11.1; it is set to 35 to match Modellhaushalt 1, so that differences across
# households come from composition alone.
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
    """The §12.4 gross monthly income grid for the standard-case simulation."""

    start_eur: int = 0
    """First grid point: zero monthly gross income."""
    step_eur: int = 25
    """Grid spacing; §12.4 allows at most 25 €."""
    ceiling_eur: int = 8_000
    """Technical upper bound on monthly gross income."""
    stop_after_consecutive_empty_points: int = 12
    """Stop once both scenarios show no Grundsicherung claim this often in a row."""
    bisection_tolerance_eur: int = 1
    """Exit threshold `y*` is located by bisection to this precision (D10)."""

    def points(self) -> tuple[int, ...]:
        """Return every grid point from `start_eur` to `ceiling_eur`."""
        return tuple(range(self.start_eur, self.ceiling_eur + 1, self.step_eur))


# The one income grid every simulation module uses.
INCOME_GRID = IncomeGrid()


class WeightingScheme(StrEnum):
    """The four §8.2 Berichtsgewichte; every central distribution shows all four."""

    GEMEINDE_UNWEIGHTED = "gemeinde_unweighted"
    """One Gemeinde, one weight: what the administrative landscape looks like."""
    GEMEINDE_POPULATION = "gemeinde_population"
    """Weighted by Gemeinde population: what the population is exposed to."""
    POLICY_REGION_UNWEIGHTED = "policy_region_unweighted"
    """One Kreis, one weight: how independent regulatory regimes differ."""
    BEDARFSGEMEINSCHAFT = "bedarfsgemeinschaft"
    """Weighted by SGB II Bedarfsgemeinschaften; available only after P1."""


class ExclusionReason(StrEnum):
    """Reason codes admitted in `exclusion_log.csv` (D3)."""

    GEMEINDEFREIES_GEBIET = "gemeindefreies_gebiet"
    """Unincorporated area with no Träger and no rule."""
    KEIN_DOKUMENT = "kein_dokument"
    """No KdU Richtlinie could be located for the responsible Kreis."""
    NUR_BRUTTOWARM = "nur_bruttowarm"
    """The document caps Bruttowarmmiete only, so heating cannot be separated."""
    NUR_EUR_PRO_QM_OHNE_FLAECHE = "nur_eur_pro_qm_ohne_flaeche"
    """Only a €/m² figure is published, with no admissible Wohnfläche."""
    ABLEITUNGSVERBOT = "ableitungsverbot"
    """The document forbids deriving a per-household cap from its figures."""
    NICHT_OEFFENTLICH = "nicht_oeffentlich"
    """The rule exists but is not publicly available."""


# Upper-exclusive population breaks defining the Gemeindegrößenklassen (§8.3).
GEMEINDE_SIZE_CLASS_BREAKS: tuple[int, ...] = (2_000, 5_000, 10_000, 20_000, 50_000)

# The §9.1 split: below this many inhabitants a Gemeinde counts as small.
SMALL_GEMEINDE_THRESHOLD = 10_000

# The § 12 WoGG Sicherheitszuschlag a Kreis without a Konzept may apply (D7).
WOGG_SAFETY_MARKUP = 1.10

# Tolerance on `K/W` when detecting WoGG-linked Kreise (D7, A12).
# 5e-4 is the value that isolates the 1,203 Gemeinden sitting exactly at the
# markup at h=1. A looser 0.005 admits a further 18.2 % of rows, which are Kreise that
# happen to land near 1.10 rather than Kreise that adopted the WoGG table.
WOGG_SAFETY_MARKUP_TOLERANCE = 5e-4


def corpus_root() -> Path:
    """Return the KdU source corpus root, or fail with an actionable message.

    Reads the `KDU_CORPUS` environment variable and falls back to
    `DEFAULT_CORPUS_ROOT`. The corpus is never copied into the repository
    (D4), so a missing directory is an installation error the caller must fix
    rather than something to work around.

    Raises:
        FileNotFoundError: If the resolved directory does not exist.

    """
    root = Path(os.environ.get(CORPUS_ENV_VAR, DEFAULT_CORPUS_ROOT))
    if not root.is_dir():
        msg = (
            f"KdU source corpus not found at {root}. The corpus is stored in Sciebo "
            f"and is never committed (decision log D4). Either mount it at that "
            f"path or point the {CORPUS_ENV_VAR} environment variable at your "
            f"local copy, for example: export {CORPUS_ENV_VAR}=/path/to/KdU"
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

DATA_CATALOG.add("gemeinden_geojson", DATA / "gemeinden.geo.json")
DATA_CATALOG.add("gemeinde_lookup", DATA / "gemeinde_lookup.arrow")
DATA_CATALOG.add("gemeinde_population", DATA / "gemeinde_population.arrow")
DATA_CATALOG.add("kdu_gemeinden", DATA / "kdu_gemeinden.csv")
DATA_CATALOG.add("wogg_parameters", DATA / "wogg_parameters.csv")

DATA_CATALOG.add("wogg_benchmark", BLD / "wogg_benchmark.parquet")

DATA_CATALOG.add("municipality_crosswalk", BLD / "municipality_crosswalk.parquet")
DATA_CATALOG.add(
    "kdu_municipality_household",
    BLD / "kdu_municipality_household.parquet",
)
DATA_CATALOG.add(
    "kdu_policy_region_household",
    BLD / "kdu_policy_region_household.parquet",
)
DATA_CATALOG.add("analysis_sample_main", BLD / "analysis_sample_main.parquet")
DATA_CATALOG.add("analysis_sample_extended", BLD / "analysis_sample_extended.parquet")

DATA_CATALOG.add("gemeinden_raw_geojson", BLD / "gemeinden_raw.geojson")
DATA_CATALOG.add("neighbour_pairs", BLD / "neighbour_pairs.parquet")
DATA_CATALOG.add("border_jumps", BLD / "border_jumps.parquet")
DATA_CATALOG.add("neighbour_jump_flags", BLD / "neighbour_jump_flags.parquet")

DATA_CATALOG.add("data_dictionary", BLD / "data_dictionary.csv")
DATA_CATALOG.add("source_register", BLD / "source_register.csv")
DATA_CATALOG.add("exclusion_log", BLD / "exclusion_log.csv")
DATA_CATALOG.add("quality_report", BLD / "quality_report.html")
DATA_CATALOG.add("results_manifest", BLD / "results_manifest.csv")

DATA_CATALOG.add("germany_map", BLD / "germany_map.html")


def catalog_path(name: str) -> Path:
    """Return the filesystem path registered in `DATA_CATALOG` under `name`.

    Task signatures take the catalog entry itself, so that pytask can track the
    dependency. Everything else — tests, scripts, ad-hoc analysis — wants the
    plain path, and this is the typed way to get it.
    """
    return Path(str(cast("PathNode", DATA_CATALOG[name]).path))
