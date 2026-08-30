"""P0.7 — run the §12 Standardfall microsimulation and write its result tables.

Everything here is orchestration: which cells, which rent assumption, which
heating figure, which income grid. The simulation itself lives in
`kdu.simulation.microsim`, and the `min(m, cap)` rule that defines the contrast
lives in `kdu.simulation.kdu_cap`.

Four tables come out of it:

- `microsim_cells.parquet` — §12.2 Variante 1 at the central heating assumption,
  one row per simulation cell with every §12.6 and §12.7 outcome
- `microsim_heating_sensitivity.parquet` — the same outcomes at 75 % and 125 % of
  the BA heating figure (§12.3)
- `microsim_rent_grid.parquet` — §12.2 Variante 2, `ΔT(0)` across rents from 50 %
  to 130 % of `max(K, W)`
- `microsim_budget_curves.parquet` — the full income grid for the Gemeinden at the
  P10, median and P90 of the proxy error (§12.8 figure 3)
- `microsim_gemeinde.parquet` — the cell results joined back to every Gemeinde

§12.2 Variante 3, the Bestandsmieten scenario, waits on the Zensus module.
`bestandsmiete_hook` is where it plugs in.
"""

from pathlib import Path
from typing import Annotated

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from pytask import Product

from kdu.config import BLD, INCOME_GRID, MODEL_HOUSEHOLDS, catalog_path
from kdu.simulation.kdu_cap import round_currency_m, round_ratio
from kdu.simulation.microsim import (
    SCENARIO_KDU,
    SCENARIO_WOGG,
    HeatingAssumption,
    assign_cells,
    budget_curve,
    build_cases,
    evaluate,
    exit_threshold_m,
    hours_equivalent,
    national_heating_costs_m,
    rent_grid_factors,
    simulation_cells,
)

# The BA Wohnkosten table §12.3 takes the heating assumption from. It is written
# by `data_management/task_ba.py`, which owns its catalog registration.
BA_WOHNKOSTEN = BLD / "ba_wohnkosten_long.parquet"

# Cells evaluated per GETTSIM call when the whole income grid is attached.
# GETTSIM's runtime is flat in batch size, so this only bounds peak memory.
CELL_CHUNK_SIZE = 120

# Grid points kept beyond the last exit threshold, so §12.4's stopping rule — no
# claim in either scenario for twelve consecutive points — is satisfied exactly.
TRAILING_EMPTY_POINTS = INCOME_GRID.stop_after_consecutive_empty_points

# Quantiles of the proxy error whose Gemeinden get a budget curve (§12.8 fig. 3).
BUDGET_CURVE_QUANTILES: tuple[float, ...] = (0.10, 0.50, 0.90)


def task_microsim(
    analysis_sample: Path = catalog_path("analysis_sample_main"),
    crosswalk: Path = catalog_path("municipality_crosswalk"),
    ba_wohnkosten: Path = BA_WOHNKOSTEN,
    cells_path: Annotated[Path, Product] = BLD / "microsim_cells.parquet",
    heating_path: Annotated[Path, Product] = (
        BLD / "microsim_heating_sensitivity.parquet"
    ),
    rent_grid_path: Annotated[Path, Product] = BLD / "microsim_rent_grid.parquet",
    budget_curve_path: Annotated[Path, Product] = (
        BLD / "microsim_budget_curves.parquet"
    ),
    gemeinde_path: Annotated[Path, Product] = BLD / "microsim_gemeinde.parquet",
) -> None:
    """Simulate both scenarios on D10's cells and join the results back to Gemeinden."""
    sample = pd.read_parquet(analysis_sample)
    municipalities = pd.read_parquet(crosswalk)
    heating = national_heating_costs_m(pd.read_parquet(ba_wohnkosten))

    cells_by_household = {
        key: simulation_cells(sample, household.household_size)
        for key, household in MODEL_HOUSEHOLDS.items()
    }
    cell_results = pd.concat(
        [
            simulate_household(key, cells, heating.for_household(key))
            for key, cells in cells_by_household.items()
        ],
        ignore_index=True,
    )
    cell_results.to_parquet(cells_path, index=False)

    heating_sensitivity(cells_by_household, heating).to_parquet(
        heating_path,
        index=False,
    )
    rent_grid_results(cells_by_household, heating).to_parquet(
        rent_grid_path,
        index=False,
    )
    gemeinde = join_to_gemeinden(
        sample, municipalities, cells_by_household, cell_results
    )
    gemeinde.to_parquet(gemeinde_path, index=False)
    budget_curves(cells_by_household, heating, gemeinde).to_parquet(
        budget_curve_path,
        index=False,
    )


