"""The §12.8 test protocol for the Standardfall microsimulation.

Tests 1 to 3 and the monotonicity assertion live in `test_kdu_cap.py`, where the
`min(m, cap)` rule itself is owned. What is added here is everything that needs
GETTSIM: the exact K/W contrast the audit pins down, the ban on a higher cap
lowering the Anspruch, hand-computed Ansprüche at selected incomes, the two sides
of each Einkommensanrechnung bracket, the child and couple households, and the
central rounding rule.
"""

import numpy as np
import pandas as pd
import pytest

from kdu.config import MODEL_HOUSEHOLDS
from kdu.simulation.kdu_cap import round_currency_m, unterkunftskosten_m
from kdu.simulation.microsim import (
    HEIZKOSTEN_SENSITIVITY_FACTORS,
    SCENARIO_KDU,
    SCENARIO_WOGG,
    build_cases,
    evaluate,
    exit_threshold_m,
    national_heating_costs_m,
    rent_grid_factors,
    simulation_cells,
)

REGELSATZ_SINGLE_M = 563.0
BUERGERGELD_GRUNDFREIBETRAG_M = 100.0
BUERGERGELD_SECOND_BRACKET_M = 520.0


def _one_case(
    household_key: str,
    kdu_cap_m: float,
    wogg_cap_m: float,
    actual_rent_m: float,
    heizkosten_m: float,
    gross_income_m: float = 0.0,
) -> pd.DataFrame:
    """Build the two-scenario case pair for a single (cap, rent, income) point."""
    cells = pd.DataFrame(
        {
            "cell_id": [0],
            "kdu_cap_m": [kdu_cap_m],
            "wogg_cap_m": [wogg_cap_m],
            "mietenstufe": [3],
        },
    )
    return build_cases(
        cells=cells,
        household_key=household_key,
        actual_bruttokaltmiete_m=np.array([actual_rent_m]),
        heizkosten_m=heizkosten_m,
        gross_income_m=np.array([gross_income_m]),
    )


def _by_scenario(results: pd.DataFrame, column: str) -> dict[str, float]:
    return {
        str(scenario): float(group[column].iloc[0])
        for scenario, group in results.groupby("scenario")
    }


@pytest.fixture(scope="module")
def audited_contrast() -> pd.DataFrame:
    """The exact case `docs/gettsim_audit.md` §2 verified, run end to end."""
    cases = _one_case("single_35", 520.0, 456.0, 520.0, 90.0)
    return evaluate(cases)


def test_audited_contrast_reproduces_the_kdu_anspruch(
    audited_contrast: pd.DataFrame,
) -> None:
    """A6: with K = 520, W = 456, m = 520 and 90 € heating, T^K(0) is 1,173 €."""
    assert _by_scenario(audited_contrast, "anspruch_m")[SCENARIO_KDU] == 1173.0


def test_audited_contrast_reproduces_the_wohngeld_proxy_anspruch(
    audited_contrast: pd.DataFrame,
) -> None:
    """A6: the same case under the Wohngeld proxy gives T^W(0) = 1,109 €."""
    assert _by_scenario(audited_contrast, "anspruch_m")[SCENARIO_WOGG] == 1109.0


def test_audited_contrast_difference_is_exactly_k_minus_w(
    audited_contrast: pd.DataFrame,
) -> None:
    """A6's headline: ΔT(0) = 1173 − 1109 = 64 = K − W, with heating cancelling."""
    anspruch = _by_scenario(audited_contrast, "anspruch_m")
    assert anspruch[SCENARIO_KDU] - anspruch[SCENARIO_WOGG] == 520.0 - 456.0


def test_regelbedarf_at_zero_income_is_regelsatz_plus_recognised_housing(
    audited_contrast: pd.DataFrame,
) -> None:
    """§12.8 test 5, hand-computed: 563 € Regelsatz + 520 € cap + 90 € heating."""
    assert (
        _by_scenario(audited_contrast, "anspruch_m")[SCENARIO_KDU]
        == REGELSATZ_SINGLE_M + 520.0 + 90.0
    )


def test_identical_caps_give_identical_ansprueche() -> None:
    """§12.8 test 1, through GETTSIM: K = W leaves nothing to differ in."""
    results = evaluate(_one_case("single_35", 500.0, 500.0, 700.0, 90.0))
    anspruch = _by_scenario(results, "anspruch_m")
    assert anspruch[SCENARIO_KDU] == anspruch[SCENARIO_WOGG]


