"""What GETTSIM's own national housing rule recognises, computed by GETTSIM.

Every other module in this package hands GETTSIM a finished housing amount and
so prunes GETTSIM's own rule out of the taxes-and-transfers graph. This module
does the opposite: it supplies the inputs that rule needs —
`wohnen__bruttokaltmiete_m_hh`, `wohnen__heizkosten_m_hh`,
`wohnen__wohnfläche_hh`, `wohnen__bewohnt_eigentum_hh` and
`bürgergeld__bezug_im_vorjahr` — and lets GETTSIM apply its national parameters.

The coupling is deliberate here and is the point of the exercise. Elsewhere the
rule is kept local so that a GETTSIM release cannot silently change what the
project measures; here GETTSIM itself is the object of measurement, so the
installed release is recorded alongside every number this module produces.

What GETTSIM recognises is a warm amount, so the two regimes it is compared
against are put on the same warm footing by adding the same Heizkosten to the
capped Bruttokaltmiete. Heating is identical across all three regimes and
therefore never drives a difference between them.

This module exports:

- `gettsim_recognised_warm_eur_per_month` — GETTSIM's own recognised amount
- `compare_separate_caps_to_monthly_ceiling` — one dwelling under GETTSIM's two
  separate caps and under a single monthly Bruttokaltmiete ceiling
- `modal_admissible_area_sqm` and `median_local_cap_eur_per_month` — the two
  assumptions, read off the collected Richtlinien rather than asserted
- `build_housing_assumptions` — the assumed dwelling, one per household size
- `compare_recognised_housing_costs` and `gettsim_comparison_table` — the
  reported result
- `gettsim_version` — the release the result was taken from

All amounts are euro per month at the household level.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import version
from types import MappingProxyType

import numpy as np
import pandas as pd
from gettsim import InputData, MainTarget, TTTargets, main
from numpy.typing import NDArray

from kdu.config import ANALYSIS_DATE, MODEL_HOUSEHOLDS
from kdu.eligibility.microsimulation import HeatingAssumption
from kdu.eligibility.recognised_housing_costs import round_currency, round_ratio

# The Rechtsstand every GETTSIM call in this module is evaluated at.
POLICY_DATE = ANALYSIS_DATE.isoformat()

# The single GETTSIM target this module asks for. Requesting it and nothing else
# keeps the required input set down to the five housing columns and the two
# identifiers, so no unrelated assumption can reach the result.
GETTSIM_TARGETS: dict[str, dict[str, str]] = {
    "bürgergeld": {"kosten_der_unterkunft_m": "kosten_der_unterkunft_m"},
}

# Whether the household drew Bürgergeld in the previous year.
#
# `bürgergeld.kosten_der_unterkunft_m` branches on this input, and the two
# branches are different rules rather than two values of one rule: with `False`
# GETTSIM recognises the actual warm rent in full and applies no housing cap at
# all, so no comparison against a cap is defined. `True` selects the capped
# branch, which is the rule this project measures, and it is the standing state
# of a household that has been in the transfer system for more than a year.
BEZUG_IM_VORJAHR = True

# Whether the household owns the dwelling it lives in.
#
# `berechtigte_wohnfläche` reads a different admissible-area table for owners.
# The collected Richtlinien and the Wohngeld fallback alike set caps on rent,
# so the comparison is defined for tenants and the owner branch is excluded
# deliberately rather than left to a default.
BEWOHNT_EIGENTUM = False

# GETTSIM's national ceiling on the warm rent per square metre, in euro per
# square metre and month, as `bürgergeld/kosten_der_unterkunft.yaml` sets it
# from 2023. Held here so the reference arithmetic in the tests and the
# documented rule do not have to reach into the installed package.
GETTSIM_MIETOBERGRENZE_EUR_PER_SQM = 10.0

# GETTSIM's national admissible rented area for the first person, in square
# metres, and the increment for each further person.
GETTSIM_BERECHTIGTE_WOHNFLAECHE_BASE_SQM = 45.0
GETTSIM_BERECHTIGTE_WOHNFLAECHE_PER_FURTHER_PERSON_SQM = 15.0

# The small expensive dwelling that separates the two functional forms.
#
# A single adult in 30 square metres at 390 euro Bruttokaltmiete and 60 euro
# Heizkosten. The area is below what GETTSIM admits and the warm rent per square
# metre is above what it allows, so exactly one of GETTSIM's two separate caps
# binds while the monthly Bruttokaltmiete ceiling of the median Gemeinde does
# not bind at all. The dwelling is chosen to make that difference visible; it is
# an illustration and not an observation from any of the collected Richtlinien.
ILLUSTRATIVE_DWELLING_WOHNFLAECHE_SQM = 30.0
ILLUSTRATIVE_DWELLING_BRUTTOKALTMIETE_EUR_PER_MONTH = 390.0
ILLUSTRATIVE_DWELLING_HEIZKOSTEN_EUR_PER_MONTH = 60.0


@dataclass(frozen=True)
class HousingAssumption:
    """The dwelling a Modellhaushalt of a given size is assumed to occupy.

    The same dwelling is put through all three regimes, so a difference between
    them is a difference in the rule and never in the household.
    """

    household_size: int
    """Number of persons in the household."""
    actual_bruttokaltmiete_m: float
    """Assumed actual Bruttokaltmiete, the median local cap at this size.

    A household at the median local cap is the one the collected Richtlinien
    describe as just affordable, so it is the rent at which the three regimes
    are most nearly comparable. It is an assumption, not an observation: the
    project has no Gemeinde-level distribution of actual rents paid by
    Bedarfsgemeinschaften.
    """
    wohnflaeche_sqm: float
    """Assumed actual Wohnfläche, the modal admissible area in the Richtlinien.

    The area a household actually occupies is unobserved, so the most frequently
    published admissible area stands in for it. At household size one that is
    50 square metres against GETTSIM's 45.
    """
    heizkosten_m: float
    """Recognised Heizkosten, from the Wohnkostenstatistik of the Bundesagentur."""


@dataclass(frozen=True)
class SeparateCapsComparison:
    """One dwelling under two functional forms, component by component.

    GETTSIM caps an area and a warm price per square metre separately and
    multiplies the two capped factors; a Richtlinie caps one monthly
    Bruttokaltmiete and assesses Heizkosten beside it. The two are different
    functions of the same dwelling, and the components are kept apart here
    because merging them into a single euro figure would hide the very
    separation the comparison is about.

    All amounts are euro per month at the household level.
    """

    wohnflaeche_sqm: float
    """Wohnfläche of the dwelling, square metres."""
    bruttokaltmiete_m: float
    """Actual Bruttokaltmiete."""
    heizkosten_m: float
    """Actual Heizkosten."""
    warmmiete_m: float
    """Actual warm rent, the sum of Bruttokaltmiete and Heizkosten."""
    warmmiete_je_qm_m: float
    """Actual warm rent per square metre, euro per square metre and month."""
    gettsim_admissible_wohnflaeche_sqm: float
    """The area GETTSIM admits for a household of this size, square metres."""
    gettsim_price_ceiling_eur_per_sqm: float
    """GETTSIM's ceiling on the warm rent per square metre."""
    gettsim_area_cap_binds: bool
    """Whether the admissible area is below the area actually occupied."""
    gettsim_price_ceiling_binds: bool
    """Whether the actual warm rent per square metre exceeds the ceiling."""
    gettsim_recognised_warm_m: float
    """What GETTSIM recognises, a warm amount with Heizkosten inside it.

    Computed by GETTSIM itself rather than by transcribing its formula.
    """
    local_bruttokaltmiete_cap_m: float
    """The monthly Bruttokaltmiete ceiling the dwelling is held against."""
    local_recognised_bruttokaltmiete_m: float
    """The Bruttokaltmiete recognised under that ceiling."""
    local_recognised_heizkosten_m: float
    """The Heizkosten recognised beside it, assessed on their own."""
    gettsim_version: str
    """The GETTSIM release `gettsim_recognised_warm_m` was taken from."""