def simulate_household(
    household_key: str,
    cells: pd.DataFrame,
    heizkosten_m: float,
) -> pd.DataFrame:
    """Run §12.2 Variante 1 for one Modellhaushalt and return every §12.6 outcome.

    Variante 1 sets `m = max(K, W)`. That is a **construction scenario** that
    isolates the maximum mechanical difference between the two parameters, not a
    typical market rent: at that rent both caps bind, so the recognised amounts
    are exactly `K` and `W`.
    """
    rent = binding_rent_m(cells)
    zero_income = evaluate(
        build_cases(
            cells=cells,
            household_key=household_key,
            actual_bruttokaltmiete_m=rent,
            heizkosten_m=heizkosten_m,
            gross_income_m=np.zeros(len(cells)),
        ),
    )
    thresholds = exit_threshold_m(
        cells=cells,
        household_key=household_key,
        actual_bruttokaltmiete_m=rent,
        heizkosten_m=heizkosten_m,
    )
    ceiling = float(
        max(thresholds[SCENARIO_KDU].max(), thresholds[SCENARIO_WOGG].max())
        + TRAILING_EMPTY_POINTS * INCOME_GRID.step_eur,
    )
    along_grid = grid_outcomes(
        cells=cells,
        household_key=household_key,
        rent=rent,
        heizkosten_m=heizkosten_m,
        ceiling_m=ceiling,
    )
    delta_y_star = thresholds[SCENARIO_KDU] - thresholds[SCENARIO_WOGG]
    zero = _by_scenario(zero_income, "anspruch_m")
    return (
        cells.assign(
            household_key=household_key,
            household_label=MODEL_HOUSEHOLDS[household_key].label,
            heizkosten_m=heizkosten_m,
            actual_bruttokaltmiete_m=rent,
            rent_variant="variante_1_binding",
            transfer_kdu_zero_m=round_currency_m(zero[SCENARIO_KDU]),
            transfer_wogg_zero_m=round_currency_m(zero[SCENARIO_WOGG]),
            delta_transfer_zero_m=round_currency_m(
                zero[SCENARIO_KDU] - zero[SCENARIO_WOGG],
            ),
            exit_threshold_kdu_m=thresholds[SCENARIO_KDU],
            exit_threshold_wogg_m=thresholds[SCENARIO_WOGG],
            delta_exit_threshold_m=delta_y_star,
            delta_hours_per_week=round_ratio(hours_equivalent(delta_y_star)),
        )
        .merge(along_grid, on="cell_id", how="left", validate="one_to_one")
        .assign(proxy_error_m=lambda frame: frame["kdu_cap_m"] - frame["wogg_cap_m"])
    )


def binding_rent_m(cells: pd.DataFrame) -> NDArray[np.float64]:
    """§12.2 Variante 1: the construction rent `m = max(K, W)`."""
    return np.maximum(
        cells["kdu_cap_m"].to_numpy(dtype=float),
        cells["wogg_cap_m"].to_numpy(dtype=float),
    )