def test_rent_below_both_caps_gives_identical_ansprueche() -> None:
    """§12.8 test 2, through GETTSIM: neither cap binds, so neither matters."""
    results = evaluate(_one_case("single_35", 520.0, 456.0, 300.0, 90.0))
    anspruch = _by_scenario(results, "anspruch_m")
    assert anspruch[SCENARIO_KDU] == anspruch[SCENARIO_WOGG]


def test_a_higher_kdu_cap_never_lowers_the_anspruch() -> None:
    """§12.8 test 4: raising the recognised cap can only raise the Anspruch."""
    caps = np.arange(300.0, 900.0, 25.0)
    cells = pd.DataFrame(
        {
            "cell_id": np.arange(len(caps)),
            "kdu_cap_m": caps,
            "wogg_cap_m": caps,
            "mietenstufe": np.full(len(caps), 3),
        },
    )
    cases = build_cases(
        cells=cells,
        household_key="single_35",
        actual_bruttokaltmiete_m=np.full(len(caps), 1200.0),
        heizkosten_m=90.0,
        gross_income_m=np.zeros(len(caps)),
    )
    anspruch = (
        evaluate(cases)
        .query("scenario == @SCENARIO_KDU")
        .sort_values("kdu_cap_m")["anspruch_m"]
        .to_numpy()
    )
    assert np.all(np.diff(anspruch) >= 0.0)


def test_all_simulated_results_are_finite() -> None:
    """A7: assert finiteness rather than filtering GETTSIM's benign 0/0 warning."""
    results = evaluate(_one_case("single_35", 520.0, 456.0, 520.0, 90.0))
    assert np.isfinite(results.select_dtypes("number").to_numpy()).all()


def test_results_carry_the_central_rounding_rule() -> None:
    """§12.8 test 8: every euro result equals its own centrally rounded value."""
    results = evaluate(_one_case("single_parent_child_8", 620.0, 551.0, 620.0, 100.0))
    amounts = results["anspruch_m"].to_numpy()
    np.testing.assert_array_equal(amounts, round_currency_m(amounts))


@pytest.fixture(scope="module")
def income_ladder() -> pd.DataFrame:
    """One single-person case per income point around both Anrechnung brackets."""
    incomes = np.array([0.0, 100.0, 101.0, 520.0, 521.0])
    cells = pd.DataFrame(
        {
            "cell_id": np.arange(len(incomes)),
            "kdu_cap_m": np.full(len(incomes), 520.0),
            "wogg_cap_m": np.full(len(incomes), 456.0),
            "mietenstufe": np.full(len(incomes), 3),
        },
    )
    cases = build_cases(
        cells=cells,
        household_key="single_35",
        actual_bruttokaltmiete_m=np.full(len(incomes), 520.0),
        heizkosten_m=90.0,
        gross_income_m=incomes,
    )
    results = evaluate(cases).query("scenario == @SCENARIO_KDU")
    return results.set_index("gross_income_m")["anspruch_m"]


def test_income_up_to_the_grundfreibetrag_leaves_the_anspruch_untouched(
    income_ladder: pd.Series,
) -> None:
    """§12.8 test 6: the first 100 € are free, so 100 € earns the same as 0 €."""
    assert income_ladder[BUERGERGELD_GRUNDFREIBETRAG_M] == income_ladder[0.0]


def test_the_euro_above_the_grundfreibetrag_is_counted_at_eighty_percent(
    income_ladder: pd.Series,
) -> None:
    """§12.8 test 6: in the 100–520 € bracket 20 % stays free, so 80 cents count."""
    step = income_ladder[BUERGERGELD_GRUNDFREIBETRAG_M] - income_ladder[101.0]
    assert step == pytest.approx(0.8, abs=1e-6)


def test_the_euro_above_the_second_bracket_is_counted_at_seventy_percent(
    income_ladder: pd.Series,
) -> None:
    """§12.8 test 6: from 520 € on, 30 % stays free, so only 70 cents count."""
    step = income_ladder[BUERGERGELD_SECOND_BRACKET_M] - income_ladder[521.0]
    assert step == pytest.approx(0.7, abs=1e-6)