def compare_separate_caps_to_monthly_ceiling(
    wohnflaeche_sqm: float,
    bruttokaltmiete_m: float,
    heizkosten_m: float,
    local_bruttokaltmiete_cap_m: float,
) -> SeparateCapsComparison:
    """Put one dwelling through GETTSIM's rule and through a monthly ceiling.

    GETTSIM's side is computed by calling GETTSIM, so the figure is the
    installed release's own and moves with it. The Richtlinie side applies the
    monthly Bruttokaltmiete ceiling to the Bruttokaltmiete alone and leaves the
    Heizkosten beside it, which is how a Träger assesses them.

    The two sides are therefore not two levels of one quantity: GETTSIM's is a
    single warm amount, the Richtlinie's is a recognised cold amount plus a
    separately recognised heating amount. They are reported as such.

    Args:
        wohnflaeche_sqm: Wohnfläche of the dwelling, square metres.
        bruttokaltmiete_m: Actual Bruttokaltmiete, euro per month.
        heizkosten_m: Actual Heizkosten, euro per month.
        local_bruttokaltmiete_cap_m: The monthly Bruttokaltmiete ceiling, euro
            per month.

    Returns:
        The components of both sides for a one-person household.

    Raises:
        ValueError: If any input is not finite and positive.

    """
    _fail_if_dwelling_is_not_usable(
        wohnflaeche_sqm=wohnflaeche_sqm,
        bruttokaltmiete_m=bruttokaltmiete_m,
        heizkosten_m=heizkosten_m,
        local_bruttokaltmiete_cap_m=local_bruttokaltmiete_cap_m,
    )
    warmmiete_m = bruttokaltmiete_m + heizkosten_m
    warmmiete_je_qm_m = warmmiete_m / wohnflaeche_sqm
    recognised = gettsim_recognised_warm_eur_per_month(
        household_sizes=np.array([1]),
        bruttokaltmiete=np.array([bruttokaltmiete_m]),
        heizkosten=np.array([heizkosten_m]),
        wohnflaeche=np.array([wohnflaeche_sqm]),
    )
    return SeparateCapsComparison(
        wohnflaeche_sqm=wohnflaeche_sqm,
        bruttokaltmiete_m=bruttokaltmiete_m,
        heizkosten_m=heizkosten_m,
        warmmiete_m=warmmiete_m,
        warmmiete_je_qm_m=float(round_currency(warmmiete_je_qm_m)),
        gettsim_admissible_wohnflaeche_sqm=GETTSIM_BERECHTIGTE_WOHNFLAECHE_BASE_SQM,
        gettsim_price_ceiling_eur_per_sqm=GETTSIM_MIETOBERGRENZE_EUR_PER_SQM,
        gettsim_area_cap_binds=bool(
            wohnflaeche_sqm > GETTSIM_BERECHTIGTE_WOHNFLAECHE_BASE_SQM,
        ),
        gettsim_price_ceiling_binds=bool(
            warmmiete_je_qm_m > GETTSIM_MIETOBERGRENZE_EUR_PER_SQM,
        ),
        gettsim_recognised_warm_m=float(round_currency(recognised[0])),
        local_bruttokaltmiete_cap_m=local_bruttokaltmiete_cap_m,
        local_recognised_bruttokaltmiete_m=float(
            round_currency(min(bruttokaltmiete_m, local_bruttokaltmiete_cap_m)),
        ),
        local_recognised_heizkosten_m=float(round_currency(heizkosten_m)),
        gettsim_version=gettsim_version(),
    )


