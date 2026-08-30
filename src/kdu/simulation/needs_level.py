"""P0.6 — the regionalised administrative Bruttokaltbedarf of §11.

Regelbedarfe are national. The recognised Bruttokaltmiete is not. Adding the two
together turns a local KdU-Obergrenze into a quantity social policy can read
directly, and shows that a nationally uniform Regelbedarf implies nothing like a
nationally uniform administrative need once the housing component is in.

For model household `c` in Gemeinde `g`, §11.2 defines

```
B^K = R + M + K        B^W = R + M + W
```

with `R` the Regelbedarfe, `M` the standardised Mehrbedarfe, and `K` and `W` the
local KdU-Obergrenze and the Wohngeld Höchstbetrag at the household's size.

**Heating is deliberately outside the measure.** §11.2 and §20 therefore forbid
calling it a full Existenzminimum; the only admissible name is
`NEEDS_MEASURE_LABEL`, and every figure, table and sentence uses that name.

`R` and `M` come from the same GETTSIM version and the same Rechtsstand as the §12
simulation, evaluated with the housing component set to zero, so the two modules
can never drift apart on the Regelbedarf side.
"""

from dataclasses import dataclass
from functools import cache
from types import MappingProxyType

import numpy as np
import pandas as pd

from kdu.config import MODEL_HOUSEHOLDS, WOGG_SAFETY_MARKUP
from kdu.simulation.kdu_cap import round_currency_m, round_ratio
from kdu.simulation.microsim import SCENARIO_KDU, build_cases, evaluate

# The one admissible name for the measure (§11.2, §20). It says "Bruttokaltbedarf"
# because heating is excluded, and "before income offsetting" because it is a
# Bedarf rather than a payment.
NEEDS_MEASURE_LABEL = "administrative Bruttokaltbedarf before income offsetting"

# Columns `administrative_need` returns, in order.
NEED_COLUMNS: tuple[str, ...] = (
    "ags",
    "household_key",
    "household_size",
    "kdu_cap_m",
    "wogg_cap_m",
    "wogg_klima_cap_m",
    "standard_need_m",
    "need_kdu_m",
    "need_wogg_m",
    "need_wogg_klima_m",
    "need_difference_m",
    "kdu_share_of_need",
    "wogg_share_of_need",
)


@dataclass(frozen=True)
class RegelbedarfComponents:
    """The national part of the §11.2 need, split into `R` and `M`."""

    household_key: str
    """Key of the §11.1 Modellhaushalt."""
    regelbedarf_m: float
    """`R`: the Regelbedarfe of every member, euro per month."""
    mehrbedarf_m: float
    """`M`: standardised Mehrbedarfe, euro per month."""

    @property
    def standard_need_m(self) -> float:
        """`R + M`: everything in the measure except the housing component."""
        return round(self.regelbedarf_m + self.mehrbedarf_m, 2)


@cache
def regelbedarf_components() -> MappingProxyType[str, RegelbedarfComponents]:
    """Return `R` and `M` for every §11.1 Modellhaushalt.

    Both are read out of GETTSIM at zero income and zero recognised
    housing cost, so the Regelbedarf side of P0.6 is the same object the P0.7
    simulation uses. The child Regelsätze include the Kindersofortzuschlag, and
    the single-parent Regelsatz includes the § 21 Abs. 3 Mehrbedarf, which the
    split below separates back out.

    Returns:
        A mapping from household key to its `RegelbedarfComponents`.

    """
    cases = pd.concat(
        [_zero_housing_case(key) for key in MODEL_HOUSEHOLDS],
        ignore_index=True,
    )
    # `query` resolves an `@name` from the caller's locals only, so a
    # module-level constant has to be bound here first.
    scenario = SCENARIO_KDU
    results = evaluate(cases.assign(case_id=np.arange(len(cases)))).query(
        "scenario == @scenario",
    )
    totals = dict(zip(results["household_key"], results["regelsatz_m"], strict=True))
    shares = dict(
        zip(results["household_key"], results["mehrbedarfsanteil"], strict=True),
    )
    # GETTSIM raises the adult Regelsatz to `rbs_1 * (1 + anteil)`, so the § 21
    # Abs. 3 Mehrbedarf is that share of Regelbedarfsstufe 1 exactly.
    rbs_1 = float(totals["single_35"])
    components = {}
    for key in MODEL_HOUSEHOLDS:
        mehrbedarf = float(shares[key]) * rbs_1
        components[key] = RegelbedarfComponents(
            household_key=key,
            regelbedarf_m=float(round_currency_m(float(totals[key]) - mehrbedarf)),
            mehrbedarf_m=float(round_currency_m(mehrbedarf)),
        )
    return MappingProxyType(components)


