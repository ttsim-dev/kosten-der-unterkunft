"""The §12 Standardfall microsimulation: two scenarios, one cap apart.

Scenario K recognises `min(m, K)` as the Bruttokaltmiete, scenario W recognises
`min(m, W)`. Every other legal and economic parameter is identical, so the whole
difference in every simulated Anspruch, exit threshold and budget curve comes from
the choice of regional housing-cost parameter.

GETTSIM is GETTSIM 1.3 (D9). Its own national Angemessenheitsgrenze is replaced
rather than reconfigured: `kdu_cap.unterkunftskosten_m` computes the recognised
amount here, `kdu_cap.kopfteil_m` splits it per person, and it reaches GETTSIM
through `kdu_cap.GETTSIM_UNTERKUNFTSKOSTEN_COLUMN`, which prunes GETTSIM's
housing rule out of the DAG. `docs/gettsim_audit.md` records why that matters:
left in place GETTSIM's 10 €/m² warm cap binds at 450 € for a single person and
would have measured ΔT as zero across most of the sample.

The public surface is:

- `simulation_cells` and `assign_cells` — D10's cell design, so GETTSIM sees
  ~800 distinct cap pairs rather than 9,442 Gemeinden
- `build_cases` — turn cells into the two-scenario case frame
- `evaluate` — run GETTSIM on a case frame and return household-level outcomes
- `exit_threshold_m` — locate `y*` by bisection to one euro, monotonicity asserted
- `budget_curve` — the ≤25 € income grid of §12.4
- `national_heating_costs_m` — the §12.3 heating assumption from the BA data
- `rent_grid_factors` — §12.2 Variante 2

All amounts are euro per month.
"""

from dataclasses import dataclass
from functools import cache
from types import MappingProxyType
from typing import Any, cast

import dags.tree as dt
import numpy as np
import pandas as pd
from gettsim import InputData, MainTarget, TTTargets, main
from numpy.typing import NDArray

from kdu.config import (
    ANALYSIS_DATE,
    INCOME_GRID,
    MODEL_HOUSEHOLDS,
    WOHNGELD_FALLBACK_MARKUP,
    MemberRole,
)
from kdu.simulation.kdu_cap import (
    GETTSIM_UNTERKUNFTSKOSTEN_COLUMN,
    fail_if_not_weakly_decreasing,
    kopfteil_m,
    recognised_bruttokaltmiete_m,
    round_currency_m,
    unterkunftskosten_m,
)

# Number of adults in a couple household.
N_ADULTS_IN_COUPLE = 2

# Column count of the cell frame once the Klimakomponente is present.
N_CELL_COLUMNS_WITH_CLIMATE_COMPONENT = 4


# The Rechtsstand every GETTSIM call is evaluated at (D2).
POLICY_DATE = ANALYSIS_DATE.isoformat()

# Scenario labels. `SCENARIO_KDU` recognises the local KdU-Obergrenze,
# `SCENARIO_WOGG` the Wohngeld-Höchstbetrag used as its proxy (§12.1).
SCENARIO_KDU = "K"
SCENARIO_WOGG = "W"
SCENARIOS: tuple[str, str] = (SCENARIO_KDU, SCENARIO_WOGG)

# §12.3's heating sensitivity: the BA mean and its 75 % and 125 % variants.
HEIZKOSTEN_SENSITIVITY_FACTORS: tuple[float, float, float] = (0.75, 1.0, 1.25)

# The BA measure §12.3 asks for, and the stock it is weighted by.
BA_HEIZKOSTEN_MEASURE = "recognised_heizkosten_eur_per_bg"
BA_STOCK_MEASURE = "bg_stock_with_recognised_kdu"

# Statutory Mindestlohn on the Analysestichtag, euro per hour (A7).
MINDESTLOHN_EUR_PER_HOUR = 13.90

# Weeks per month used to convert a monthly income into weekly hours (§12.6).
WEEKS_PER_MONTH = 4.33

# Monthly earnings equivalent to one hour of Mindestlohn work per week (§12.6),
# so `ΔH = Δy* / MINDESTLOHN_EUR_PER_WEEKLY_HOUR_M`.
MINDESTLOHN_EUR_PER_WEEKLY_HOUR_M = WEEKS_PER_MONTH * MINDESTLOHN_EUR_PER_HOUR

# Number of rungs on the ladder that brackets `y*` and carries D10's mandatory
# monotonicity assertion before bisection starts.
MONOTONICITY_LADDER_POINTS = 65

# Admissible Wohnfläche assumed for a household of `n` persons: 45 m² for the
# first person and 15 m² for each further one. It only reaches GETTSIM's own
# housing rule, which the override prunes away, but Wohngeld and GETTSIM's
# input validation still want a plausible value.
WOHNFLAECHE_BASE_SQM = 45.0
WOHNFLAECHE_PER_FURTHER_PERSON_SQM = 15.0

# Contribution months credited to the pensioner household. 45 years of
# Pflichtbeiträge put the Zugangsfaktor at exactly 1.0 for retirement at the
# Regelaltersgrenze, so the pension is Entgeltpunkte times Rentenwert with no
# Abschlag and no Zuschlag to explain away.
PENSIONER_PFLICHTBEITRAGSMONATE = 540.0

# Age at which the pensioner household is assumed to have retired, in whole years
# and months. It is the Regelaltersgrenze of the 1956 birth cohort.
PENSIONER_RETIREMENT_AGE_YEARS = 65
PENSIONER_RETIREMENT_MONTH = 11