def grid_outcomes(
    cells: pd.DataFrame,
    household_key: str,
    rent: NDArray[np.float64],
    heizkosten_m: float,
    ceiling_m: float,
) -> pd.DataFrame:
    """Walk the ≤25 € income grid and reduce it to the §12.6 and §12.7 outcomes."""
    incomes = np.arange(
        INCOME_GRID.start_eur,
        ceiling_m + INCOME_GRID.step_eur,
        INCOME_GRID.step_eur,
        dtype=float,
    )
    frames = []
    for start in range(0, len(cells), CELL_CHUNK_SIZE):
        block = cells.iloc[start : start + CELL_CHUNK_SIZE].reset_index(drop=True)
        results = budget_curve(
            cells=block,
            household_key=household_key,
            actual_bruttokaltmiete_m=rent[start : start + CELL_CHUNK_SIZE],
            heizkosten_m=heizkosten_m,
            incomes_m=incomes,
        )
        frames.append(reduce_grid(results))
    return pd.concat(frames, ignore_index=True)


def reduce_grid(results: pd.DataFrame) -> pd.DataFrame:
    """Reduce one block's budget curves to one row per cell.

    Delivers `ΔT^max` (§12.6), the largest difference in income after housing
    costs, and the §12.7 regime boundaries: where SGB receipt ends once the
    Vorrangprüfung has run, and where Wohngeld or Kinderzuschlag begins.
    """
    kdu = _scenario_block(results, SCENARIO_KDU)
    wogg = _scenario_block(results, SCENARIO_WOGG)
    paired = pd.DataFrame(
        {
            "cell_id": kdu["cell_id"].to_numpy(),
            "gross_income_m": kdu["gross_income_m"].to_numpy(),
            "abs_delta_transfer_m": np.abs(
                kdu["anspruch_m"].to_numpy() - wogg["anspruch_m"].to_numpy(),
            ),
            "abs_delta_income_after_housing_m": np.abs(
                kdu["income_after_housing_m"].to_numpy()
                - wogg["income_after_housing_m"].to_numpy(),
            ),
            "sgb_ends_kdu": kdu["sgb_betrag_m"].to_numpy() <= 0.0,
            "sgb_ends_wogg": wogg["sgb_betrag_m"].to_numpy() <= 0.0,
            "wohngeld_kdu": _receives_wohngeld(kdu),
            "wohngeld_wogg": _receives_wohngeld(wogg),
        },
    )
    grouped = paired.groupby("cell_id", sort=True)
    reduced = grouped.agg(
        delta_transfer_max_m=("abs_delta_transfer_m", "max"),
        delta_income_after_housing_max_m=("abs_delta_income_after_housing_m", "max"),
    )
    reduced["sgb_regime_end_kdu_m"] = _first_income_where(grouped, "sgb_ends_kdu")
    reduced["sgb_regime_end_wogg_m"] = _first_income_where(grouped, "sgb_ends_wogg")
    reduced["wohngeld_regime_start_kdu_m"] = _first_income_where(
        grouped, "wohngeld_kdu"
    )
    reduced["wohngeld_regime_start_wogg_m"] = _first_income_where(
        grouped,
        "wohngeld_wogg",
    )
    reduced["delta_sgb_regime_end_m"] = (
        reduced["sgb_regime_end_kdu_m"] - reduced["sgb_regime_end_wogg_m"]
    )
    return reduced.reset_index()


