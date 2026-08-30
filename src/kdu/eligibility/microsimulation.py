"""The gross income at which a Modellhaushalt leaves the transfer system.

Two scenarios differ in one number. One recognises the local KdU-Obergrenze as
the Bruttokaltmiete cap, the other the Wohngeld fallback that BSG case law
prescribes where a Kreis publishes no schlüssiges Konzept. Every other legal and
economic parameter is identical.

At zero income the recognised rent enters the Bedarf one for one, so the
difference in Anspruch between the two scenarios equals the difference between
the two caps exactly. That identity needs no simulation and this module does not
compute it.

What does need a simulation is the Transfer-Ausstiegsschwelle: the lowest gross
monthly income at which no SGB claim remains. A household whose recognised rent
is higher has a higher Bedarf and so remains entitled up to a higher income, but
closing a cap difference of one euro takes more than one euro of gross earnings,
because the Einkommensanrechnung of § 11b SGB II withdraws only part of each
additional euro, because Steuern and Sozialversicherungsbeiträge intervene, and
because the household may pass from Bürgergeld into Wohngeld on the way out. The
resulting amplification is the quantity this module reports.

The public surface is:

- `distinct_cap_pairs` and `assign_cap_pairs` — one evaluation per distinct
  combination of local cap and Mietenstufe rather than one per Gemeinde
- `build_cases` — turn cap pairs into the two-scenario case frame
- `evaluate` — run GETTSIM on a case frame and return household-level outcomes
- `exit_threshold_eur_per_month` — locate the threshold by bisection to one euro
- `national_heizkosten_eur_per_month` — the heating assumption, from the
  Wohnkostenstatistik of the Bundesagentur für Arbeit
- `exit_threshold_by_gemeinde`, `summarise_exit_thresholds` and
  `plot_exit_threshold_distribution` — the reported results

All amounts are euro per month.
"""

from dataclasses import dataclass
from functools import cache
from types import MappingProxyType
from typing import Any

import dags.tree as dt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from gettsim import InputData, MainTarget, TTTargets, main
from numpy.typing import NDArray

from kdu.config import (
    ANALYSIS_DATE,
    INCOME_GRID,
    MODEL_HOUSEHOLDS,
    MemberRole,
)
from kdu.eligibility.recognised_housing_costs import (
    GETTSIM_UNTERKUNFTSKOSTEN_COLUMN,
    fail_if_not_weakly_decreasing,
    kopfteil_eur_per_month,
    recognised_bruttokaltmiete_eur_per_month,
    round_currency,
    unterkunftskosten_eur_per_month,
)

pio.templates.default = "plotly_dark"

# Number of adults in a couple household.
N_ADULTS_IN_COUPLE = 2

# The Rechtsstand every GETTSIM call is evaluated at.
POLICY_DATE = ANALYSIS_DATE.isoformat()

# The two scenarios. They differ only in which cap enters `min(actual rent, cap)`.
SCENARIO_LOCAL_CAP = "local_kdu_cap"
SCENARIO_FALLBACK = "wohngeld_fallback"
SCENARIOS: tuple[str, str] = (SCENARIO_LOCAL_CAP, SCENARIO_FALLBACK)

# The measure of recognised heating costs read from the Wohnkostenstatistik, and
# the stock of Bedarfsgemeinschaften its national mean is weighted by.

# Number of ascending income points that bracket the exit threshold and carry
# the monotonicity assertion before bisection starts.
INCOME_LADDER_POINTS = 65

# Admissible Wohnfläche assumed for a household: 45 square metres for the first
# person and 15 for each further one. It reaches only GETTSIM's own housing
# rule, which the override prunes away, but Wohngeld and GETTSIM's input
# validation still require a plausible value.
WOHNFLAECHE_BASE_SQM = 45.0
WOHNFLAECHE_PER_FURTHER_PERSON_SQM = 15.0

# Contribution months credited to the pensioner household. 45 years of
# Pflichtbeiträge put the Zugangsfaktor at exactly 1.0 for retirement at the
# Regelaltersgrenze, so the pension is Entgeltpunkte times Rentenwert with no
# Abschlag and no Zuschlag to explain away.
PENSIONER_PFLICHTBEITRAGSMONATE = 540.0

# Age at which the pensioner household is assumed to have retired.
PENSIONER_RETIREMENT_AGE_YEARS = 65
PENSIONER_RETIREMENT_MONTH = 11