@pytest.fixture(scope="module")
def zero_income_by_household() -> dict[str, float]:
    """T^K(0) for all four §11.1 Modellhaushalte at one common cap and rent."""
    frames = []
    for key in MODEL_HOUSEHOLDS:
        cells = pd.DataFrame(
            {"cell_id": [0], "kdu_cap_m": [600.0], "wogg_cap_m": [600.0]},
        ).assign(mietenstufe=3)
        frames.append(
            evaluate(
                build_cases(
                    cells=cells,
                    household_key=key,
                    actual_bruttokaltmiete_m=np.array([600.0]),
                    heizkosten_m=100.0,
                    gross_income_m=np.array([0.0]),
                ),
            ).query("scenario == @SCENARIO_KDU"),
        )
    combined = pd.concat(frames, ignore_index=True)
    return dict(
        zip(combined["household_key"], combined["anspruch_m"], strict=True),
    )


def test_single_household_anspruch_is_regelsatz_plus_housing(
    zero_income_by_household: dict[str, float],
) -> None:
    """§12.8 test 7, the reference case: 563 € + 600 € cap + 100 € heating."""
    assert zero_income_by_household["single_35"] == 563.0 + 700.0


def test_single_parent_household_carries_the_alleinerziehenden_mehrbedarf(
    zero_income_by_household: dict[str, float],
) -> None:
    """§12.8 test 7: the § 21 Abs. 3 Mehrbedarf raises the adult's Regelsatz by 12 %."""
    child_income_m = 259.0 + 299.0
    expected = 630.56 + 415.0 + 700.0 - child_income_m
    assert zero_income_by_household["single_parent_child_8"] == pytest.approx(
        expected,
        abs=0.01,
    )


def test_couple_household_sums_four_regelsaetze_net_of_kindergeld(
    zero_income_by_household: dict[str, float],
) -> None:
    """Two RBS 2 adults, a child of 8 and a child of 14, less Kindergeld."""
    kindergeld_m = 2 * 259.0
    expected = 506.0 + 506.0 + 415.0 + 496.0 + 700.0 - kindergeld_m
    assert zero_income_by_household["couple_children_8_14"] == pytest.approx(
        expected,
        abs=0.01,
    )


def test_pensioner_household_is_paid_under_sgb_xii_not_sgb_ii(
    zero_income_by_household: dict[str, float],
) -> None:
    """§11.1 household 4 draws Grundsicherung im Alter, on the same housing chain."""
    assert zero_income_by_household["pensioner_70"] == 563.0 + 700.0


def test_the_kdu_scenario_exit_threshold_is_never_below_the_proxy_one() -> None:
    """A higher recognised Bedarf can only push the exit threshold out, never in."""
    cells = pd.DataFrame(
        {
            "cell_id": [0, 1],
            "kdu_cap_m": [520.0, 700.0],
            "wogg_cap_m": [456.0, 456.0],
            "mietenstufe": [3, 3],
        },
    )
    thresholds = exit_threshold_m(
        cells=cells,
        household_key="single_35",
        actual_bruttokaltmiete_m=np.array([520.0, 700.0]),
        heizkosten_m=90.0,
    )
    assert np.all(thresholds[SCENARIO_KDU] >= thresholds[SCENARIO_WOGG])


def test_the_exit_threshold_is_located_to_one_euro() -> None:
    """D10: bisection returns a whole-euro threshold, not a 25 € grid point."""
    cells = pd.DataFrame(
        {
            "cell_id": [0],
            "kdu_cap_m": [520.0],
            "wogg_cap_m": [456.0],
            "mietenstufe": [3],
        },
    )
    thresholds = exit_threshold_m(
        cells=cells,
        household_key="single_35",
        actual_bruttokaltmiete_m=np.array([520.0]),
        heizkosten_m=90.0,
    )
    assert float(thresholds[SCENARIO_KDU][0]) == pytest.approx(
        round(float(thresholds[SCENARIO_KDU][0])),
    )


def test_simulation_cells_collapse_the_sample_to_distinct_cap_pairs() -> None:
    """D10: h = 1 has 782 distinct (K, Mietenstufe) cells, not 9,442 Gemeinden."""
    sample = pd.DataFrame(
        {
            "ags": ["01001000", "01002000", "01003000"],
            "household_size": [1, 1, 1],
            "kdu_bkc_cap": [486.0, 486.0, 520.0],
            "wogg_base_cap": [456.0, 456.0, 511.0],
            "wogg_rent_level": pd.array([3, 3, 4], dtype="Int64"),
            "wogg_rent_level_missing": [False, False, False],
        },
    )
    cells = simulation_cells(sample, household_size=1)
    assert len(cells) == 2