# Every column `evaluate` expects on a case frame.
CASE_COLUMNS: tuple[str, ...] = (
    "case_id",
    "cell_id",
    "scenario",
    "household_key",
    "mietenstufe",
    "kdu_cap_m",
    "wogg_cap_m",
    "actual_bruttokaltmiete_m",
    "heizkosten_m",
    "gross_income_m",
    "recognised_bruttokaltmiete_m",
    "unterkunftskosten_m",
)

_TT_TARGETS: dict[str, Any] = {
    "bürgergeld": {
        "anspruchshöhe_m": "buergergeld_anspruch_m",
        "betrag_m": "buergergeld_betrag_m",
        "regelsatz_m": "regelsatz_m",
        "kosten_der_unterkunft_m": "anerkannte_kdu_m",
        "mehrbedarfsanteil_alleinerziehend": "mehrbedarfsanteil",
    },
    "grundsicherung": {
        "im_alter": {
            "anspruchshöhe_m": "grundsicherung_anspruch_m",
            "betrag_m": "grundsicherung_betrag_m",
        },
    },
    "wohngeld": {"betrag_m_wthh": "wohngeld_m"},
    "kinderzuschlag": {"betrag_m_bg": "kinderzuschlag_m"},
    "kindergeld": {"betrag_m": "kindergeld_m"},
    "unterhaltsvorschuss": {"betrag_m": "unterhaltsvorschuss_m"},
    "einkommensteuer": {"betrag_y_sn": "einkommensteuer_y_sn"},
    "solidaritätszuschlag": {"betrag_y_sn": "solidaritaetszuschlag_y_sn"},
    "sozialversicherung": {
        "beiträge_versicherter_m": "sozialbeitraege_m",
        "rente": {"altersrente": {"betrag_m": "rente_m"}},
    },
    "sn_id": "sn_id",
}

# GETTSIM outputs that are person-level and therefore summed over the household.
_PERSON_LEVEL_OUTPUTS: tuple[str, ...] = (
    "buergergeld_anspruch_m",
    "buergergeld_betrag_m",
    "grundsicherung_anspruch_m",
    "grundsicherung_betrag_m",
    "regelsatz_m",
    "anerkannte_kdu_m",
    "kindergeld_m",
    "unterhaltsvorschuss_m",
    "sozialbeitraege_m",
    "rente_m",
)

# GETTSIM outputs that already hold a group total and are repeated on every person
# of the group, so they are taken once rather than summed.
_GROUP_LEVEL_OUTPUTS: tuple[str, ...] = ("wohngeld_m", "kinderzuschlag_m")

# GETTSIM outputs that are a per-person rate rather than an amount, so the
# household figure is the largest rate any member carries.
_RATE_LEVEL_OUTPUTS: tuple[str, ...] = ("mehrbedarfsanteil",)

# GETTSIM outputs that are annual and defined per Steuernummer.
_STEUERNUMMER_LEVEL_OUTPUTS: tuple[str, ...] = (
    "einkommensteuer_y_sn",
    "solidaritaetszuschlag_y_sn",
)

_DTYPE_DEFAULTS: MappingProxyType[str, Any] = MappingProxyType(
    {"BoolColumn": False, "IntColumn": 0, "FloatColumn": 0.0},
)


@dataclass(frozen=True)
class HeatingAssumption:
    """The §12.3 heating figure, held constant across the two scenarios."""

    per_household_size: MappingProxyType[int, float]
    """Recognised Heizkosten in euro per month, by household size."""
    reference_month: str
    """BA reporting month the figure was taken from, as `YYYY-MM`."""
    n_regions: int
    """Number of Kreise the stock-weighted mean was taken over."""

    def for_household(self, household_key: str) -> float:
        """Return the heating assumption for a §11.1 Modellhaushalt."""
        size = MODEL_HOUSEHOLDS[household_key].household_size
        return self.per_household_size[size]


def simulation_cells(sample: pd.DataFrame, household_size: int) -> pd.DataFrame:
    """Collapse the Gemeinde sample to D10's distinct cap cells.

    GETTSIM never sees a Gemeinde. It sees the distinct combinations of local
    KdU-Obergrenze and statutory Mietenstufe, because those two are the only
    attributes a Gemeinde contributes to the simulation: the Mietenstufe fixes the
    Wohngeld benchmark and the Wohngeld branch of §12.7, the cap fixes the
    recognised Bruttokaltmiete. `assign_cells` joins the results back.

    Gemeinden without a statutory Mietenstufe carry no Wohngeld benchmark at all
    (A2), so no K−W contrast is defined for them and they are dropped here rather
    than imputed.

    Args:
        sample: The long analysis sample, keyed `ags` by `household_size`.
        household_size: The `h` at which the caps are read.

    Returns:
        One row per distinct cell, with `cell_id`, `kdu_cap_m`, `wogg_cap_m`,
        `wogg_klima_cap_m`, `mietenstufe` and the number of Gemeinden it covers.

    """
    columns = ["kdu_bkc_cap", "wogg_base_cap", "wogg_rent_level"]
    if "wogg_climate_component" in sample.columns:
        columns.append("wogg_climate_component")
    contrasted = (
        sample.query("household_size == @household_size")
        .loc[~sample["wogg_rent_level_missing"].fillna(value=True), columns]
        .dropna(subset=["kdu_bkc_cap", "wogg_base_cap", "wogg_rent_level"])
    )
    grouped = (
        contrasted.astype({"wogg_rent_level": "int64"})
        .groupby(["kdu_bkc_cap", "wogg_rent_level"], as_index=False)
        .agg(
            wogg_base_cap_m=("wogg_base_cap", "first"),
            wogg_klima_cap_m=(
                "wogg_climate_component"
                if len(columns) == N_CELL_COLUMNS_WITH_CLIMATE_COMPONENT
                else "wogg_base_cap",
                "first",
            ),
            n_gemeinden=("wogg_base_cap", "size"),
        )
        .rename(columns={"kdu_bkc_cap": "kdu_cap_m", "wogg_rent_level": "mietenstufe"})
    )
    # The counterfactual is the fallback the BSG prescribes where no schlüssiges
    # Konzept exists — the § 12 WoGG table plus the Sicherheitszuschlag (D15).
    grouped["wogg_cap_m"] = grouped["wogg_base_cap_m"] * WOHNGELD_FALLBACK_MARKUP
    if len(columns) == N_CELL_COLUMNS_WITH_CLIMATE_COMPONENT:
        grouped["wogg_klima_cap_m"] = (
            grouped["wogg_base_cap_m"] + grouped["wogg_klima_cap_m"]
        )
    return grouped.assign(
        cell_id=np.arange(len(grouped)),
        kdu_cap_m=lambda frame: frame["kdu_cap_m"].astype(float),
        wogg_cap_m=lambda frame: frame["wogg_cap_m"].astype(float),
        wogg_klima_cap_m=lambda frame: frame["wogg_klima_cap_m"].astype(float),
        household_size=household_size,
    ).loc[
        :,
        [
            "cell_id",
            "kdu_cap_m",
            "wogg_cap_m",
            "wogg_klima_cap_m",
            "mietenstufe",
            "household_size",
            "n_gemeinden",
        ],
    ]