# Every column `evaluate` expects on a case frame.
CASE_COLUMNS: tuple[str, ...] = (
    "case_id",
    "cap_pair_id",
    "scenario",
    "household_key",
    "mietenstufe",
    "kdu_cap",
    "wohngeld_fallback_cap",
    "actual_bruttokaltmiete",
    "heizkosten",
    "gross_income",
    "recognised_bruttokaltmiete",
    "unterkunftskosten",
)

_TT_TARGETS: dict[str, Any] = {
    "bürgergeld": {
        "anspruchshöhe_m": "buergergeld_anspruch",
        "betrag_m": "buergergeld_betrag",
        "regelsatz_m": "regelsatz",
        "kosten_der_unterkunft_m": "anerkannte_unterkunftskosten",
    },
    "grundsicherung": {
        "im_alter": {
            "anspruchshöhe_m": "grundsicherung_anspruch",
            "betrag_m": "grundsicherung_betrag",
        },
    },
    "wohngeld": {"betrag_m_wthh": "wohngeld"},
    "kinderzuschlag": {"betrag_m_bg": "kinderzuschlag"},
    "kindergeld": {"betrag_m": "kindergeld"},
    "unterhaltsvorschuss": {"betrag_m": "unterhaltsvorschuss"},
    "sn_id": "sn_id",
}

# GETTSIM outputs that are person-level and therefore summed over the household.
_PERSON_LEVEL_OUTPUTS: tuple[str, ...] = (
    "buergergeld_anspruch",
    "buergergeld_betrag",
    "grundsicherung_anspruch",
    "grundsicherung_betrag",
    "regelsatz",
    "anerkannte_unterkunftskosten",
    "kindergeld",
    "unterhaltsvorschuss",
)

# GETTSIM outputs that already hold a group total repeated on every member, so
# they are taken once rather than summed.
_GROUP_LEVEL_OUTPUTS: tuple[str, ...] = ("wohngeld", "kinderzuschlag")

_DTYPE_DEFAULTS: MappingProxyType[str, Any] = MappingProxyType(
    {"BoolColumn": False, "IntColumn": 0, "FloatColumn": 0.0},
)

# Wohnkostenstatistik column names for each household size.


@dataclass(frozen=True)
class HeatingAssumption:
    """Recognised heating costs, held constant across the two scenarios."""

    per_household_size: MappingProxyType[int, float]
    """Recognised Heizkosten in euro per month, by household size."""
    n_regions: int
    """Number of Jobcenter the stock-weighted mean was taken over."""

    def for_household(self, household_key: str) -> float:
        """Return the heating assumption for a Modellhaushalt."""
        size = MODEL_HOUSEHOLDS[household_key].household_size
        return self.per_household_size[size]


def distinct_cap_pairs(sample: pd.DataFrame, household_size: int) -> pd.DataFrame:
    """Reduce the Gemeinde sample to its distinct cap and Mietenstufe pairs.

    Two Gemeinden that share a local KdU-Obergrenze and a Mietenstufe produce
    identical simulated outcomes at a given household size, because those two
    attributes fix the recognised Bruttokaltmiete and the Wohngeld branch alike.
    Evaluating one row per distinct pair is therefore exact, not an
    approximation, and `assign_cap_pairs` joins the results back to every
    Gemeinde. At household size one it replaces about 9,350 evaluations with
    about 770.

    Gemeinden without a statutory Mietenstufe carry no Wohngeld benchmark, so no
    contrast is defined for them and they are dropped here rather than imputed.

    Args:
        sample: The joined caps and fallback, keyed `ags` by `household_size`.
        household_size: The household size at which the caps are read.

    Returns:
        One row per distinct pair, with `cap_pair_id`, `kdu_cap`,
        `wohngeld_fallback_cap`, `mietenstufe`, `household_size` and the number
        of Gemeinden it covers.

    """
    contrasted = sample.loc[sample["household_size"] == household_size].dropna(
        subset=["kdu_cap", "wohngeld_fallback_cap", "mietenstufe"],
    )
    grouped = (
        contrasted.astype({"mietenstufe": "int64"})
        .groupby(["kdu_cap", "mietenstufe"], as_index=False)
        .agg(
            wohngeld_fallback_cap=("wohngeld_fallback_cap", "first"),
            n_gemeinden=("wohngeld_fallback_cap", "size"),
        )
    )
    return grouped.assign(
        cap_pair_id=np.arange(len(grouped)),
        kdu_cap=lambda frame: frame["kdu_cap"].astype(float),
        wohngeld_fallback_cap=lambda frame: frame["wohngeld_fallback_cap"].astype(
            float,
        ),
        household_size=household_size,
    ).loc[
        :,
        [
            "cap_pair_id",
            "kdu_cap",
            "wohngeld_fallback_cap",
            "mietenstufe",
            "household_size",
            "n_gemeinden",
        ],
    ]