def administrative_need(
    sample: pd.DataFrame,
    household_key: str,
) -> pd.DataFrame:
    """Compute `B^K` and `B^W` per Gemeinde for one §11.1 Modellhaushalt.

    Args:
        sample: The long analysis sample, keyed `ags` by `household_size`.
        household_key: Key of the Modellhaushalt.

    Returns:
        One row per Gemeinde with `NEED_COLUMNS`. Gemeinden with no statutory
        Mietenstufe keep `need_kdu_m` and lose only the Wohngeld columns and the
        difference, because A2 leaves no Wohngeld benchmark to compare against.

    """
    household = MODEL_HOUSEHOLDS[household_key]
    size = household.household_size
    standard_need = regelbedarf_components()[household_key].standard_need_m
    rows = sample.query("household_size == @size")
    kdu_cap = rows["kdu_bkc_cap"].astype("Float64")
    wogg_base_cap = rows["wogg_base_cap"].astype("Float64")
    # `W` is the § 12 WoGG table plus the BSG Sicherheitszuschlag (D15).
    wogg_cap = wogg_base_cap * WOGG_SAFETY_MARKUP
    climate = (
        rows["wogg_climate_component"].astype("Float64")
        if "wogg_climate_component" in rows.columns
        else pd.Series(pd.NA, index=rows.index, dtype="Float64")
    )
    need_kdu = standard_need + kdu_cap
    need_wogg = standard_need + wogg_cap
    frame = pd.DataFrame(
        {
            "ags": rows["ags"].to_numpy(),
            "household_key": household_key,
            "household_size": size,
            "kdu_cap_m": kdu_cap.to_numpy(),
            "wogg_cap_m": wogg_cap.to_numpy(),
            "wogg_klima_cap_m": (wogg_base_cap + climate).to_numpy(),
            "standard_need_m": standard_need,
            "need_kdu_m": need_kdu.to_numpy(),
            "need_wogg_m": need_wogg.to_numpy(),
            "need_wogg_klima_m": (standard_need + wogg_base_cap + climate).to_numpy(),
            "need_difference_m": (need_kdu - need_wogg).to_numpy(),
            "kdu_share_of_need": (kdu_cap / need_kdu).to_numpy(),
            "wogg_share_of_need": (wogg_cap / need_wogg).to_numpy(),
        },
    )
    return frame.loc[:, list(NEED_COLUMNS)]


def summarise_need(need: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    """Report the §11.3 statistics of the administrative Bruttokaltbedarf.

    Args:
        need: Output of `administrative_need`, optionally joined to the
            municipality crosswalk so `by` can name a Bundesland, Mietenstufe or
            Gemeindegrößenklasse column.
        by: Grouping columns; the household alone if omitted.

    Returns:
        One row per group with P10, median and P90 of `B^K` and `B^W`, the
        regional range of `B^K`, the median KdU share `S^K`, and the median
        `B^K − B^W`.

    """
    grouping = ["household_key", *(by or [])]
    grouped = need.groupby(grouping, dropna=False, observed=True)
    summary = grouped.agg(
        n_gemeinden=("ags", "size"),
        n_gemeinden_with_benchmark=("need_wogg_m", "count"),
        need_kdu_p10=("need_kdu_m", lambda values: values.quantile(0.10)),
        need_kdu_median=("need_kdu_m", "median"),
        need_kdu_p90=("need_kdu_m", lambda values: values.quantile(0.90)),
        need_kdu_min=("need_kdu_m", "min"),
        need_kdu_max=("need_kdu_m", "max"),
        need_wogg_p10=("need_wogg_m", lambda values: values.quantile(0.10)),
        need_wogg_median=("need_wogg_m", "median"),
        need_wogg_p90=("need_wogg_m", lambda values: values.quantile(0.90)),
        need_difference_median=("need_difference_m", "median"),
        kdu_share_median=("kdu_share_of_need", "median"),
    ).reset_index()
    summary["need_kdu_range"] = summary["need_kdu_max"] - summary["need_kdu_min"]
    amounts = [
        column
        for column in summary.columns
        if column.startswith(("need_kdu", "need_wogg", "need_difference"))
    ]
    for column in amounts:
        summary[column] = round_currency_m(summary[column].astype(float))
    summary["kdu_share_median"] = round_ratio(
        summary["kdu_share_median"].astype(float),
    )
    return summary


def _zero_housing_case(household_key: str) -> pd.DataFrame:
    """One case for `household_key` at zero income and zero recognised housing."""
    cells = pd.DataFrame(
        {"cell_id": [0], "kdu_cap_m": [0.0], "wogg_cap_m": [0.0], "mietenstufe": [3]},
    )
    return build_cases(
        cells=cells,
        household_key=household_key,
        actual_bruttokaltmiete_m=np.array([0.0]),
        heizkosten_m=0.0,
        gross_income_m=np.array([0.0]),
    )


__all__ = [
    "NEEDS_MEASURE_LABEL",
    "NEED_COLUMNS",
    "RegelbedarfComponents",
    "administrative_need",
    "regelbedarf_components",
    "summarise_need",
]