def assign_cells(
    sample: pd.DataFrame,
    cells: pd.DataFrame,
) -> pd.DataFrame:
    """Left-join every Gemeinde of the sample onto its simulation cell (D10).

    Gemeinden without a Mietenstufe stay in the frame with a null `cell_id`, so
    the coverage gap A2 records is visible rather than silently dropped.
    """
    keys = sample.query("household_size == @household_size").loc[
        :,
        ["ags", "kdu_bkc_cap", "wogg_rent_level"],
    ]
    lookup = cells.loc[:, ["cell_id", "kdu_cap_m", "mietenstufe"]].rename(
        columns={"kdu_cap_m": "kdu_bkc_cap", "mietenstufe": "wogg_rent_level"},
    )
    return keys.astype({"wogg_rent_level": "Int64"}).merge(
        lookup.astype({"wogg_rent_level": "Int64"}),
        on=["kdu_bkc_cap", "wogg_rent_level"],
        how="left",
    )


def build_cases(
    cells: pd.DataFrame,
    household_key: str,
    actual_bruttokaltmiete_m: NDArray[np.float64],
    heizkosten_m: float,
    gross_income_m: NDArray[np.float64],
    wogg_cap_column: str = "wogg_cap_m",
) -> pd.DataFrame:
    """Turn cells into the two-scenario case frame of §12.1.

    Each cell yields exactly two cases that differ in one number only: the cap
    that enters `min(m, cap)`. Heating is added to both identically (§12.3), so
    it cancels from every K−W difference.

    Args:
        cells: Cells from `simulation_cells`, or any frame with `cell_id`,
            `kdu_cap_m`, the chosen Wohngeld cap column and `mietenstufe`.
        household_key: Key of the §11.1 Modellhaushalt.
        actual_bruttokaltmiete_m: Assumed actual rent `m`, one per cell (§12.2).
        heizkosten_m: Heating cost held constant across scenarios (§12.3).
        gross_income_m: Gross monthly income, one per cell (§12.4).
        wogg_cap_column: Which Wohngeld benchmark to use; the D6 base cap by
            default, `"wogg_klima_cap_m"` for the mandatory robustness row.

    Returns:
        A frame with `CASE_COLUMNS`, two rows per cell.

    """
    caps = {
        SCENARIO_KDU: cells["kdu_cap_m"].to_numpy(dtype=float),
        SCENARIO_WOGG: cells[wogg_cap_column].to_numpy(dtype=float),
    }
    rent = np.asarray(actual_bruttokaltmiete_m, dtype=float)
    income = np.asarray(gross_income_m, dtype=float)
    heizkosten = np.full(len(cells), float(heizkosten_m))
    frames = []
    for scenario, cap in caps.items():
        frames.append(
            pd.DataFrame(
                {
                    "cell_id": cells["cell_id"].to_numpy(),
                    "scenario": scenario,
                    "household_key": household_key,
                    "mietenstufe": cells["mietenstufe"].to_numpy(dtype=int),
                    "kdu_cap_m": caps[SCENARIO_KDU],
                    "wogg_cap_m": caps[SCENARIO_WOGG],
                    "actual_bruttokaltmiete_m": rent,
                    "heizkosten_m": heizkosten,
                    "gross_income_m": income,
                    "recognised_bruttokaltmiete_m": recognised_bruttokaltmiete_m(
                        rent,
                        cap,
                    ),
                    "unterkunftskosten_m": unterkunftskosten_m(rent, cap, heizkosten),
                },
            ),
        )
    cases = pd.concat(frames, ignore_index=True)
    return cases.assign(case_id=np.arange(len(cases))).loc[:, list(CASE_COLUMNS)]


