"""P0.6 — the regionalised administrative Bruttokaltbedarf of §11.

The measure is `B = R + M + cap`: Regelbedarfe plus standardised Mehrbedarfe plus
the recognised Bruttokaltmiete cap, with heating deliberately outside it. These
tests pin the three quantities that could silently go wrong: the Regelbedarf side, the
arithmetic of the two scenarios, and the wording §11.2 and §20 require.
"""

import numpy as np
import pandas as pd
import pytest

from kdu.simulation.needs_level import (
    NEEDS_MEASURE_LABEL,
    administrative_need,
    regelbedarf_components,
)
from kdu.simulation.task_needs_level import build_summary_table

RBS_1_2026_M = 563.0


@pytest.fixture(scope="module")
def components() -> dict[str, float]:
    """Regelbedarf plus Mehrbedarf, no housing, for the four §11.1 households."""
    return {
        key: entry.standard_need_m for key, entry in regelbedarf_components().items()
    }


def test_single_household_standard_need_is_regelbedarfsstufe_one(
    components: dict[str, float],
) -> None:
    """RBS 1 for 2026 is 563 € (RBSFV 2026, a Nullrunde under § 28a Abs. 5 SGB XII)."""
    assert components["single_35"] == RBS_1_2026_M


def test_pensioner_household_standard_need_is_regelbedarfsstufe_one(
    components: dict[str, float],
) -> None:
    """A single pensioner draws the same Regelbedarfsstufe under SGB XII."""
    assert components["pensioner_70"] == RBS_1_2026_M


def test_single_parent_standard_need_adds_the_alleinerziehenden_mehrbedarf(
    components: dict[str, float],
) -> None:
    """§ 21 Abs. 3 SGB II: 12 % of RBS 1 for one child, plus the child's own RBS 5."""
    assert components["single_parent_child_8"] == pytest.approx(
        RBS_1_2026_M * 1.12 + 415.0,
        abs=0.01,
    )


def test_couple_standard_need_sums_two_adults_and_two_children(
    components: dict[str, float],
) -> None:
    """Two RBS 2 adults at 506 €, a child of 8 at 415 € and one of 14 at 496 €."""
    assert components["couple_children_8_14"] == pytest.approx(
        506.0 + 506.0 + 415.0 + 496.0,
        abs=0.01,
    )


def test_the_single_parent_mehrbedarf_is_reported_separately() -> None:
    """§11.2 splits the measure into `R + M + cap`, so `M` must be visible."""
    entry = regelbedarf_components()["single_parent_child_8"]
    assert entry.mehrbedarf_m == pytest.approx(RBS_1_2026_M * 0.12, abs=0.01)


def test_households_without_a_mehrbedarf_report_zero() -> None:
    assert regelbedarf_components()["single_35"].mehrbedarf_m == 0.0


@pytest.fixture(scope="module")
def need() -> pd.DataFrame:
    """`B^K` and `B^W` for two Gemeinden and the single-person household."""
    sample = pd.DataFrame(
        {
            "ags": ["01001000", "01002000"],
            "household_size": [1, 1],
            "kdu_bkc_cap": [486.0, 600.0],
            "wogg_base_cap": pd.array([456.0, 562.0], dtype="Float64"),
            "wogg_climate_component": pd.array([19.2, 24.0], dtype="Float64"),
            "wogg_rent_level": pd.array([3, 5], dtype="Int64"),
            "wogg_rent_level_missing": [False, False],
        },
    )
    return administrative_need(sample, household_key="single_35")


def test_kdu_based_need_is_regelbedarf_plus_the_local_cap(need: pd.DataFrame) -> None:
    """§11.2: `B^K = R + M + K`, with heating outside the measure."""
    assert need.loc[0, "need_kdu_m"] == RBS_1_2026_M + 486.0