def assign_cap_pairs(
    sample: pd.DataFrame,
    pairs: pd.DataFrame,
    household_size: int,
) -> pd.DataFrame:
    """Join every Gemeinde of the sample onto its cap pair.

    Gemeinden without a Mietenstufe remain in the frame with a null
    `cap_pair_id`, so the coverage gap stays visible rather than disappearing.

    Args:
        sample: The joined caps and fallback, keyed `ags` by `household_size`.
        pairs: Cap pairs from `distinct_cap_pairs`.
        household_size: The household size the pairs were built at.

    Returns:
        One row per Gemeinde with `ags`, `kdu_cap`, `mietenstufe` and
        `cap_pair_id`.

    """
    keys = sample.loc[
        sample["household_size"] == household_size,
        ["ags", "kdu_cap", "mietenstufe"],
    ]
    lookup = pairs.loc[:, ["cap_pair_id", "kdu_cap", "mietenstufe"]]
    joined = keys.astype({"mietenstufe": "Int64"}).merge(
        lookup.astype({"mietenstufe": "Int64"}),
        on=["kdu_cap", "mietenstufe"],
        how="left",
        validate="many_to_one",
    )
    _fail_if_join_duplicated_rows(joined, len(keys), "assign_cap_pairs")
    return joined


def build_cases(
    pairs: pd.DataFrame,
    household_key: str,
    actual_bruttokaltmiete: NDArray[np.float64],
    heizkosten: float,
    gross_income: NDArray[np.float64],
) -> pd.DataFrame:
    """Turn cap pairs into the two-scenario case frame.

    Each pair yields exactly two cases that differ in one number only: the cap
    entering `min(actual rent, cap)`. Heating is added to both identically, so
    it cancels from their difference.

    Args:
        pairs: Cap pairs from `distinct_cap_pairs`, or any frame carrying
            `cap_pair_id`, `kdu_cap`, `wohngeld_fallback_cap` and `mietenstufe`.
        household_key: Key of the Modellhaushalt.
        actual_bruttokaltmiete: Assumed actual rent, one per row of `pairs`.
        heizkosten: Heating cost held constant across scenarios.
        gross_income: Gross monthly income, one per row of `pairs`.

    Returns:
        A frame with `CASE_COLUMNS`, two rows per cap pair.

    """
    local_cap = pairs["kdu_cap"].to_numpy(dtype=float)
    fallback_cap = pairs["wohngeld_fallback_cap"].to_numpy(dtype=float)
    caps = {SCENARIO_LOCAL_CAP: local_cap, SCENARIO_FALLBACK: fallback_cap}
    rent = np.asarray(actual_bruttokaltmiete, dtype=float)
    income = np.asarray(gross_income, dtype=float)
    heating = np.full(len(pairs), float(heizkosten))
    frames = [
        pd.DataFrame(
            {
                "cap_pair_id": pairs["cap_pair_id"].to_numpy(),
                "scenario": scenario,
                "household_key": household_key,
                "mietenstufe": pairs["mietenstufe"].to_numpy(dtype=int),
                "kdu_cap": local_cap,
                "wohngeld_fallback_cap": fallback_cap,
                "actual_bruttokaltmiete": rent,
                "heizkosten": heating,
                "gross_income": income,
                "recognised_bruttokaltmiete": (
                    recognised_bruttokaltmiete_eur_per_month(rent, cap)
                ),
                "unterkunftskosten": unterkunftskosten_eur_per_month(
                    rent,
                    cap,
                    heating,
                ),
            },
        )
        for scenario, cap in caps.items()
    ]
    cases = pd.concat(frames, ignore_index=True)
    return cases.assign(case_id=np.arange(len(cases))).loc[:, list(CASE_COLUMNS)]