def gettsim_recognised_warm_eur_per_month(
    household_sizes: NDArray[np.int_],
    bruttokaltmiete: NDArray[np.float64],
    heizkosten: NDArray[np.float64],
    wohnflaeche: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Return what GETTSIM's own rule recognises, per household.

    GETTSIM's recognised housing cost is a person-level column, so one input row
    per person is built and the person-level amounts are summed back to the
    household.

    Args:
        household_sizes: Number of persons, one entry per household.
        bruttokaltmiete: Actual household Bruttokaltmiete, euro per month.
        heizkosten: Actual household Heizkosten, euro per month.
        wohnflaeche: Actual household Wohnfläche, square metres.

    Returns:
        The recognised warm housing cost per household, euro per month, in the
        order the inputs were given.

    Raises:
        ValueError: If the inputs differ in length, or if any household size is
            below one or any area is not positive.

    """
    _fail_if_inputs_are_inconsistent(
        household_sizes=household_sizes,
        bruttokaltmiete=bruttokaltmiete,
        heizkosten=heizkosten,
        wohnflaeche=wohnflaeche,
    )
    sizes = np.asarray(household_sizes, dtype=int)
    household_index = np.repeat(np.arange(len(sizes)), sizes)
    persons = pd.DataFrame(
        {
            "p_id": np.arange(len(household_index)),
            "hh_id": household_index,
            "bürgergeld__bezug_im_vorjahr": BEZUG_IM_VORJAHR,
            "wohnen__bewohnt_eigentum_hh": BEWOHNT_EIGENTUM,
            "wohnen__bruttokaltmiete_m_hh": np.asarray(bruttokaltmiete, dtype=float)[
                household_index
            ],
            "wohnen__heizkosten_m_hh": np.asarray(heizkosten, dtype=float)[
                household_index
            ],
            "wohnen__wohnfläche_hh": np.asarray(wohnflaeche, dtype=float)[
                household_index
            ],
        },
    )
    per_person = main(
        main_target=MainTarget.results.df_with_mapper,
        policy_date_str=POLICY_DATE,
        input_data=InputData.df_with_qname_columns(persons),
        tt_targets=TTTargets(tree=GETTSIM_TARGETS),  # ty: ignore[unknown-argument]
    )
    per_household = (
        pd.Series(
            per_person["kosten_der_unterkunft_m"].to_numpy(dtype=float),
            index=household_index,
        )
        .groupby(level=0)
        .sum()
    )
    return per_household.to_numpy(dtype=float)


def modal_admissible_area_sqm(caps: pd.DataFrame, household_size: int) -> float:
    """Return the most frequently published admissible area at `household_size`.

    Args:
        caps: The cleaned cap table, carrying `household_size` and
            `max_area_sqm`.
        household_size: The household size to read.

    Returns:
        The modal admissible Wohnfläche in square metres.

    Raises:
        ValueError: If no Richtlinie publishes an area at that household size.

    """
    areas = caps.loc[caps["household_size"] == household_size, "max_area_sqm"].dropna()
    if areas.empty:
        msg = f"no admissible area is published at household size {household_size}"
        raise ValueError(msg)
    return float(areas.astype(float).mode().iloc[0])


def median_local_cap_eur_per_month(caps: pd.DataFrame, household_size: int) -> float:
    """Return the median local Bruttokaltmiete cap at `household_size`.

    Every Gemeinde counts once, so this is the median of the administrative
    landscape rather than of the claimant population.

    Args:
        caps: The cleaned cap table, carrying `household_size` and `kdu_cap`.
        household_size: The household size to read.

    Returns:
        The median cap in euro per month.

    Raises:
        ValueError: If no Gemeinde publishes a cap at that household size.

    """
    values = caps.loc[caps["household_size"] == household_size, "kdu_cap"].dropna()
    if values.empty:
        msg = f"no local cap is published at household size {household_size}"
        raise ValueError(msg)
    return float(round_currency(values.astype(float).median()))


def build_housing_assumptions(
    caps: pd.DataFrame,
    heizkosten_per_household_size: Mapping[int, float],
    household_sizes: Sequence[int],
) -> MappingProxyType[int, HousingAssumption]:
    """Assemble the assumed dwelling for every household size.

    Args:
        caps: The cleaned cap table.
        heizkosten_per_household_size: Recognised Heizkosten by household size.
        household_sizes: The household sizes to build an assumption for.

    Returns:
        One `HousingAssumption` per household size.

    """
    return MappingProxyType(
        {
            size: HousingAssumption(
                household_size=size,
                actual_bruttokaltmiete_m=median_local_cap_eur_per_month(caps, size),
                wohnflaeche_sqm=modal_admissible_area_sqm(caps, size),
                heizkosten_m=float(heizkosten_per_household_size[size]),
            )
            for size in household_sizes
        },
    )


def compare_recognised_housing_costs(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    heizkosten_per_household_size: Mapping[int, float],
    household_sizes: Sequence[int],
) -> pd.DataFrame:
    """Recognised warm housing cost under the three regimes, per household size.

    The same household — same actual Bruttokaltmiete, same Wohnfläche, same
    Heizkosten — is put through GETTSIM's national rule, through the local KdU
    cap of each Gemeinde, and through the Wohngeld fallback of each Gemeinde.
    GETTSIM's rule is national and yields one number; the other two are
    distributions over Gemeinden and are reported by their deciles and median.

    Args:
        caps: The cleaned cap table, keyed `ags` by `household_size`.
        fallback: The Wohngeld fallback, keyed `ags` by `household_size`.
        heizkosten_per_household_size: Recognised Heizkosten by household size.
        household_sizes: The household sizes to compare.

    Returns:
        One row per household size, with the assumptions, the three regimes, the
        share of Gemeinden recognising more than GETTSIM does, and the GETTSIM
        release the comparison was computed under.

    """
    assumptions = build_housing_assumptions(
        caps=caps,
        heizkosten_per_household_size=heizkosten_per_household_size,
        household_sizes=household_sizes,
    )
    ordered = tuple(assumptions[size] for size in household_sizes)
    gettsim_warm = round_currency(
        gettsim_recognised_warm_eur_per_month(
            household_sizes=np.array([a.household_size for a in ordered]),
            bruttokaltmiete=np.array([a.actual_bruttokaltmiete_m for a in ordered]),
            heizkosten=np.array([a.heizkosten_m for a in ordered]),
            wohnflaeche=np.array([a.wohnflaeche_sqm for a in ordered]),
        ),
    )
    installed = gettsim_version()
    rows = [
        _compare_one_household_size(
            caps=caps,
            fallback=fallback,
            assumption=assumption,
            gettsim_recognised_warm_m=float(gettsim_warm[position]),
            gettsim_release=installed,
        )
        for position, assumption in enumerate(ordered)
    ]
    return pd.DataFrame(rows)


def gettsim_comparison_table(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    heating: HeatingAssumption,
) -> pd.DataFrame:
    """Compare the three regimes at every size a Modellhaushalt occurs at.

    GETTSIM's housing rule reads the household size and nothing else about who
    the members are, so two Modellhaushalte of the same size receive the same
    recognised amount. Reporting one row per size rather than one per
    Modellhaushalt states that, and `model_household_keys` names the
    Modellhaushalte each row covers.

    Args:
        caps: The cleaned cap table, keyed `ags` by `household_size`.
        fallback: The Wohngeld fallback, keyed `ags` by `household_size`.
        heating: The heating assumption from the Wohnkostenstatistik.

    Returns:
        The comparison, one row per household size, ascending.

    """
    keys_by_size: dict[int, list[str]] = {}
    for key, household in MODEL_HOUSEHOLDS.items():
        keys_by_size.setdefault(household.household_size, []).append(key)
    sizes = tuple(sorted(keys_by_size))
    comparison = compare_recognised_housing_costs(
        caps=caps,
        fallback=fallback,
        heizkosten_per_household_size=heating.per_household_size,
        household_sizes=sizes,
    )
    return comparison.assign(
        model_household_keys=[" | ".join(sorted(keys_by_size[size])) for size in sizes],
    )


def gettsim_version() -> str:
    """Return the installed GETTSIM release.

    This result measures GETTSIM rather than the law, and a release may change
    the national parameters or the rule itself, so the version is part of the
    result and travels with it into `bld/`.
    """
    return version("gettsim")


def _compare_one_household_size(
    caps: pd.DataFrame,
    fallback: pd.DataFrame,
    assumption: HousingAssumption,
    gettsim_recognised_warm_m: float,
    gettsim_release: str,
) -> dict[str, float | int | str]:
    """Build the reported row for one household size."""
    size = assumption.household_size
    local = caps.loc[caps["household_size"] == size, ["ags", "kdu_cap"]].dropna()
    statutory = fallback.loc[
        fallback["household_size"] == size,
        ["ags", "wohngeld_fallback_cap"],
    ].dropna()
    joined = local.merge(statutory, on="ags", how="inner", validate="one_to_one")
    rent = assumption.actual_bruttokaltmiete_m
    heating = assumption.heizkosten_m
    local_warm = np.minimum(joined["kdu_cap"].to_numpy(dtype=float), rent) + heating
    fallback_warm = (
        np.minimum(joined["wohngeld_fallback_cap"].to_numpy(dtype=float), rent)
        + heating
    )
    return {
        "household_size": size,
        "actual_bruttokaltmiete_m": rent,
        "wohnflaeche_sqm": assumption.wohnflaeche_sqm,
        "heizkosten_m": heating,
        "n_gemeinden": len(joined),
        "gettsim_recognised_warm_m": gettsim_recognised_warm_m,
        "gettsim_recognised_bruttokaltmiete_m": float(
            round_currency(gettsim_recognised_warm_m - heating),
        ),
        "local_cap_recognised_warm_m_p10": float(
            round_currency(np.quantile(local_warm, 0.10)),
        ),
        "local_cap_recognised_warm_m_median": float(
            round_currency(np.median(local_warm)),
        ),
        "local_cap_recognised_warm_m_p90": float(
            round_currency(np.quantile(local_warm, 0.90)),
        ),
        "fallback_recognised_warm_m_median": float(
            round_currency(np.median(fallback_warm)),
        ),
        "gettsim_minus_local_cap_median_m": float(
            round_currency(gettsim_recognised_warm_m - np.median(local_warm)),
        ),
        "share_of_gemeinden_above_gettsim": float(
            round_ratio(np.mean(local_warm > gettsim_recognised_warm_m)),
        ),
        "gettsim_version": gettsim_release,
    }


def _fail_if_dwelling_is_not_usable(
    wohnflaeche_sqm: float,
    bruttokaltmiete_m: float,
    heizkosten_m: float,
    local_bruttokaltmiete_cap_m: float,
) -> None:
    """Reject a dwelling whose numbers cannot carry the comparison."""
    for name, value in (
        ("wohnflaeche_sqm", wohnflaeche_sqm),
        ("bruttokaltmiete_m", bruttokaltmiete_m),
        ("heizkosten_m", heizkosten_m),
        ("local_bruttokaltmiete_cap_m", local_bruttokaltmiete_cap_m),
    ):
        if not np.isfinite(value) or value <= 0.0:
            msg = f"{name} must be finite and positive, got {value}"
            raise ValueError(msg)


def _fail_if_inputs_are_inconsistent(
    household_sizes: NDArray[np.int_],
    bruttokaltmiete: NDArray[np.float64],
    heizkosten: NDArray[np.float64],
    wohnflaeche: NDArray[np.float64],
) -> None:
    lengths = {
        len(household_sizes),
        len(bruttokaltmiete),
        len(heizkosten),
        len(wohnflaeche),
    }
    if len(lengths) != 1:
        msg = (
            f"household_sizes, bruttokaltmiete, heizkosten and wohnflaeche must "
            f"have the same length, got lengths {sorted(lengths)}"
        )
        raise ValueError(msg)
    if np.any(np.asarray(household_sizes) < 1):
        msg = f"household_sizes must be at least 1, got {household_sizes}"
        raise ValueError(msg)
    if np.any(np.asarray(wohnflaeche, dtype=float) <= 0.0):
        msg = f"wohnflaeche must be positive, got {wohnflaeche}"
        raise ValueError(msg)
    for name, values in (
        ("bruttokaltmiete", bruttokaltmiete),
        ("heizkosten", heizkosten),
    ):
        array = np.asarray(values, dtype=float)
        if not np.all(np.isfinite(array)) or np.any(array < 0.0):
            msg = f"{name} must be finite and non-negative, got {values}"
            raise ValueError(msg)


__all__ = [
    "BEWOHNT_EIGENTUM",
    "BEZUG_IM_VORJAHR",
    "GETTSIM_BERECHTIGTE_WOHNFLAECHE_BASE_SQM",
    "GETTSIM_BERECHTIGTE_WOHNFLAECHE_PER_FURTHER_PERSON_SQM",
    "GETTSIM_MIETOBERGRENZE_EUR_PER_SQM",
    "ILLUSTRATIVE_DWELLING_BRUTTOKALTMIETE_EUR_PER_MONTH",
    "ILLUSTRATIVE_DWELLING_HEIZKOSTEN_EUR_PER_MONTH",
    "ILLUSTRATIVE_DWELLING_WOHNFLAECHE_SQM",
    "POLICY_DATE",
    "HousingAssumption",
    "SeparateCapsComparison",
    "build_housing_assumptions",
    "compare_recognised_housing_costs",
    "compare_separate_caps_to_monthly_ceiling",
    "gettsim_comparison_table",
    "gettsim_recognised_warm_eur_per_month",
    "gettsim_version",
    "median_local_cap_eur_per_month",
    "modal_admissible_area_sqm",
]