def expand_over_income(
    cells: pd.DataFrame,
    incomes_m: NDArray[np.float64],
    actual_bruttokaltmiete_m: NDArray[np.float64],
) -> tuple[pd.DataFrame, NDArray[np.float64], NDArray[np.float64]]:
    """Cross every cell with every income point of a grid.

    Returns the repeated cell frame together with the matching rent and income
    vectors, so the result can be handed straight to `build_cases`.
    """
    n_incomes = len(incomes_m)
    repeated = cells.loc[cells.index.repeat(n_incomes)].reset_index(drop=True)
    rent = np.repeat(np.asarray(actual_bruttokaltmiete_m, dtype=float), n_incomes)
    income = np.tile(np.asarray(incomes_m, dtype=float), len(cells))
    return repeated, rent, income


def evaluate(cases: pd.DataFrame) -> pd.DataFrame:
    """Run GETTSIM on a case frame and return household-level outcomes.

    One GETTSIM call covers every case in the frame, whatever the model household:
    GETTSIM is fully vectorised over one row per person and its cost is a flat
    ~2 s up to several hundred thousand rows.

    Args:
        cases: A frame with `CASE_COLUMNS`, as `build_cases` produces.

    Returns:
        `cases` with one row per case and the simulated outcomes joined on:
        `anspruch_m` (the SGB claim before the Vorrangprüfung), `sgb_betrag_m`,
        `wohngeld_m`, `kinderzuschlag_m`, `kindergeld_m`, `anerkannte_kdu_m`,
        `regelsatz_m`, `disposable_income_m` and `income_after_housing_m`.

    Raises:
        ValueError: If any simulated result is not finite (A7).

    """
    _fail_if_case_columns_are_missing(cases)
    person_frames = []
    person_offset = 0
    household_offset = 0
    for household_key, group in cases.groupby("household_key", sort=True):
        frame = _build_person_frame(
            cases=group,
            household_key=str(household_key),
            person_offset=person_offset,
            household_offset=household_offset,
        )
        person_frames.append(frame)
        person_offset += len(frame)
        household_offset += len(group)
    persons = pd.concat(person_frames, ignore_index=True)
    raw = _run_gettsim(persons.drop(columns=["case_id"]))
    aggregated = _aggregate_to_case(
        raw.assign(case_id=persons["case_id"].to_numpy(), hh_id=persons["hh_id"]),
    )
    joined = cases.merge(aggregated, on="case_id", how="left", validate="one_to_one")
    result = _derive_outcomes(joined)
    _fail_if_not_finite(result)
    return result


def budget_curve(
    cells: pd.DataFrame,
    household_key: str,
    actual_bruttokaltmiete_m: NDArray[np.float64],
    heizkosten_m: float,
    incomes_m: NDArray[np.float64] | None = None,
    wogg_cap_column: str = "wogg_cap_m",
) -> pd.DataFrame:
    """Evaluate both scenarios on the ≤25 € income grid of §12.4.

    The Anspruch is asserted weakly decreasing along the grid for every cell and
    scenario, which is the property D10's bisection for `y*` relies on.
    """
    grid = (
        np.asarray(INCOME_GRID.points(), dtype=float)
        if incomes_m is None
        else np.asarray(incomes_m, dtype=float)
    )
    repeated, rent, income = expand_over_income(cells, grid, actual_bruttokaltmiete_m)
    cases = build_cases(
        cells=repeated,
        household_key=household_key,
        actual_bruttokaltmiete_m=rent,
        heizkosten_m=heizkosten_m,
        gross_income_m=income,
        wogg_cap_column=wogg_cap_column,
    )
    results = evaluate(cases)
    _fail_if_anspruch_is_not_monotone(results)
    return results


def exit_threshold_m(
    cells: pd.DataFrame,
    household_key: str,
    actual_bruttokaltmiete_m: NDArray[np.float64],
    heizkosten_m: float,
    wogg_cap_column: str = "wogg_cap_m",
    ceiling_m: float | None = None,
    tolerance_m: float | None = None,
) -> dict[str, NDArray[np.float64]]:
    """Locate the Transfer-Ausstiegsschwelle `y*` by bisection to one euro (D10).

    `y*` is the lowest gross monthly income at which no SGB claim remains. It is
    bracketed on a ladder that the monotonicity assertion runs over first, then
    narrowed by bisection, so the reported `Δy*` carries no 25 € grid artefact.

    Args:
        cells: Cells from `simulation_cells`.
        household_key: Key of the §11.1 Modellhaushalt.
        actual_bruttokaltmiete_m: Assumed actual rent `m`, one per cell.
        heizkosten_m: Heating cost held constant across scenarios.
        wogg_cap_column: Which Wohngeld benchmark the W scenario uses.
        ceiling_m: Technical upper bound on gross income; §12.4's 8,000 € by
            default.
        tolerance_m: Bisection precision; D10's one euro by default.

    Returns:
        One array of thresholds per scenario, aligned with the rows of `cells`.

    Raises:
        ValueError: If the Anspruch is not weakly decreasing in income, or if a
            cell still holds a claim at `ceiling_m`.

    """
    ceiling = float(INCOME_GRID.ceiling_eur if ceiling_m is None else ceiling_m)
    tolerance = float(
        INCOME_GRID.bisection_tolerance_eur if tolerance_m is None else tolerance_m,
    )
    ladder = np.linspace(0.0, ceiling, MONOTONICITY_LADDER_POINTS)
    on_ladder = budget_curve(
        cells=cells,
        household_key=household_key,
        actual_bruttokaltmiete_m=actual_bruttokaltmiete_m,
        heizkosten_m=heizkosten_m,
        incomes_m=ladder,
        wogg_cap_column=wogg_cap_column,
    )
    thresholds: dict[str, NDArray[np.float64]] = {}
    for scenario in SCENARIOS:
        claims = _anspruch_matrix(on_ladder, scenario, len(cells), len(ladder))
        _fail_if_a_claim_survives_the_ceiling(claims, scenario, ceiling)
        lower, upper = _bracket_from_ladder(claims, ladder)
        thresholds[scenario] = _bisect(
            cells=cells,
            household_key=household_key,
            actual_bruttokaltmiete_m=actual_bruttokaltmiete_m,
            heizkosten_m=heizkosten_m,
            wogg_cap_column=wogg_cap_column,
            scenario=scenario,
            lower=lower,
            upper=upper,
            tolerance=tolerance,
        )
    return thresholds