def test_simulation_cells_drop_gemeinden_without_a_statutory_mietenstufe() -> None:
    """A2: 119 Gemeinden have no Wohngeld benchmark, so no K−W contrast exists."""
    sample = pd.DataFrame(
        {
            "ags": ["01001000", "03154503"],
            "household_size": [1, 1],
            "kdu_bkc_cap": [486.0, 500.0],
            "wogg_base_cap": pd.array([456.0, None], dtype="Float64"),
            "wogg_rent_level": pd.array([3, None], dtype="Int64"),
            "wogg_rent_level_missing": [False, True],
        },
    )
    assert len(simulation_cells(sample, household_size=1)) == 1


def test_rent_grid_spans_fifty_to_one_hundred_thirty_percent() -> None:
    """§12.2 Variante 2: a grid from 50 % to 130 % of max(K, W) in ≤10 % steps."""
    factors = rent_grid_factors()
    assert (factors[0], factors[-1]) == (0.5, 1.3)


def test_rent_grid_steps_are_at_most_ten_percent() -> None:
    """§12.2 Variante 2 sets the maximum step width, not the minimum."""
    assert np.all(np.diff(rent_grid_factors()) <= 0.1 + 1e-9)


def test_heating_sensitivity_brackets_the_central_assumption() -> None:
    """§12.3: the heating sensitivity runs at 75 % and 125 % of the BA mean."""
    assert HEIZKOSTEN_SENSITIVITY_FACTORS == (0.75, 1.0, 1.25)


def test_national_heating_costs_are_a_stock_weighted_mean_over_kreise() -> None:
    """§12.3: the BA figure is weighted by Bedarfsgemeinschaften, never a plain mean."""
    ba = pd.DataFrame(
        {
            "reference_month": ["2026-04"] * 4,
            "region_level": ["kreis"] * 4,
            "region_code": ["01001", "01001", "01002", "01002"],
            "breakdown": ["household_size"] * 4,
            "category": ["1_person"] * 4,
            "measure": [
                "recognised_heizkosten_eur_per_bg",
                "bg_stock_with_recognised_kdu",
                "recognised_heizkosten_eur_per_bg",
                "bg_stock_with_recognised_kdu",
            ],
            "value": [60.0, 100.0, 80.0, 300.0],
        },
    )
    assumption = national_heating_costs_m(ba)
    assert assumption.per_household_size[1] == pytest.approx(75.0)


def test_income_after_housing_costs_subtracts_the_actual_bruttowarmmiete() -> None:
    """§12.6: `Y^posthousing` uses the actual warm rent, not the recognised amount."""
    cases = _one_case("single_35", 520.0, 456.0, 700.0, 90.0)
    results = evaluate(cases)
    row = results.query("scenario == @SCENARIO_KDU").iloc[0]
    assert row["income_after_housing_m"] == pytest.approx(
        row["disposable_income_m"] - (700.0 + 90.0),
        abs=0.01,
    )


def test_handing_the_engine_the_household_total_would_inflate_the_bedarf() -> None:
    """A6's gotcha, made visible: the override column is per-person, not per-household.

    `build_cases` splits by Kopfteil, so a two-person household's Anspruch at zero
    income is the Regelsätze plus the household housing amount exactly once.
    """
    household_amount = float(
        unterkunftskosten_m(
            np.array([620.0]),
            np.array([620.0]),
            np.array([100.0]),
        )[0],
    )
    cells = pd.DataFrame(
        {
            "cell_id": [0],
            "kdu_cap_m": [620.0],
            "wogg_cap_m": [620.0],
            "mietenstufe": [3],
        },
    )
    results = evaluate(
        build_cases(
            cells=cells,
            household_key="single_parent_child_8",
            actual_bruttokaltmiete_m=np.array([620.0]),
            heizkosten_m=100.0,
            gross_income_m=np.array([0.0]),
        ),
    )
    assert float(results["anerkannte_kdu_m"].iloc[0]) == pytest.approx(household_amount)


def test_simulation_cells_carry_the_primary_benchmark_cap() -> None:
    """The counterfactual is `W × 1.10`, not the bare § 12 WoGG table (D15)."""
    sample = pd.DataFrame(
        {
            "ags": ["01001000"],
            "household_size": [1],
            "kdu_bkc_cap": [486.0],
            "wogg_base_cap": pd.array([456.0], dtype="Float64"),
            "wogg_rent_level": pd.array([3], dtype="Int64"),
            "wogg_rent_level_missing": [False],
        },
    )
    cells = simulation_cells(sample, household_size=1)
    assert cells.loc[0, "wogg_cap_m"] == pytest.approx(456.0 * 1.10)