def test_wohngeld_based_need_is_regelbedarf_plus_the_proxy_cap(
    need: pd.DataFrame,
) -> None:
    """§11.2: `B^W = R + M + W`, on the primary benchmark `W × 1.10` (D15)."""
    assert need.loc[0, "need_wogg_m"] == pytest.approx(RBS_1_2026_M + 456.0 * 1.10)


def test_the_need_difference_is_exactly_the_proxy_error(need: pd.DataFrame) -> None:
    """Everything but the housing component is national, so `B^K − B^W = K − W`."""
    np.testing.assert_allclose(
        need["need_difference_m"].to_numpy(),
        need["kdu_cap_m"].to_numpy() - need["wogg_cap_m"].to_numpy(),
    )


def test_the_kdu_share_is_the_cap_over_the_kdu_based_need(need: pd.DataFrame) -> None:
    """§11.3: `S^K = K / B^K`."""
    assert need.loc[0, "kdu_share_of_need"] == pytest.approx(
        486.0 / (RBS_1_2026_M + 486.0),
        abs=1e-6,
    )


def test_the_klima_robustness_need_uses_the_climate_component(
    need: pd.DataFrame,
) -> None:
    """D6 makes the base-plus-Klimakomponente row mandatory, not optional."""
    assert need.loc[0, "need_wogg_klima_m"] == RBS_1_2026_M + 456.0 + 19.2


def test_gemeinden_without_a_mietenstufe_keep_their_kdu_need_but_lose_the_contrast() -> (
    None
):
    """A2: 119 Gemeinden have a cap but no statutory Wohngeld benchmark."""
    sample = pd.DataFrame(
        {
            "ags": ["03154503"],
            "household_size": [1],
            "kdu_bkc_cap": [500.0],
            "wogg_base_cap": pd.array([None], dtype="Float64"),
            "wogg_climate_component": pd.array([None], dtype="Float64"),
            "wogg_rent_level": pd.array([None], dtype="Int64"),
            "wogg_rent_level_missing": [True],
        },
    )
    result = administrative_need(sample, household_key="single_35")
    assert result["need_kdu_m"].notna().all()
    assert result["need_difference_m"].isna().all()


def test_the_measure_label_is_the_one_paragraph_eleven_point_two_prescribes() -> None:
    """§11.2 and §20 both forbid calling this a full Existenzminimum."""
    assert NEEDS_MEASURE_LABEL == (
        "administrative Bruttokaltbedarf before income offsetting"
    )


def test_the_measure_label_never_claims_to_be_an_existenzminimum() -> None:
    assert "Existenzminimum" not in NEEDS_MEASURE_LABEL


def test_summary_reports_the_needs_level_with_the_linked_group_set_aside() -> None:
    """D15 makes their gap zero by construction, so both readings are reported."""
    need = pd.DataFrame(
        {
            "ags": ["01001000", "01002000"],
            "household_key": ["single_35", "single_35"],
            "household_size": [1, 1],
            "need_kdu_m": [1049.0, 1000.0],
            "need_wogg_m": [1001.6, 1000.0],
            "need_wogg_klima_m": [1020.0, 1010.0],
            "need_difference_m": [47.4, 0.0],
            "kdu_cap_m": [486.0, 437.0],
            "wogg_cap_m": [438.6, 437.0],
            "kdu_share_of_need": [0.46, 0.44],
            "wogg_share_of_need": [0.44, 0.44],
            "standard_need_m": [563.0, 563.0],
            "wogg_klima_cap_m": [457.8, 456.2],
            "population": [1000, 1000],
            "bundesland": ["Schleswig-Holstein", "Schleswig-Holstein"],
            "mietenstufe": [3, 3],
            "gemeinde_size_class": ["50,000 and over", "50,000 and over"],
            "wogg_linked_flag": [False, True],
        },
    )
    summary = build_summary_table(need)
    unlinked = summary.query(
        "breakdown == 'wogg_linked_flag' and group == 'False'",
    )
    assert unlinked["need_difference_median"].iloc[0] == pytest.approx(47.4)