def national_heating_costs_m(ba_wohnkosten: pd.DataFrame) -> HeatingAssumption:
    """Derive the §12.3 heating assumption from the BA Wohnkosten data.

    §12.3 asks for the nationwide average recognised Heizkosten per household
    size. The BA publishes no national row, so the mean is taken over Kreise and
    weighted by the stock of Bedarfsgemeinschaften with recognised KdU — never an
    unweighted mean of Kreis figures, which would over-weight small Kreise.

    Args:
        ba_wohnkosten: The long BA Wohnkosten table.

    Returns:
        The heating assumption, one figure per household size.

    """
    kreise = ba_wohnkosten.query(
        "region_level == 'kreis' and breakdown == 'household_size'",
    )
    reference_month = str(kreise["reference_month"].max())
    latest = kreise.query("reference_month == @reference_month")
    # `query` resolves an `@name` from the caller's locals only, so these
    # module-level constants have to be bound here first.
    heizkosten_measure = BA_HEIZKOSTEN_MEASURE  # noqa: F841  read by query()
    stock_measure = BA_STOCK_MEASURE  # noqa: F841  read by query()
    values = latest.query("measure == @heizkosten_measure").set_index(
        ["region_code", "category"],
    )["value"]
    weights = latest.query("measure == @stock_measure").set_index(
        ["region_code", "category"],
    )["value"]
    joined = pd.concat({"value": values, "weight": weights}, axis=1).dropna()
    weighted = joined.groupby("category").apply(
        lambda group: (
            float((group["value"] * group["weight"]).sum())
            / float(group["weight"].sum())
        ),
        include_groups=False,
    )
    per_size = {
        size: float(round_currency_m(weighted[category]))
        for size, category in _BA_HOUSEHOLD_SIZE_CATEGORIES.items()
        if category in weighted.index
    }
    return HeatingAssumption(
        per_household_size=MappingProxyType(per_size),
        reference_month=reference_month,
        n_regions=int(joined.index.get_level_values("region_code").nunique()),
    )


def rent_grid_factors() -> NDArray[np.float64]:
    """The §12.2 Variante 2 rent grid: 50 % to 130 % of `max(K, W)`."""
    return np.round(np.arange(0.5, 1.3001, 0.1), 2)


def hours_equivalent(delta_y_star_m: NDArray[np.float64]) -> NDArray[np.float64]:
    """Convert a shift in the exit threshold into weekly Mindestlohn hours (§12.6)."""
    return np.asarray(delta_y_star_m, dtype=float) / MINDESTLOHN_EUR_PER_WEEKLY_HOUR_M


def wohnflaeche_sqm(household_size: int) -> float:
    """Admissible Wohnfläche assumed for a household of `household_size` persons."""
    return WOHNFLAECHE_BASE_SQM + WOHNFLAECHE_PER_FURTHER_PERSON_SQM * (
        household_size - 1
    )


# BA household-size categories, keyed by the household size they stand for.
_BA_HOUSEHOLD_SIZE_CATEGORIES: MappingProxyType[int, str] = MappingProxyType(
    {
        1: "1_person",
        2: "2_persons",
        3: "3_persons",
        4: "4_persons",
        5: "5_persons",
    },
)


@cache
def _input_template() -> MappingProxyType[str, Any]:
    """Every input column GETTSIM demands, filled with a neutral default."""
    template = dt.flatten_to_qnames(
        main(
            main_target=MainTarget.templates.input_data_dtypes.tree,
            policy_date_str=POLICY_DATE,
            tt_targets=TTTargets(tree=_TT_TARGETS),  # ty: ignore[unknown-argument]
        ),
    )
    row = {name: _DTYPE_DEFAULTS[str(dtype)] for name, dtype in template.items()}
    for name in row:
        if "p_id_" in name:
            row[name] = -1
    row[GETTSIM_UNTERKUNFTSKOSTEN_COLUMN] = 0.0
    return MappingProxyType(row)


@cache
def _gross_pension_per_entgeltpunkt_m() -> float:
    """Monthly gross Altersrente one Entgeltpunkt buys the pensioner household.

    The §12.4 income grid for the Rentnerhaushalt is a grid over the gross
    pension, but GETTSIM takes Entgeltpunkte. The pension is linear in
    Entgeltpunkte at a fixed Zugangsfaktor, so one GETTSIM call at a single
    Entgeltpunkt inverts the relation exactly.
    """
    household = MODEL_HOUSEHOLDS["pensioner_70"]
    row = dict(_input_template())
    row.update(_demographics(age=household.members[0].age))
    row.update(_pension_inputs(entgeltpunkte=1.0, age=household.members[0].age))
    row.update(
        {
            "p_id": 0,
            "hh_id": 0,
            "lohnsteuer__steuerklasse": 1,
            "wohngeld__mietstufe_hh": 3,
            "wohnen__wohnfläche_hh": wohnflaeche_sqm(1),
            "wohnen__heizkosten_m_hh": 0.0,
            "wohnen__bruttokaltmiete_m_hh": 0.0,
            "bürgergeld__bezug_im_vorjahr": True,
        },
    )
    result = _run_gettsim(pd.DataFrame([row]))
    return float(result["rente_m"].iloc[0])