def heating_sensitivity(
    cells_by_household: dict[str, pd.DataFrame],
    heating: HeatingAssumption,
) -> pd.DataFrame:
    """§12.3: repeat `ΔT(0)` and `Δy*` at 75 % and 125 % of the BA heating figure.

    Heating is identical across the two scenarios by construction, so it cannot
    move `ΔT(0)` at all. It moves `Δy*`, because a higher Bedarf pushes both exit
    thresholds out and the income-offsetting schedule is not linear.
    """
    frames = []
    for key, cells in cells_by_household.items():
        rent = binding_rent_m(cells)
        central = heating.for_household(key)
        for factor in (0.75, 1.25):
            heizkosten = float(round_currency_m(central * factor))
            zero = _by_scenario(
                evaluate(
                    build_cases(
                        cells=cells,
                        household_key=key,
                        actual_bruttokaltmiete_m=rent,
                        heizkosten_m=heizkosten,
                        gross_income_m=np.zeros(len(cells)),
                    ),
                ),
                "anspruch_m",
            )
            thresholds = exit_threshold_m(
                cells=cells,
                household_key=key,
                actual_bruttokaltmiete_m=rent,
                heizkosten_m=heizkosten,
            )
            delta_y_star = thresholds[SCENARIO_KDU] - thresholds[SCENARIO_WOGG]
            frames.append(
                cells.assign(
                    household_key=key,
                    heating_factor=factor,
                    heizkosten_m=heizkosten,
                    delta_transfer_zero_m=round_currency_m(
                        zero[SCENARIO_KDU] - zero[SCENARIO_WOGG],
                    ),
                    exit_threshold_kdu_m=thresholds[SCENARIO_KDU],
                    exit_threshold_wogg_m=thresholds[SCENARIO_WOGG],
                    delta_exit_threshold_m=delta_y_star,
                    delta_hours_per_week=round_ratio(hours_equivalent(delta_y_star)),
                ),
            )
    return pd.concat(frames, ignore_index=True)


def rent_grid_results(
    cells_by_household: dict[str, pd.DataFrame],
    heating: HeatingAssumption,
) -> pd.DataFrame:
    """§12.2 Variante 2: `ΔT(0)` across rents from 50 % to 130 % of `max(K, W)`."""
    frames = []
    for key, cells in cells_by_household.items():
        heizkosten = heating.for_household(key)
        binding = binding_rent_m(cells)
        for factor in rent_grid_factors():
            rent = round_currency_m(binding * factor)
            zero = _by_scenario(
                evaluate(
                    build_cases(
                        cells=cells,
                        household_key=key,
                        actual_bruttokaltmiete_m=rent,
                        heizkosten_m=heizkosten,
                        gross_income_m=np.zeros(len(cells)),
                    ),
                ),
                "anspruch_m",
            )
            frames.append(
                cells.assign(
                    household_key=key,
                    rent_factor=float(factor),
                    actual_bruttokaltmiete_m=rent,
                    heizkosten_m=heizkosten,
                    delta_transfer_zero_m=round_currency_m(
                        zero[SCENARIO_KDU] - zero[SCENARIO_WOGG],
                    ),
                ),
            )
    return pd.concat(frames, ignore_index=True)


def budget_curves(
    cells_by_household: dict[str, pd.DataFrame],
    heating: HeatingAssumption,
    gemeinde: pd.DataFrame,
) -> pd.DataFrame:
    """Full budget curves for the Gemeinden at the P10, median and P90 proxy error."""
    frames = []
    for key, cells in cells_by_household.items():
        chosen = select_reference_gemeinden(gemeinde, key)
        block = (
            cells.loc[cells["cell_id"].isin(chosen["cell_id"])]
            .reset_index(drop=True)
            .merge(chosen, on="cell_id", how="left", validate="one_to_one")
        )
        results = budget_curve(
            cells=block,
            household_key=key,
            actual_bruttokaltmiete_m=binding_rent_m(block),
            heizkosten_m=heating.for_household(key),
            incomes_m=np.asarray(INCOME_GRID.points(), dtype=float),
        )
        frames.append(
            results.merge(
                block.loc[:, ["cell_id", "ags", "gemeinde", "quantile_label"]],
                on="cell_id",
                how="left",
                validate="many_to_one",
            ),
        )
    return pd.concat(frames, ignore_index=True)