def evaluate(cases: pd.DataFrame) -> pd.DataFrame:
    """Run GETTSIM on a case frame and return household-level outcomes.

    One GETTSIM call covers every case in the frame, whatever the Modellhaushalt:
    GETTSIM is vectorised over one row per person.

    Args:
        cases: A frame with `CASE_COLUMNS`, as `build_cases` produces.

    Returns:
        `cases` with one row per case and the simulated outcomes joined on,
        including `anspruch` — the SGB claim before the Vorrangprüfung — and
        `sgb_betrag`, the amount actually paid.

    Raises:
        ValueError: If any simulated result is not finite.

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


def exit_threshold_eur_per_month(
    pairs: pd.DataFrame,
    household_key: str,
    actual_bruttokaltmiete: NDArray[np.float64],
    heizkosten: float,
    ceiling: float | None = None,
    tolerance: float | None = None,
) -> dict[str, NDArray[np.float64]]:
    """Locate the Transfer-Ausstiegsschwelle by bisection to one euro.

    The threshold is the lowest gross monthly income at which no SGB claim
    remains. It is bracketed on an ascending sequence of incomes that the
    monotonicity assertion runs over first, then narrowed by bisection, so the
    reported difference carries no grid artefact.

    Args:
        pairs: Cap pairs from `distinct_cap_pairs`.
        household_key: Key of the Modellhaushalt.
        actual_bruttokaltmiete: Assumed actual rent, one per cap pair.
        heizkosten: Heating cost held constant across scenarios.
        ceiling: Technical upper bound on gross income.
        tolerance: Bisection precision, one euro by default.

    Returns:
        One array of thresholds per scenario, aligned with the rows of `pairs`.

    Raises:
        ValueError: If the Anspruch is not weakly decreasing in income, or if a
            cap pair still holds a claim at `ceiling`.

    """
    upper_bound = float(INCOME_GRID.ceiling_eur if ceiling is None else ceiling)
    precision = float(
        INCOME_GRID.bisection_tolerance_eur if tolerance is None else tolerance,
    )
    ladder = np.linspace(0.0, upper_bound, INCOME_LADDER_POINTS)
    on_ladder = _evaluate_on_income_ladder(
        pairs=pairs,
        household_key=household_key,
        actual_bruttokaltmiete=actual_bruttokaltmiete,
        heizkosten=heizkosten,
        incomes=ladder,
    )
    thresholds: dict[str, NDArray[np.float64]] = {}
    for scenario in SCENARIOS:
        claims = _anspruch_matrix(on_ladder, scenario, len(pairs), len(ladder))
        _fail_if_a_claim_survives_the_ceiling(claims, scenario, upper_bound)
        lower, upper = _bracket_from_ladder(claims, ladder)
        thresholds[scenario] = _bisect(
            pairs=pairs,
            household_key=household_key,
            actual_bruttokaltmiete=actual_bruttokaltmiete,
            heizkosten=heizkosten,
            scenario=scenario,
            lower=lower,
            upper=upper,
            tolerance=precision,
        )
    return thresholds


def national_heizkosten_eur_per_month(
    wohnkostenstatistik: pd.DataFrame,
) -> HeatingAssumption:
    """Derive the heating assumption from the Wohnkostenstatistik.

    The Bundesagentur für Arbeit publishes no national row, so the mean over
    Jobcenter is weighted by the stock of Bedarfsgemeinschaften. An unweighted
    mean of Jobcenter figures would over-weight small Jobcenter.

    Args:
        wohnkostenstatistik: The cleaned table, one row per Jobcenter and
            household size, carrying `heizkosten` and `bedarfsgemeinschaften`.

    Returns:
        The heating assumption, one figure per household size.

    """
    reported = wohnkostenstatistik.dropna(
        subset=["recognised_heizkosten", "bedarfsgemeinschaften"],
    ).query("bedarfsgemeinschaften > 0")
    weighted = reported["recognised_heizkosten"] * reported["bedarfsgemeinschaften"]
    per_size = {
        int(size): float(round_currency(value))
        for size, value in (
            weighted.groupby(reported["household_size"]).sum()
            / reported["bedarfsgemeinschaften"]
            .groupby(reported["household_size"])
            .sum()
        ).items()
    }
    return HeatingAssumption(
        per_household_size=MappingProxyType(per_size),
        n_regions=int(reported["jobcenter_id"].nunique()),
    )


def wohnflaeche_sqm(household_size: int) -> float:
    """Admissible Wohnfläche assumed for a household of `household_size`."""
    return WOHNFLAECHE_BASE_SQM + WOHNFLAECHE_PER_FURTHER_PERSON_SQM * (
        household_size - 1
    )


def exit_threshold_by_gemeinde(
    sample: pd.DataFrame,
    heating: HeatingAssumption,
) -> pd.DataFrame:
    """Compute the exit threshold under both caps for every Gemeinde.

    The assumed actual Bruttokaltmiete is the larger of the two caps, so the cap
    binds in both scenarios and the contrast isolates the effect of the cap
    rather than of an arbitrary rent assumption.

    Args:
        sample: The joined caps and fallback, keyed `ags` by `household_size`.
        heating: The heating assumption from
            `national_heizkosten_eur_per_month`.

    Returns:
        One row per Gemeinde and Modellhaushalt, with the two thresholds, their
        difference, the difference between the caps, and the amplification.

    """
    frames = []
    for household_key, household in MODEL_HOUSEHOLDS.items():
        size = household.household_size
        pairs = distinct_cap_pairs(sample, size)
        rent = np.maximum(
            pairs["kdu_cap"].to_numpy(dtype=float),
            pairs["wohngeld_fallback_cap"].to_numpy(dtype=float),
        )
        thresholds = exit_threshold_eur_per_month(
            pairs=pairs,
            household_key=household_key,
            actual_bruttokaltmiete=rent,
            heizkosten=heating.for_household(household_key),
        )
        resolved = pairs.assign(
            household_key=household_key,
            actual_bruttokaltmiete=rent,
            exit_threshold_local_cap=thresholds[SCENARIO_LOCAL_CAP],
            exit_threshold_fallback=thresholds[SCENARIO_FALLBACK],
        )
        assigned = assign_cap_pairs(sample, pairs, size)
        frames.append(
            assigned.loc[:, ["ags", "cap_pair_id"]].merge(
                resolved,
                on="cap_pair_id",
                how="inner",
                validate="many_to_one",
            ),
        )
    result = pd.concat(frames, ignore_index=True)
    return result.assign(
        cap_difference=lambda frame: round_currency(
            frame["kdu_cap"] - frame["wohngeld_fallback_cap"],
        ),
        exit_threshold_difference=lambda frame: (
            frame["exit_threshold_local_cap"] - frame["exit_threshold_fallback"]
        ),
    )


def summarise_exit_thresholds(thresholds: pd.DataFrame) -> pd.DataFrame:
    """Summarise the exit-threshold contrast by Modellhaushalt.

    The amplification is the median over Gemeinden of the per-Gemeinde ratio of
    the change in exit threshold to the difference between the caps. Gemeinden
    whose caps differ by no more than one euro are excluded from it: their ratio
    is a small number divided by a smaller one and carries no information about
    how the transfer withdrawal translates a cap difference into income.

    Args:
        thresholds: The frame `exit_threshold_by_gemeinde` returns.

    Returns:
        One row per Modellhaushalt with the deciles of the cap difference and of
        the change in exit threshold, and the amplification.

    """
    rows = []
    for household_key, group in thresholds.groupby("household_key", sort=True):
        cap_difference = group["cap_difference"]
        threshold_difference = group["exit_threshold_difference"]
        binding = group.query("cap_difference.abs() > 1.0")
        rows.append(
            {
                "household_key": household_key,
                "household_label": MODEL_HOUSEHOLDS[str(household_key)].label,
                "n_gemeinden": len(group),
                "cap_difference_p10": cap_difference.quantile(0.10),
                "cap_difference_median": cap_difference.median(),
                "cap_difference_p90": cap_difference.quantile(0.90),
                "exit_threshold_difference_p10": threshold_difference.quantile(0.10),
                "exit_threshold_difference_median": threshold_difference.median(),
                "exit_threshold_difference_p90": threshold_difference.quantile(0.90),
                "amplification": (
                    float(
                        (
                            binding["exit_threshold_difference"]
                            / binding["cap_difference"]
                        ).median(),
                    )
                    if len(binding)
                    else float("nan")
                ),
            },
        )
    return pd.DataFrame(rows).round(3)


def plot_exit_threshold_distribution(thresholds: pd.DataFrame) -> go.Figure:
    """Plot the change in exit threshold against the difference between caps.

    One panel per Modellhaushalt. The identity line marks where a one-euro cap
    difference would move the exit threshold by one euro; the vertical distance
    from it is the amplification the transfer withdrawal produces.

    Args:
        thresholds: The frame `exit_threshold_by_gemeinde` returns.

    Returns:
        The figure.

    """
    households = sorted(thresholds["household_key"].unique())
    figure = go.Figure()
    for index, household_key in enumerate(households):
        group = thresholds.query("household_key == @household_key")
        figure.add_trace(
            go.Scattergl(
                x=group["cap_difference"],
                y=group["exit_threshold_difference"],
                mode="markers",
                name=MODEL_HOUSEHOLDS[household_key].label,
                marker={"size": 3, "opacity": 0.35},
                visible=index == 0,
            ),
        )
    span = float(thresholds["cap_difference"].abs().max())
    figure.add_trace(
        go.Scatter(
            x=[-span, span],
            y=[-span, span],
            mode="lines",
            name="One euro of cap, one euro of income",
            line={"color": "grey", "dash": "dash"},
        ),
    )
    figure.update_layout(
        title=("A cap error moves the transfer exit by more than its own size"),
        xaxis_title="Local cap minus Wohngeld fallback (EUR per month)",
        yaxis_title="Change in gross income at transfer exit (EUR per month)",
        updatemenus=[
            {
                "buttons": [
                    {
                        "label": MODEL_HOUSEHOLDS[key].label,
                        "method": "update",
                        "args": [
                            {
                                "visible": [other == key for other in households]
                                + [True],
                            },
                        ],
                    }
                    for key in households
                ],
                "direction": "down",
                "showactive": True,
                "x": 0.0,
                "xanchor": "left",
                "y": 1.12,
                "yanchor": "top",
            },
        ],
    )
    return figure


def _evaluate_on_income_ladder(
    pairs: pd.DataFrame,
    household_key: str,
    actual_bruttokaltmiete: NDArray[np.float64],
    heizkosten: float,
    incomes: NDArray[np.float64],
) -> pd.DataFrame:
    """Evaluate both scenarios at every income point, asserting monotonicity."""
    n_incomes = len(incomes)
    repeated = pairs.loc[pairs.index.repeat(n_incomes)].reset_index(drop=True)
    rent = np.repeat(np.asarray(actual_bruttokaltmiete, dtype=float), n_incomes)
    income = np.tile(np.asarray(incomes, dtype=float), len(pairs))
    results = evaluate(
        build_cases(
            pairs=repeated,
            household_key=household_key,
            actual_bruttokaltmiete=rent,
            heizkosten=heizkosten,
            gross_income=income,
        ),
    )
    _fail_if_anspruch_is_not_monotone(results, len(pairs), n_incomes)
    return results


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
def _gross_pension_per_entgeltpunkt() -> float:
    """Monthly gross Altersrente corresponding to one Entgeltpunkt.

    The income sequence for the Rentnerhaushalt varies the gross pension, but
    GETTSIM takes Entgeltpunkte. The pension is linear in Entgeltpunkte at a
    fixed Zugangsfaktor, so one GETTSIM call at a single Entgeltpunkt inverts
    the relation exactly.
    """
    household = MODEL_HOUSEHOLDS["pensioner_70"]
    age = household.members[0].age
    row = dict(_input_template())
    row.update(_demographics(age=age))
    row.update(_pension_inputs(entgeltpunkte=1.0, age=age))
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
    result = _run_gettsim_with_pension(pd.DataFrame([row]))
    return float(result["rente"].iloc[0])


def _demographics(age: int) -> dict[str, Any]:
    """Age inputs for a person of `age` completed years at the Analysestichtag.

    `alter` and `alter_monate` are ordinary input columns: GETTSIM does not
    derive them from `geburtsjahr`, and leaving them at their zero default makes
    every adult a newborn without any error being raised.
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
    """Pension inputs placing the household at the Regelaltersgrenze."""
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

    is_child = np.array([member.role is MemberRole.CHILD for member in members])[slot]
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
        cases["heizkosten"].to_numpy(dtype=float),
        n_members,
    )
    frame["wohnen__bruttokaltmiete_m_hh"] = np.repeat(
        cases["actual_bruttokaltmiete"].to_numpy(dtype=float),
        n_members,
    )
    frame["bürgergeld__bezug_im_vorjahr"] = household.karenzzeit_elapsed
    frame[GETTSIM_UNTERKUNFTSKOSTEN_COLUMN] = kopfteil_eur_per_month(
        np.repeat(cases["unterkunftskosten"].to_numpy(dtype=float), n_members),
        np.full(total, household.household_size),
    )

    income = np.repeat(cases["gross_income"].to_numpy(dtype=float), n_members)
    _assign_income(frame, household, slot, income, is_pensioner)

    frame["case_id"] = np.repeat(cases["case_id"].to_numpy(), n_members)
    return frame