def _demographics(age: int) -> dict[str, Any]:
    """Age inputs for a person of `age` completed years at the Analysestichtag.

    `alter` and `alter_monate` are ordinary input columns: GETTSIM does not
    derive them from `geburtsjahr`, and leaving them at their zero default makes
    every adult a newborn, silently. They are set here so that cannot happen.
    """
    return {
        "alter": age,
        "alter_monate": 12 * age + (ANALYSIS_DATE.month - 1),
        "geburtsjahr": ANALYSIS_DATE.year - age,
        "geburtsmonat": 1,
        "geburtstag": 1,
        "arbeitsstunden_w": 0.0,
        "sozialversicherung__rente__jahr_renteneintritt": ANALYSIS_DATE.year,
        "sozialversicherung__rente__monat_renteneintritt": 1,
    }


def _pension_inputs(entgeltpunkte: float, age: int) -> dict[str, Any]:
    """Pension inputs placing the household at the Regelaltersgrenze.

    The Entgeltpunkte are chosen so that no Abschlag applies.
    """
    return {
        "sozialversicherung__rente__bezieht_rente": True,
        "sozialversicherung__rente__entgeltpunkte": entgeltpunkte,
        "sozialversicherung__rente__pflichtbeitragsmonate": (
            PENSIONER_PFLICHTBEITRAGSMONATE
        ),
        "sozialversicherung__rente__jahr_renteneintritt": (
            ANALYSIS_DATE.year - age + PENSIONER_RETIREMENT_AGE_YEARS
        ),
        "sozialversicherung__rente__monat_renteneintritt": PENSIONER_RETIREMENT_MONTH,
    }


def _build_person_frame(
    cases: pd.DataFrame,
    household_key: str,
    person_offset: int,
    household_offset: int,
) -> pd.DataFrame:
    """Expand a case frame into one GETTSIM input row per person."""
    household = MODEL_HOUSEHOLDS[household_key]
    members = household.members
    n_cases = len(cases)
    n_members = len(members)
    slot = np.tile(np.arange(n_members), n_cases)
    case_position = np.repeat(np.arange(n_cases), n_members)
    total = n_cases * n_members

    frame = pd.DataFrame(
        {name: np.full(total, value) for name, value in _input_template().items()},
    )
    for name, value in _demographics(age=0).items():
        frame[name] = np.full(total, value)
    ages = np.array([member.age for member in members])[slot]
    frame["alter"] = ages
    frame["alter_monate"] = 12 * ages + (ANALYSIS_DATE.month - 1)
    frame["geburtsjahr"] = ANALYSIS_DATE.year - ages

    household_base = person_offset + case_position * n_members
    frame["p_id"] = person_offset + np.arange(total)
    frame["hh_id"] = household_offset + case_position

    is_child = np.array(
        [member.role is MemberRole.CHILD for member in members],
    )[slot]
    is_pensioner = np.array(
        [member.role is MemberRole.ADULT_PENSIONER for member in members],
    )[slot]
    frame["familie__alleinerziehend"] = household.is_single_parent & ~is_child
    frame["sozialversicherung__pflege__beitrag__hat_kinder"] = household.n_children > 0
    frame["lohnsteuer__steuerklasse"] = _steuerklasse(household, is_child)
    frame["einkommensteuer__gemeinsam_veranlagt"] = (
        household.n_adults == N_ADULTS_IN_COUPLE
    ) & ~is_child

    _link_family(frame, household, slot, household_base, is_child)

    frame["wohngeld__mietstufe_hh"] = np.repeat(
        cases["mietenstufe"].to_numpy(dtype=int),
        n_members,
    )
    frame["wohnen__wohnfläche_hh"] = wohnflaeche_sqm(household.household_size)
    frame["wohnen__heizkosten_m_hh"] = np.repeat(
        cases["heizkosten_m"].to_numpy(dtype=float),
        n_members,
    )
    frame["wohnen__bruttokaltmiete_m_hh"] = np.repeat(
        cases["actual_bruttokaltmiete_m"].to_numpy(dtype=float),
        n_members,
    )
    frame["bürgergeld__bezug_im_vorjahr"] = household.karenzzeit_elapsed
    frame[GETTSIM_UNTERKUNFTSKOSTEN_COLUMN] = kopfteil_m(
        np.repeat(cases["unterkunftskosten_m"].to_numpy(dtype=float), n_members),
        np.full(total, household.household_size),
    )

    income = np.repeat(cases["gross_income_m"].to_numpy(dtype=float), n_members)
    _assign_income(frame, household, slot, income, is_pensioner)

    frame["case_id"] = np.repeat(cases["case_id"].to_numpy(), n_members)
    return frame


def _steuerklasse(household: Any, is_child: NDArray[np.bool_]) -> NDArray[np.int_]:  # noqa: ANN401
    """Lohnsteuerklasse: I single, II Alleinerziehend, IV/IV for a couple."""
    if household.is_single_parent:
        adult_class = 2
    elif household.n_adults == N_ADULTS_IN_COUPLE:
        adult_class = 4
    else:
        adult_class = 1
    return np.where(is_child, 1, adult_class)


