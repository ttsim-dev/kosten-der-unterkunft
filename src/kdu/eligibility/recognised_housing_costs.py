"""The recognised-housing-cost rule of § 22 Abs. 1 SGB II, owned by this repo.

This module applies `min(actual rent, cap)` and hands GETTSIM a finished
amount, so GETTSIM never applies a housing-cost rule of its own.

The separation is deliberate. GETTSIM carries an approximate national
Angemessenheitsgrenze — `berechtigte Wohnfläche` times the smaller of the warm
rent per square metre and 10 EUR per square metre — which would truncate both
scenarios alike and leave the contrast between them measuring nothing. Supplying
`GETTSIM_UNTERKUNFTSKOSTEN_COLUMN` as input data prunes that rule out of the
GETTSIM taxes-and-transfers graph. Keeping the rule here also means a GETTSIM
release cannot silently change what the project measures.

All amounts are euro per month at the Bedarfsgemeinschaft level.
"""

import numpy as np
from numpy.typing import NDArray

# The GETTSIM input column that the recognised housing cost fills. Supplying it
# as input data replaces GETTSIM's own `bürgergeld.kosten_der_unterkunft_m`
# policy function. It is a person-level column, so the household amount passes
# through `kopfteil_eur_per_month` first. This is the single point of coupling
# to GETTSIM.
GETTSIM_UNTERKUNFTSKOSTEN_COLUMN = "bürgergeld__kosten_der_unterkunft_m"

# Places every euro amount the project reports is rounded to. This is the only
# place money is rounded, so two scenarios differing only in the cap can never
# differ through rounding alone.
CURRENCY_DECIMALS = 2

# Places every share or ratio is rounded to, kept separate from
# `CURRENCY_DECIMALS` because a share of 0.01 is a percentage point, not a cent.
RATIO_DECIMALS = 4


def recognised_bruttokaltmiete_eur_per_month(
    actual_bruttokaltmiete: NDArray[np.float64],
    cap: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Apply a Bruttokaltmiete cap to an actual rent.

    One scenario passes the local KdU-Obergrenze as `cap`, the other the
    Wohngeld fallback. Every other legal and economic parameter is identical, so
    the whole difference between the two scenarios enters through this argument.

    Args:
        actual_bruttokaltmiete: Actual Bruttokaltmiete, euro per month.
        cap: The scenario's cap on the Bruttokaltmiete, euro per month.

    Returns:
        The recognised Bruttokaltmiete, euro per month.

    """
    _fail_if_not_a_valid_amount(actual_bruttokaltmiete, "actual_bruttokaltmiete")
    _fail_if_not_a_valid_amount(cap, "cap")
    return np.minimum(actual_bruttokaltmiete, cap)


def unterkunftskosten_eur_per_month(
    actual_bruttokaltmiete: NDArray[np.float64],
    cap: NDArray[np.float64],
    heizkosten: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Total recognised Bedarf für Unterkunft und Heizung.

    Heating is recognised in full and held identical across the two scenarios,
    so it cancels from their difference and the contrast stays a pure
    Bruttokaltmiete effect.

    Args:
        actual_bruttokaltmiete: Actual Bruttokaltmiete, euro per month.
        cap: The scenario's cap on the Bruttokaltmiete, euro per month.
        heizkosten: Recognised heating costs, euro per month.

    Returns:
        The amount handed to GETTSIM through
        `GETTSIM_UNTERKUNFTSKOSTEN_COLUMN`, euro per month.

    """
    _fail_if_not_a_valid_amount(heizkosten, "heizkosten")
    return (
        recognised_bruttokaltmiete_eur_per_month(actual_bruttokaltmiete, cap)
        + heizkosten
    )


def kopfteil_eur_per_month(
    household_amount: NDArray[np.float64],
    anzahl_personen: NDArray[np.int_],
) -> NDArray[np.float64]:
    """Split a household housing amount into equal per-person shares.

    `GETTSIM_UNTERKUNFTSKOSTEN_COLUMN` is a person-level column: GETTSIM divides
    the household rent by household size before anything else uses it
    (Kopfteilprinzip, BSG B 14/7b AS 58/06 R). Passing the household total
    instead inflates the Bedarf by a factor of household size, which is
    invisible for a single-person household and wrong for every other one.

    Args:
        household_amount: Recognised housing amount for the whole household,
            euro per month.
        anzahl_personen: Number of persons in the household.

    Returns:
        The per-person share, euro per month.

    """
    _fail_if_not_a_valid_amount(household_amount, "household_amount")
    if np.any(anzahl_personen < 1):
        msg = f"anzahl_personen must be at least 1, got {anzahl_personen}"
        raise ValueError(msg)
    return household_amount / anzahl_personen


def fail_if_not_weakly_decreasing(
    values: NDArray[np.float64],
    name: str,
    tolerance: float = 1e-6,
) -> None:
    """Assert the monotonicity the bisection for the exit threshold relies on.

    Bisection locates the Transfer-Ausstiegsschwelle exactly only if the
    Anspruch is weakly decreasing in gross income. That is a property of
    GETTSIM's Einkommensanrechnung rather than something this project may
    assume, so every bisection checks it against evaluated income points.

    Args:
        values: Anspruch evaluated on an ascending sequence of gross incomes.
        name: Name of the checked quantity, used in the error message.
        tolerance: Increase treated as rounding noise rather than a violation.

    Raises:
        ValueError: If any step increases by more than `tolerance`.

    """
    increases = np.diff(values) > tolerance
    if increases.any():
        first = int(np.flatnonzero(increases)[0])
        msg = (
            f"{name} is not weakly decreasing, so bisection for the exit "
            f"threshold is invalid. First increase at index {first}: "
            f"{values[first]} -> {values[first + 1]}."
        )
        raise ValueError(msg)


def round_currency(values: NDArray[np.float64] | float) -> NDArray[np.float64]:
    """Round a euro-per-month amount to whole cents.

    Args:
        values: Euro-per-month amounts.

    Returns:
        The same amounts rounded to `CURRENCY_DECIMALS` places.

    """
    return np.round(np.asarray(values, dtype=np.float64), CURRENCY_DECIMALS)


def round_ratio(values: NDArray[np.float64] | float) -> NDArray[np.float64]:
    """Round a share or ratio to `RATIO_DECIMALS` places."""
    return np.round(np.asarray(values, dtype=np.float64), RATIO_DECIMALS)


def _fail_if_not_a_valid_amount(values: NDArray[np.float64], name: str) -> None:
    if not np.all(np.isfinite(values)):
        msg = f"{name} must be finite, got {values}"
        raise ValueError(msg)
    if np.any(values < 0):
        msg = f"{name} must be non-negative, got {values}"
        raise ValueError(msg)