def _steuerklasse(household: Any, is_child: NDArray[np.bool_]) -> NDArray[np.int_]:  # noqa: ANN401
    """Lohnsteuerklasse: I single, II Alleinerziehend, IV and IV for a couple."""
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
    """Set the Ehepartner, Einstandspartner, Elternteil and Kindergeld links."""
    first_adult = household_base
    if household.n_adults == N_ADULTS_IN_COUPLE:
        partner_slot = np.where(slot == 0, 1, 0)
        partner_id = household_base + partner_slot
        frame["familie__p_id_ehepartner"] = np.where(is_child, -1, partner_id)
        frame["bürgergeld__p_id_einstandspartner"] = np.where(is_child, -1, partner_id)
    frame["familie__p_id_elternteil_1"] = np.where(is_child, first_adult, -1)
    if household.n_adults == N_ADULTS_IN_COUPLE:
        frame["familie__p_id_elternteil_2"] = np.where(is_child, household_base + 1, -1)
    frame["kindergeld__p_id_empfänger"] = np.where(is_child, first_adult, -1)


def _assign_income(
    frame: pd.DataFrame,
    household: Any,  # noqa: ANN401
    slot: NDArray[np.int_],
    income: NDArray[np.float64],
    is_pensioner: NDArray[np.bool_],
) -> None:
    """Put the income on the household's earner or on its pensioner.

    Earnings go to the first adult alone. A single-earner couple is the case in
    which the Erwerbstätigenfreibetrag of § 11b SGB II is claimed once rather
    than twice; splitting earnings across a couple is a separate scenario rather
    than a default that should be adopted without saying so.
    """
    if not household.has_earnings:
        entgeltpunkte = income / _gross_pension_per_entgeltpunkt()
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