def _link_family(
    frame: pd.DataFrame,
    household: Any,  # noqa: ANN401
    slot: NDArray[np.int_],
    household_base: NDArray[np.int_],
    is_child: NDArray[np.bool_],
) -> None:
    """Wire up the Ehepartner, Einstandspartner, Elternteil and Kindergeld links."""
    first_adult = household_base
    if household.n_adults == N_ADULTS_IN_COUPLE:
        partner_slot = np.where(slot == 0, 1, 0)
        partner_id = household_base + partner_slot
        frame["familie__p_id_ehepartner"] = np.where(is_child, -1, partner_id)
        frame["bürgergeld__p_id_einstandspartner"] = np.where(is_child, -1, partner_id)
    frame["familie__p_id_elternteil_1"] = np.where(is_child, first_adult, -1)
    if household.n_adults == N_ADULTS_IN_COUPLE:
        frame["familie__p_id_elternteil_2"] = np.where(
            is_child,
            household_base + 1,
            -1,
        )
    frame["kindergeld__p_id_empfänger"] = np.where(is_child, first_adult, -1)


def _assign_income(
    frame: pd.DataFrame,
    household: Any,  # noqa: ANN401
    slot: NDArray[np.int_],
    income: NDArray[np.float64],
    is_pensioner: NDArray[np.bool_],
) -> None:
    """Put the grid income on the household's earner or on its pensioner.

    Earnings go to the first adult alone. §11.1 fixes no split across a couple,
    and a single-earner couple is the case in which the Erwerbstätigenfreibetrag
    of § 11b SGB II is claimed once rather than twice; the alternative split is a
    separate scenario, not a silent default.
    """
    if not household.has_earnings:
        entgeltpunkte = income / _gross_pension_per_entgeltpunkt_m()
        frame["sozialversicherung__rente__bezieht_rente"] = is_pensioner
        frame["sozialversicherung__rente__entgeltpunkte"] = np.where(
            is_pensioner,
            entgeltpunkte,
            0.0,
        )
        frame["sozialversicherung__rente__pflichtbeitragsmonate"] = np.where(
            is_pensioner,
            PENSIONER_PFLICHTBEITRAGSMONATE,
            0.0,
        )
        ages = frame["alter"].to_numpy()
        frame["sozialversicherung__rente__jahr_renteneintritt"] = np.where(
            is_pensioner,
            ANALYSIS_DATE.year - ages + PENSIONER_RETIREMENT_AGE_YEARS,
            ANALYSIS_DATE.year,
        )
        frame["sozialversicherung__rente__monat_renteneintritt"] = np.where(
            is_pensioner,
            PENSIONER_RETIREMENT_MONTH,
            1,
        )
        return
    is_earner = slot == 0
    frame["einnahmen__bruttolohn_m"] = np.where(is_earner, income, 0.0)
    frame["arbeitsstunden_w"] = np.where(is_earner & (income > 0.0), 40.0, 0.0)


def _run_gettsim(persons: pd.DataFrame) -> pd.DataFrame:
    """One GETTSIM call over one row per person."""
    return main(  # ty: ignore[invalid-return-type]
        main_target=MainTarget.results.df_with_mapper,
        policy_date_str=POLICY_DATE,
        input_data=InputData.df_with_qname_columns(persons),
        tt_targets=TTTargets(tree=_TT_TARGETS),  # ty: ignore[unknown-argument]
    )


def _aggregate_to_case(raw: pd.DataFrame) -> pd.DataFrame:
    """Collapse person rows to one row per case, respecting each output's level."""
    by_case = raw.groupby("case_id", sort=True)
    aggregated = by_case[list(_PERSON_LEVEL_OUTPUTS)].sum()
    for column in _GROUP_LEVEL_OUTPUTS:
        aggregated[column] = by_case[column].first()
    for column in _RATE_LEVEL_OUTPUTS:
        aggregated[column] = by_case[column].max()
    for column in _STEUERNUMMER_LEVEL_OUTPUTS:
        per_steuernummer = raw.drop_duplicates(subset=["case_id", "sn_id"])
        aggregated[column] = per_steuernummer.groupby("case_id", sort=True)[
            column
        ].sum()
    return aggregated.reset_index()


def _derive_outcomes(joined: pd.DataFrame) -> pd.DataFrame:
    """Add the §12.6 outcome columns and apply the central rounding rule."""
    anspruch = round_currency_m(
        joined["buergergeld_anspruch_m"] + joined["grundsicherung_anspruch_m"],
    )
    sgb_betrag = round_currency_m(
        joined["buergergeld_betrag_m"] + joined["grundsicherung_betrag_m"],
    )
    market_income = joined["gross_income_m"].to_numpy(dtype=float)
    taxes_m = (
        joined["einkommensteuer_y_sn"] + joined["solidaritaetszuschlag_y_sn"]
    ) / 12.0
    disposable = round_currency_m(
        market_income
        - joined["sozialbeitraege_m"].to_numpy(dtype=float)
        - taxes_m.to_numpy(dtype=float)
        + joined["kindergeld_m"].to_numpy(dtype=float)
        + joined["unterhaltsvorschuss_m"].to_numpy(dtype=float)
        + sgb_betrag
        + joined["wohngeld_m"].to_numpy(dtype=float)
        + joined["kinderzuschlag_m"].to_numpy(dtype=float),
    )
    warm_rent = joined["actual_bruttokaltmiete_m"].to_numpy(dtype=float) + joined[
        "heizkosten_m"
    ].to_numpy(dtype=float)
    return joined.assign(
        anspruch_m=anspruch,
        sgb_betrag_m=sgb_betrag,
        anerkannte_kdu_m=round_currency_m(joined["anerkannte_kdu_m"]),
        regelsatz_m=round_currency_m(joined["regelsatz_m"]),
        wohngeld_m=round_currency_m(joined["wohngeld_m"]),
        kinderzuschlag_m=round_currency_m(joined["kinderzuschlag_m"]),
        kindergeld_m=round_currency_m(joined["kindergeld_m"]),
        disposable_income_m=disposable,
        income_after_housing_m=round_currency_m(disposable - warm_rent),
        receives_sgb=sgb_betrag > 0.0,
    ).drop(
        columns=[
            "buergergeld_anspruch_m",
            "buergergeld_betrag_m",
            "grundsicherung_anspruch_m",
            "grundsicherung_betrag_m",
            "einkommensteuer_y_sn",
            "solidaritaetszuschlag_y_sn",
        ],
    )


