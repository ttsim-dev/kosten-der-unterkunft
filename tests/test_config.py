from datetime import date
from pathlib import Path

import pytest

from kdu import config
from kdu.config import (
    ANALYSIS_DATE,
    CORPUS_ENV_VAR,
    CORPUS_PATHS,
    DATA_CATALOG,
    HOUSEHOLD_SIZES,
    INCOME_GRID,
    LEGAL_VINTAGE,
    MIETENSTUFEN,
    MODEL_HOUSEHOLDS,
    ExclusionReason,
    MemberRole,
    WeightingScheme,
    catalog_path,
    corpus_path,
    corpus_root,
)


def test_analysis_date_is_the_stichtag() -> None:
    assert date(2026, 8, 31) == ANALYSIS_DATE


def test_legal_vintage_pins_wogg_and_sgb_to_2026() -> None:
    assert (LEGAL_VINTAGE.wogg_rechtsstand, LEGAL_VINTAGE.sgb_rechtsstand) == (
        2026,
        2026,
    )


def test_ba_reference_month_does_not_exceed_the_stichtag() -> None:
    assert LEGAL_VINTAGE.ba_reference_month <= ANALYSIS_DATE.strftime("%Y-%m")


def test_household_sizes_cover_one_to_five() -> None:
    assert HOUSEHOLD_SIZES == (1, 2, 3, 4, 5)


def test_four_model_households_are_defined() -> None:
    assert len(MODEL_HOUSEHOLDS) == 4


@pytest.mark.parametrize(
    ("key", "expected_size"),
    [
        ("single_35", 1),
        ("single_parent_child_8", 2),
        ("couple_children_8_14", 4),
        ("pensioner_70", 1),
    ],
)
def test_model_household_size_matches_its_members(key: str, expected_size: int) -> None:
    assert MODEL_HOUSEHOLDS[key].household_size == expected_size


def test_couple_household_has_children_aged_eight_and_fourteen() -> None:
    assert MODEL_HOUSEHOLDS["couple_children_8_14"].child_ages == (8, 14)


def test_single_parent_household_is_flagged_for_the_mehrbedarf() -> None:
    assert MODEL_HOUSEHOLDS["single_parent_child_8"].is_single_parent


def test_pensioner_household_member_is_seventy_and_a_pensioner() -> None:
    member = MODEL_HOUSEHOLDS["pensioner_70"].members[0]
    assert (member.age, member.role) == (70, MemberRole.ADULT_PENSIONER)


def test_every_model_household_is_beyond_the_karenzzeit() -> None:
    assert all(household.karenzzeit_elapsed for household in MODEL_HOUSEHOLDS.values())


def test_income_grid_step_does_not_exceed_25_euro() -> None:
    assert INCOME_GRID.step_eur <= 25


def test_income_grid_ceiling_is_8000_euro() -> None:
    assert INCOME_GRID.ceiling_eur == 8_000


def test_income_grid_stops_after_twelve_empty_points() -> None:
    assert INCOME_GRID.stop_after_consecutive_empty_points == 12


def test_income_grid_points_start_at_zero_and_end_at_the_ceiling() -> None:
    points = INCOME_GRID.points()
    assert (points[0], points[-1]) == (0, 8_000)


def test_four_weighting_schemes_are_defined() -> None:
    assert len(WeightingScheme) == 4


def test_exclusion_reasons_match_the_decision_log_codes() -> None:
    assert {reason.value for reason in ExclusionReason} == {
        "gemeindefreies_gebiet",
        "kein_dokument",
        "nur_bruttowarm",
        "nur_eur_pro_qm_ohne_flaeche",
        "ableitungsverbot",
        "nicht_oeffentlich",
    }


def test_corpus_root_reads_the_environment_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CORPUS_ENV_VAR, str(tmp_path))
    assert corpus_root() == tmp_path


def test_corpus_root_raises_when_the_corpus_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CORPUS_ENV_VAR, str(tmp_path / "nowhere"))
    with pytest.raises(FileNotFoundError, match=CORPUS_ENV_VAR):
        corpus_root()


def test_corpus_root_falls_back_to_the_sciebo_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(CORPUS_ENV_VAR, raising=False)
    monkeypatch.setattr(config, "DEFAULT_CORPUS_ROOT", tmp_path)
    assert corpus_root() == tmp_path


def test_corpus_path_resolves_a_registered_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CORPUS_ENV_VAR, str(tmp_path))
    assert corpus_path("converted_text") == tmp_path / "kdu_pdfs/converted_text"


def test_corpus_path_raises_on_an_unknown_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CORPUS_ENV_VAR, str(tmp_path))
    with pytest.raises(KeyError, match="Unknown corpus member"):
        corpus_path("kdu_pdfs")


def test_every_corpus_member_is_relative() -> None:
    assert not any(Path(value).is_absolute() for value in CORPUS_PATHS.values())


@pytest.mark.parametrize(
    "name",
    [
        "gemeinden_geojson",
        "gemeinde_lookup",
        "gemeinde_population",
        "kdu_gemeinden",
        "wogg_parameters",
        "wogg_benchmark",
        "municipality_crosswalk",
        "kdu_municipality_household",
        "kdu_policy_region_household",
        "analysis_sample_main",
        "analysis_sample_extended",
        "data_dictionary",
        "source_register",
        "exclusion_log",
        "quality_report",
        "results_manifest",
        "germany_map",
    ],
)
def test_data_catalog_registers(name: str) -> None:
    assert DATA_CATALOG[name] is not None


@pytest.mark.parametrize(
    "name",
    ["gemeinden_geojson", "gemeinde_lookup", "gemeinde_population", "kdu_gemeinden"],
)
def test_committed_inputs_exist(name: str) -> None:
    assert catalog_path(name).exists()


def test_mietenstufen_cover_one_to_seven() -> None:
    assert MIETENSTUFEN == (1, 2, 3, 4, 5, 6, 7)


def test_wogg_hoechstbetrag_rechtsstand_is_in_force_at_the_stichtag() -> None:
    assert LEGAL_VINTAGE.wogg_hoechstbetrag_in_force_from <= ANALYSIS_DATE


def test_wogg_components_rechtsstand_is_in_force_at_the_stichtag() -> None:
    assert LEGAL_VINTAGE.wogg_components_in_force_from <= ANALYSIS_DATE