def _run_gettsim_with_pension(persons: pd.DataFrame) -> pd.DataFrame:
    """One GETTSIM call that additionally returns the Altersrente."""
    targets = dict(_TT_TARGETS)
    targets["sozialversicherung"] = {
        "rente": {"altersrente": {"betrag_m": "rente"}},
    }
    return main(  # ty: ignore[invalid-return-type]
        main_target=MainTarget.results.df_with_mapper,
        policy_date_str=POLICY_DATE,
        input_data=InputData.df_with_qname_columns(persons),
        tt_targets=TTTargets(tree=targets),  # ty: ignore[unknown-argument]
    )


def _aggregate_to_case(raw: pd.DataFrame) -> pd.DataFrame:
    """Collapse person rows to one row per case, respecting each output's level."""
    by_case = raw.groupby("case_id", sort=True)
    aggregated = by_case[list(_PERSON_LEVEL_OUTPUTS)].sum()
    for column in _GROUP_LEVEL_OUTPUTS:
        aggregated[column] = by_case[column].first()
    return aggregated.reset_index()


def _derive_outcomes(joined: pd.DataFrame) -> pd.DataFrame:
    """Add the outcome columns and apply the central rounding rule."""
    anspruch = round_currency(
        joined["buergergeld_anspruch"] + joined["grundsicherung_anspruch"],
    )
    sgb_betrag = round_currency(
        joined["buergergeld_betrag"] + joined["grundsicherung_betrag"],
    )
    return joined.assign(
        anspruch=anspruch,
        sgb_betrag=sgb_betrag,
        anerkannte_unterkunftskosten=round_currency(
            joined["anerkannte_unterkunftskosten"],
        ),
        regelsatz=round_currency(joined["regelsatz"]),
        wohngeld=round_currency(joined["wohngeld"]),
        kinderzuschlag=round_currency(joined["kinderzuschlag"]),
        kindergeld=round_currency(joined["kindergeld"]),
        receives_sgb=sgb_betrag > 0.0,
    ).drop(
        columns=[
            "buergergeld_anspruch",
            "buergergeld_betrag",
            "grundsicherung_anspruch",
            "grundsicherung_betrag",
        ],
    )