def select_reference_gemeinden(
    gemeinde: pd.DataFrame, household_key: str
) -> pd.DataFrame:
    """Pick the Gemeinde nearest each quantile of the proxy error (§12.8 fig. 3)."""
    rows = gemeinde.query("household_key == @household_key").dropna(
        subset=["proxy_error_m", "cell_id"],
    )
    chosen = []
    for quantile in BUDGET_CURVE_QUANTILES:
        target = rows["proxy_error_m"].quantile(quantile)
        nearest = rows.iloc[(rows["proxy_error_m"] - target).abs().argmin()]
        chosen.append(
            {
                "cell_id": int(nearest["cell_id"]),
                "ags": nearest["ags"],
                "gemeinde": nearest.get("gemeinde"),
                "quantile_label": f"P{int(quantile * 100)}",
            },
        )
    return pd.DataFrame(chosen).drop_duplicates(subset=["cell_id"])


def join_to_gemeinden(
    sample: pd.DataFrame,
    municipalities: pd.DataFrame,
    cells_by_household: dict[str, pd.DataFrame],
    cell_results: pd.DataFrame,
) -> pd.DataFrame:
    """D10: left-join the cell results back onto every Gemeinde of the sample."""
    frames = []
    for key, household in MODEL_HOUSEHOLDS.items():
        assignment = assign_cells(
            sample,
            cells_by_household[key],
            household.household_size,
        ).assign(household_key=key)
        outcomes = cell_results.query("household_key == @key").drop(
            columns=["household_key", "kdu_cap_m", "mietenstufe", "household_size"],
        )
        frames.append(
            assignment.merge(
                outcomes, on="cell_id", how="left", validate="many_to_one"
            ),
        )
    joined = pd.concat(frames, ignore_index=True)
    flags = (
        sample.query("household_size == 1")
        .loc[:, ["ags", "wogg_linked_flag", "quality_tier"]]
        .drop_duplicates(subset=["ags"])
    )
    keys = municipalities.loc[
        :,
        [
            "ags",
            "gemeinde",
            "policy_region_id",
            "kreis",
            "bundesland",
            "mietenstufe",
            "gemeinde_size_class",
            "population",
        ],
    ]
    return joined.merge(flags, on="ags", how="left", validate="many_to_one").merge(
        keys,
        on="ags",
        how="left",
        validate="many_to_one",
    )


def bestandsmiete_hook() -> None:
    """§12.2 Variante 3, the Bestandsmieten scenario, once the Zensus module lands.

    It plugs in exactly where Variante 1 does: replace `binding_rent_m` with the
    local Zensus Bestandsmiete per cell and nothing else changes, because the
    scenario contrast lives entirely in `kdu_cap.recognised_bruttokaltmiete_m`.
    The label to use is "Bestandsmietenszenario", never "market rent".
    """
    msg = (
        "The Bestandsmieten rent assumption of §12.2 Variante 3 needs the Zensus "
        "module; it is deliberately not implemented yet."
    )
    raise NotImplementedError(msg)


def _by_scenario(results: pd.DataFrame, column: str) -> dict[str, NDArray[np.float64]]:
    """Split one outcome column into its two scenarios, both sorted by cell."""
    return {
        scenario: results.query("scenario == @scenario")
        .sort_values("cell_id")[column]
        .to_numpy(dtype=float)
        for scenario in (SCENARIO_KDU, SCENARIO_WOGG)
    }


def _scenario_block(results: pd.DataFrame, scenario: str) -> pd.DataFrame:
    return (
        results.query("scenario == @scenario")
        .sort_values(["cell_id", "gross_income_m"])
        .reset_index(drop=True)
    )


def _receives_wohngeld(block: pd.DataFrame) -> NDArray[np.bool_]:
    return (
        block["wohngeld_m"].to_numpy(dtype=float)
        + block["kinderzuschlag_m"].to_numpy(dtype=float)
    ) > 0.0


def _first_income_where(grouped: object, flag: str) -> pd.Series:
    """Lowest grid income at which `flag` first holds, per cell."""
    return grouped.apply(  # ty: ignore[unresolved-attribute]
        lambda group: group.loc[group[flag], "gross_income_m"].min(),
        include_groups=False,
    )