def _anspruch_matrix(
    results: pd.DataFrame,
    scenario: str,  # noqa: ARG001  read by query()
    n_cells: int,
    n_incomes: int,
) -> NDArray[np.float64]:
    """Reshape one scenario's grid results into a cell-by-income matrix."""
    ordered = results.query("scenario == @scenario").sort_values(
        ["cell_id", "gross_income_m"],
    )
    return ordered["anspruch_m"].to_numpy(dtype=float).reshape(n_cells, n_incomes)


def _bracket_from_ladder(
    claims: NDArray[np.float64],
    ladder: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return the last income with a claim and the first without, per cell."""
    exhausted = claims <= 0.0
    first_zero = np.argmax(exhausted, axis=1)
    lower = np.where(first_zero == 0, 0.0, ladder[np.maximum(first_zero - 1, 0)])
    return lower, ladder[first_zero]


def _bisect(
    cells: pd.DataFrame,
    household_key: str,
    actual_bruttokaltmiete_m: NDArray[np.float64],
    heizkosten_m: float,
    wogg_cap_column: str,
    scenario: str,  # noqa: ARG001  read by query()
    lower: NDArray[np.float64],
    upper: NDArray[np.float64],
    tolerance: float,
) -> NDArray[np.float64]:
    """Narrow `[lower, upper]` to `tolerance` and return the whole-euro threshold."""
    lower = lower.copy()
    upper = upper.copy()
    while np.max(upper - lower) > tolerance:
        midpoint = 0.5 * (lower + upper)
        cases = build_cases(
            cells=cells,
            household_key=household_key,
            actual_bruttokaltmiete_m=actual_bruttokaltmiete_m,
            heizkosten_m=heizkosten_m,
            gross_income_m=midpoint,
            wogg_cap_column=wogg_cap_column,
        )
        claims = (
            evaluate(cases)
            .query("scenario == @scenario")
            .sort_values("cell_id")["anspruch_m"]
            .to_numpy(dtype=float)
        )
        still_claiming = claims > 0.0
        lower = np.where(still_claiming, midpoint, lower)
        upper = np.where(still_claiming, upper, midpoint)
    return np.ceil(upper)


def _fail_if_case_columns_are_missing(cases: pd.DataFrame) -> None:
    missing = [name for name in CASE_COLUMNS if name not in cases.columns]
    if missing:
        msg = f"case frame is missing the required columns {missing}"
        raise ValueError(msg)


def _fail_if_not_finite(results: pd.DataFrame) -> None:
    """A7: GETTSIM's benign 0/0 for a zero-income household must not propagate."""
    numeric = results.select_dtypes("number")
    finite = np.isfinite(numeric.to_numpy(dtype=float))
    if not finite.all():
        offending = numeric.columns[~finite.all(axis=0)].tolist()
        msg = (
            f"simulated results are not finite in columns {offending}; "
            f"GETTSIM's 0/0 for zero-income households must not have propagated"
        )
        raise ValueError(msg)


def _fail_if_anspruch_is_not_monotone(results: pd.DataFrame) -> None:
    """D10: monotonicity in income is checked, never assumed."""
    for keys, group in results.groupby(["scenario", "cell_id"]):
        scenario, cell_id = cast("tuple[str, int]", keys)
        fail_if_not_weakly_decreasing(
            group.sort_values("gross_income_m")["anspruch_m"].to_numpy(dtype=float),
            name=f"anspruch_m (scenario {scenario}, cell {cell_id})",
        )


def _fail_if_a_claim_survives_the_ceiling(
    claims: NDArray[np.float64],
    scenario: str,
    ceiling: float,
) -> None:
    surviving = int((claims[:, -1] > 0.0).sum())
    if surviving:
        msg = (
            f"{surviving} cells still hold an SGB claim at the technical income "
            f"ceiling of {ceiling} EUR in scenario {scenario}, so y* is not "
            f"bracketed"
        )
        raise ValueError(msg)


__all__ = [
    "CASE_COLUMNS",
    "HEIZKOSTEN_SENSITIVITY_FACTORS",
    "MINDESTLOHN_EUR_PER_HOUR",
    "MINDESTLOHN_EUR_PER_WEEKLY_HOUR_M",
    "POLICY_DATE",
    "SCENARIOS",
    "SCENARIO_KDU",
    "SCENARIO_WOGG",
    "HeatingAssumption",
    "assign_cells",
    "budget_curve",
    "build_cases",
    "evaluate",
    "exit_threshold_m",
    "expand_over_income",
    "hours_equivalent",
    "national_heating_costs_m",
    "rent_grid_factors",
    "simulation_cells",
    "wohnflaeche_sqm",
]