def _anspruch_matrix(
    results: pd.DataFrame,
    scenario: str,  # noqa: ARG001  read by query()
    n_pairs: int,
    n_incomes: int,
) -> NDArray[np.float64]:
    """Reshape one scenario's results into a cap-pair by income matrix."""
    ordered = results.query("scenario == @scenario").sort_values(
        ["cap_pair_id", "gross_income"],
    )
    return ordered["anspruch"].to_numpy(dtype=float).reshape(n_pairs, n_incomes)


def _bracket_from_ladder(
    claims: NDArray[np.float64],
    ladder: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return the last income with a claim and the first without, per cap pair."""
    exhausted = claims <= 0.0
    first_zero = np.argmax(exhausted, axis=1)
    lower = np.where(first_zero == 0, 0.0, ladder[np.maximum(first_zero - 1, 0)])
    return lower, ladder[first_zero]


def _bisect(
    pairs: pd.DataFrame,
    household_key: str,
    actual_bruttokaltmiete: NDArray[np.float64],
    heizkosten: float,
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
        claims = (
            evaluate(
                build_cases(
                    pairs=pairs,
                    household_key=household_key,
                    actual_bruttokaltmiete=actual_bruttokaltmiete,
                    heizkosten=heizkosten,
                    gross_income=midpoint,
                ),
            )
            .query("scenario == @scenario")
            .sort_values("cap_pair_id")["anspruch"]
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


def _fail_if_join_duplicated_rows(
    joined: pd.DataFrame,
    expected: int,
    name: str,
) -> None:
    if len(joined) != expected:
        msg = (
            f"{name} changed the row count from {expected} to {len(joined)}; "
            f"the join key is not unique on the right-hand frame"
        )
        raise ValueError(msg)


def _fail_if_not_finite(results: pd.DataFrame) -> None:
    """GETTSIM's benign 0/0 for a zero-income household must not propagate."""
    numeric = results.select_dtypes("number")
    finite = np.isfinite(numeric.to_numpy(dtype=float))
    if not finite.all():
        offending = numeric.columns[~finite.all(axis=0)].tolist()
        msg = (
            f"simulated results are not finite in columns {offending}; "
            f"GETTSIM's 0/0 for zero-income households must not have propagated"
        )
        raise ValueError(msg)


def _fail_if_anspruch_is_not_monotone(
    results: pd.DataFrame,
    n_pairs: int,
    n_incomes: int,
) -> None:
    """Monotonicity in income is checked, never assumed."""
    for scenario in SCENARIOS:
        claims = _anspruch_matrix(results, scenario, n_pairs, n_incomes)
        for row in range(n_pairs):
            fail_if_not_weakly_decreasing(
                claims[row],
                name=f"anspruch (scenario {scenario}, cap pair {row})",
            )


def _fail_if_a_claim_survives_the_ceiling(
    claims: NDArray[np.float64],
    scenario: str,
    ceiling: float,
) -> None:
    surviving = int((claims[:, -1] > 0.0).sum())
    if surviving:
        msg = (
            f"{surviving} cap pairs still hold an SGB claim at the technical "
            f"income ceiling of {ceiling} EUR in scenario {scenario}, so the "
            f"exit threshold is not bracketed"
        )
        raise ValueError(msg)


__all__ = [
    "CASE_COLUMNS",
    "INCOME_LADDER_POINTS",
    "POLICY_DATE",
    "SCENARIOS",
    "SCENARIO_FALLBACK",
    "SCENARIO_LOCAL_CAP",
    "HeatingAssumption",
    "assign_cap_pairs",
    "build_cases",
    "distinct_cap_pairs",
    "evaluate",
    "exit_threshold_by_gemeinde",
    "exit_threshold_eur_per_month",
    "national_heizkosten_eur_per_month",
    "plot_exit_threshold_distribution",
    "summarise_exit_thresholds",
    "wohnflaeche_sqm",
]
