"""Deduplication, case construction and bracketing for the exit threshold."""

import numpy as np
import pandas as pd
import pytest

from kdu.eligibility.microsimulation import (
    CASE_COLUMNS,
    SCENARIO_FALLBACK,
    SCENARIO_LOCAL_CAP,
    _bracket_from_ladder,
    assign_cap_pairs,
    build_cases,
    distinct_cap_pairs,
    national_heizkosten_eur_per_month,
    summarise_exit_thresholds,
    wohnflaeche_sqm,
)


@pytest.fixture
def sample() -> pd.DataFrame:
    """Four Gemeinden, two of which share a cap and a Mietenstufe."""
    return pd.DataFrame(
        {
            "ags": ["01001000", "01002000", "01003000", "01004000"],
            "household_size": [1, 1, 1, 1],
            "kdu_cap": [486.0, 486.0, 500.0, 400.0],
            "mietenstufe": [3, 3, 3, 1],
            "wohngeld_fallback_cap": [501.6, 501.6, 501.6, 390.5],
        },
    )


def test_distinct_cap_pairs_collapses_gemeinden_that_share_a_cap(
    sample: pd.DataFrame,
) -> None:
    """Four Gemeinden with three distinct cap and Mietenstufe pairs yield three rows."""
    assert len(distinct_cap_pairs(sample, 1)) == 3


def test_distinct_cap_pairs_counts_the_gemeinden_behind_each_pair(
    sample: pd.DataFrame,
) -> None:
    """The pair shared by two Gemeinden records both of them."""
    pairs = distinct_cap_pairs(sample, 1)
    shared = pairs.query("kdu_cap == 486.0 and mietenstufe == 3")
    assert int(shared["n_gemeinden"].iloc[0]) == 2


def test_assign_cap_pairs_returns_one_row_per_gemeinde(
    sample: pd.DataFrame,
) -> None:
    """Joining the pairs back never duplicates or drops a Gemeinde."""
    assigned = assign_cap_pairs(sample, distinct_cap_pairs(sample, 1), 1)
    assert len(assigned) == 4


def test_build_cases_yields_two_scenarios_per_cap_pair(
    sample: pd.DataFrame,
) -> None:
    """Each cap pair enters the simulation once under each cap."""
    pairs = distinct_cap_pairs(sample, 1)
    rent = np.full(len(pairs), 900.0)
    cases = build_cases(pairs, "single_35", rent, 67.76, np.zeros(len(pairs)))
    assert len(cases) == 2 * len(pairs)


def test_build_cases_recognises_each_scenario_s_own_cap(
    sample: pd.DataFrame,
) -> None:
    """With a rent above both caps, each scenario recognises exactly its cap."""
    pairs = distinct_cap_pairs(sample, 1).query("kdu_cap == 486.0")
    rent = np.full(len(pairs), 900.0)
    cases = build_cases(pairs, "single_35", rent, 0.0, np.zeros(len(pairs)))
    recognised = cases.set_index("scenario")["recognised_bruttokaltmiete"]
    assert recognised[SCENARIO_LOCAL_CAP] == 486.0
    assert recognised[SCENARIO_FALLBACK] == 501.6


def test_build_cases_produces_every_required_column(sample: pd.DataFrame) -> None:
    """`evaluate` reads a fixed set of columns and `build_cases` supplies them."""
    pairs = distinct_cap_pairs(sample, 1)
    cases = build_cases(
        pairs,
        "single_35",
        np.full(len(pairs), 900.0),
        67.76,
        np.zeros(len(pairs)),
    )
    assert tuple(cases.columns) == CASE_COLUMNS


def test_bracket_from_ladder_encloses_the_income_where_the_claim_vanishes() -> None:
    """The bracket is the last income with a claim and the first without."""
    claims = np.array([[300.0, 200.0, 100.0, 0.0, 0.0]])
    ladder = np.array([0.0, 500.0, 1000.0, 1500.0, 2000.0])
    lower, upper = _bracket_from_ladder(claims, ladder)
    np.testing.assert_allclose(lower, [1000.0])
    np.testing.assert_allclose(upper, [1500.0])


def test_bracket_from_ladder_returns_zero_when_no_claim_exists_at_all() -> None:
    """A household with no claim even at zero income exits at zero."""
    claims = np.array([[0.0, 0.0]])
    ladder = np.array([0.0, 500.0])
    lower, upper = _bracket_from_ladder(claims, ladder)
    np.testing.assert_allclose(lower, [0.0])
    np.testing.assert_allclose(upper, [0.0])


def test_wohnflaeche_grows_by_fifteen_square_metres_per_further_person() -> None:
    """A four-person household is credited 45 plus three times 15 square metres."""
    assert wohnflaeche_sqm(4) == 90.0


def test_national_heizkosten_weights_jobcenter_by_their_stock() -> None:
    """A large Jobcenter moves the national mean more than a small one."""
    statistic = pd.DataFrame(
        {
            "region_level": ["jobcenter"] * 4,
            "region_code": ["t01", "t01", "t02", "t02"],
            "measure": [
                "recognised_heizkosten_eur_per_bg",
                "bg_stock_with_recognised_kdu",
                "recognised_heizkosten_eur_per_bg",
                "bg_stock_with_recognised_kdu",
            ],
            "1_person": [100.0, 300.0, 200.0, 100.0],
            "2_persons": [100.0, 300.0, 200.0, 100.0],
            "3_persons": [100.0, 300.0, 200.0, 100.0],
            "4_persons": [100.0, 300.0, 200.0, 100.0],
            "5_persons": [100.0, 300.0, 200.0, 100.0],
        },
    )
    heating = national_heizkosten_eur_per_month(statistic)
    assert heating.per_household_size[1] == 125.0


def test_summarise_exit_thresholds_reports_the_amplification() -> None:
    """The amplification is the median ratio over Gemeinden where the caps differ."""
    thresholds = pd.DataFrame(
        {
            "household_key": ["single_35"] * 3,
            "cap_difference": [10.0, 100.0, 0.0],
            "exit_threshold_difference": [20.0, 200.0, 0.0],
        },
    )
    summary = summarise_exit_thresholds(thresholds)
    assert summary["amplification"].iloc[0] == 2.0
