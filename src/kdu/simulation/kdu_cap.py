"""The recognised-housing-cost rule of § 22 Abs. 1 SGB II, owned by this repo.

This module is the whole of the K/W contrast defined in §12.1. It applies
`min(actual rent, cap)` itself and hands GETTSIM a finished amount,
so GETTSIM never gets to apply a housing-cost rule of its own.

That separation is deliberate (D9). GETTSIM carries an approximate national
Angemessenheitsgrenze of its own — `berechtigte_wohnfläche * min(warm rent per m²,
10 €/m²)` — which would silently truncate both scenarios and contaminate the
contrast. `docs/gettsim_audit.md` records how that cap is neutralised. Keeping the
rule here means a GETTSIM release cannot invalidate the finding.

All amounts are euro per month at the Bedarfsgemeinschaft level.
"""

import numpy as np
from numpy.typing import NDArray

# The GETTSIM input column that `unterkunftskosten_m` fills. Supplying it as input
# data replaces GETTSIM's own `bürgergeld.kosten_der_unterkunft_m` policy function,
# which is what neutralises GETTSIM's internal cap. It is a person-level column
# (see `kopfteil_m`) and the single point of coupling to GETTSIM.
GETTSIM_UNTERKUNFTSKOSTEN_COLUMN = "bürgergeld__kosten_der_unterkunft_m"

# Places every euro amount this project reports is rounded to. §12.8 test 8 asks
# for one rounding rule applied centrally, so `round_currency_m` is the only place
# a monetary result is rounded and every module calls it rather than `round`.
CURRENCY_DECIMALS = 2

# Places every share, ratio and hours figure is rounded to. Kept separate from
# `CURRENCY_DECIMALS` because a share of 0.01 is a percentage point, not a cent.
RATIO_DECIMALS = 4


def recognised_bruttokaltmiete_m(
    actual_bruttokaltmiete_m: NDArray[np.float64],
    cap_m: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Apply a Bruttokaltmiete cap to an actual rent.

    Scenario K passes the local KdU-Obergrenze as `cap_m`, scenario W the Wohngeld
    Höchstbetrag. Everything else about the two scenarios is identical, so the
    entire proxy error enters through this argument.

    Args:
        actual_bruttokaltmiete_m: Actual Bruttokaltmiete, euro per month.
        cap_m: The scenario's cap on the Bruttokaltmiete, euro per month.

    Returns:
        The recognised Bruttokaltmiete, euro per month.

    """
    _fail_if_not_a_valid_amount(actual_bruttokaltmiete_m, "actual_bruttokaltmiete_m")
    _fail_if_not_a_valid_amount(cap_m, "cap_m")
    return np.minimum(actual_bruttokaltmiete_m, cap_m)


def unterkunftskosten_m(
    actual_bruttokaltmiete_m: NDArray[np.float64],
    cap_m: NDArray[np.float64],
    heizkosten_m: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Total recognised Bedarf für Unterkunft und Heizung.

    Heating is recognised in full and is held identical across the two scenarios
    (§12.3), so it cancels from every K - W difference and the contrast stays a
    pure Bruttokaltmiete effect.

    Args:
        actual_bruttokaltmiete_m: Actual Bruttokaltmiete, euro per month.
        cap_m: The scenario's cap on the Bruttokaltmiete, euro per month.
        heizkosten_m: Recognised heating costs, euro per month.

    Returns:
        The amount to hand GETTSIM through
        `GETTSIM_UNTERKUNFTSKOSTEN_COLUMN`, euro per month.

    """
    _fail_if_not_a_valid_amount(heizkosten_m, "heizkosten_m")
    return recognised_bruttokaltmiete_m(actual_bruttokaltmiete_m, cap_m) + heizkosten_m


def kopfteil_m(
    household_amount_m: NDArray[np.float64],
    anzahl_personen_hh: NDArray[np.int_],
) -> NDArray[np.float64]:
    """Split a household housing amount into equal per-person shares.

    `GETTSIM_UNTERKUNFTSKOSTEN_COLUMN` is a person-level column: GETTSIM's
    own policy function divides the household rent by household size before
    anything else uses it (Kopfteilprinzip, BSG B 14/7b AS 58/06 R). An override
    that passes the household total instead inflates the Bedarf by a factor of
    household size, which is invisible for a single-person household and wrong
    for every other §11.1 model household.

    Args:
        household_amount_m: Recognised housing amount for the whole household,
            euro per month.
        anzahl_personen_hh: Number of persons in the household.

    Returns:
        The per-person share, euro per month.

    """
    _fail_if_not_a_valid_amount(household_amount_m, "household_amount_m")
    if np.any(anzahl_personen_hh < 1):
        msg = f"anzahl_personen_hh must be at least 1, got {anzahl_personen_hh}"
        raise ValueError(msg)
    return household_amount_m / anzahl_personen_hh


def fail_if_not_weakly_decreasing(
    values: NDArray[np.float64],
    name: str,
    tolerance: float = 1e-6,
) -> None:
    """Assert the monotonicity D10's bisection for `y*` relies on.

    Bisection locates the Transfer-Ausstiegsschwelle exactly only if the Anspruch
    is weakly decreasing in gross income. That is a property of GETTSIM's
    Einkommensanrechnung, not something this project may assume, so every
    bisection checks it against an evaluated ladder rather than trusting it.

    Args:
        values: Anspruch evaluated on an ascending income ladder.
        name: Name of the checked quantity, used in the error message.
        tolerance: Increase treated as rounding noise rather than a violation.

    Raises:
        ValueError: If any step increases by more than `tolerance`.

    """
    increases = np.diff(values) > tolerance
    if increases.any():
        first = int(np.flatnonzero(increases)[0])
        msg = (
            f"{name} is not weakly decreasing, so bisection for y* is invalid. "
            f"First increase at index {first}: "
            f"{values[first]} -> {values[first + 1]}."
        )
        raise ValueError(msg)


def round_currency_m(values: NDArray[np.float64] | float) -> NDArray[np.float64]:
    """Round a euro-per-month amount to whole cents.

    This is the project's single rounding rule for money (§12.8 test 8). Every
    simulated Anspruch, Bedarf and budget-curve value passes through it, so two
    scenarios that differ only in the cap can never differ through rounding, and a
    figure and the table beside it can never disagree in the last digit.

    Args:
        values: Euro-per-month amounts.

    Returns:
        The same amounts rounded to `CURRENCY_DECIMALS` places.

    """
    return np.round(np.asarray(values, dtype=np.float64), CURRENCY_DECIMALS)


def round_ratio(values: NDArray[np.float64] | float) -> NDArray[np.float64]:
    """Round a share, ratio or hours figure to `RATIO_DECIMALS` places."""
    return np.round(np.asarray(values, dtype=np.float64), RATIO_DECIMALS)


def _fail_if_not_a_valid_amount(values: NDArray[np.float64], name: str) -> None:
    if not np.all(np.isfinite(values)):
        msg = f"{name} must be finite, got {values}"
        raise ValueError(msg)
    if np.any(values < 0):
        msg = f"{name} must be non-negative, got {values}"
        raise ValueError(msg)
