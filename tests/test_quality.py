from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from kdu.data_management.harmonise import DerivedValueFlag, QualityTier
from kdu.data_management.quality import (
    ABSOLUTE_CAP_CEILING_EUR,
    QualityCheckResult,
    add_warn_flags,
    build_coverage_table,
    build_data_dictionary,
    build_quality_report,
    build_validation_worklist,
    run_all_checks,
)

SIZES = (1, 2, 3, 4, 5)


def make_long(n_municipalities: int = 4) -> pd.DataFrame:
    """Build a small long table with the columns every check reads."""
    records = []
    for index in range(n_municipalities):
        ags = f"0999900{index}"
        for position, size in enumerate(SIZES):
            records.append(
                {
                    "ags": ags,
                    "household_size": size,
                    "analysis_date": "2026-08-31",
                    "municipality_name": f"Gemeinde {index}",
                    "state_code": "09",
                    "state_name": "Musterland",
                    "policy_region_id": "09999",
                    "policy_region_name": "Musterkreis",
                    "kdu_bkc_cap": 400.0 + 100 * position + 10 * index,
                    "wogg_base_cap": 500.0,
                    "gross_cold_cap_total": 400.0 + 100 * position + 10 * index,
                    "net_cold_cap_total": np.nan,
                    "cold_opex_cap_total": np.nan,
                    "quality_tier": QualityTier.A.value,
                    "derived_value_flag": DerivedValueFlag.PRINTED.value,
                    "calculation_method": "published_gross_cold_total",
                    "source_document": "Doc.pdf",
                    "kdu_region": "Kreisgebiet",
                    "notes": "",
                },
            )
    long = pd.DataFrame.from_records(records)
    # One row publishes both components, so the total-versus-components check
    # has something to evaluate.
    consistent = len(SIZES)
    long.loc[consistent, "net_cold_cap_total"] = 100.0
    long.loc[consistent, "cold_opex_cap_total"] = (
        long.loc[consistent, "gross_cold_cap_total"] - 100.0
    )
    return long


def make_jump_flags(long: pd.DataFrame, n_flagged: int = 0) -> pd.DataFrame:
    """Build a `neighbour_jump_flags` frame flagging the first `n_flagged` rows."""
    flags = long[["ags", "household_size"]].copy()
    flags["large_neighbour_jump"] = False
    flags.iloc[:n_flagged, flags.columns.get_loc("large_neighbour_jump")] = True
    flags["has_cross_border_neighbour"] = True
    return flags


def run(long: pd.DataFrame) -> tuple[QualityCheckResult, ...]:
    return run_all_checks(
        long,
        geometry_ags=frozenset(long["ags"]),
        lookup_ags=frozenset(long["ags"]),
        source_valid_from={"Doc.pdf": frozenset({"2026-01-01"})},
    )


def result(results: tuple[QualityCheckResult, ...], check_id: int):
    return next(item for item in results if item.check_id == check_id)


def test_run_all_checks_returns_all_twelve() -> None:
    assert len(run(make_long())) == 12


def test_check_1_passes_on_a_unique_key() -> None:
    assert result(run(make_long()), 1).n_violations == 0


def test_check_1_catches_a_duplicated_key() -> None:
    long = pd.concat([make_long(), make_long().head(1)], ignore_index=True)
    assert result(run(long), 1).n_violations == 2


def test_check_2_catches_a_gemeinde_in_two_policy_regions() -> None:
    long = make_long()
    long.loc[0, "policy_region_id"] = "09998"
    assert result(run(long), 2).n_violations == 1


def test_check_3_catches_a_non_positive_cap() -> None:
    long = make_long()
    long.loc[0, "kdu_bkc_cap"] = 0.0
    assert result(run(long), 3).n_violations == 1


def test_check_4_counts_a_gemeinde_whose_cap_falls() -> None:
    long = make_long()
    long.loc[3, "kdu_bkc_cap"] = 100.0
    assert result(run(long), 4).n_violations == 1


def test_check_4_reports_flat_steps_separately_from_falling_ones() -> None:
    long = make_long()
    long.loc[1, "kdu_bkc_cap"] = long.loc[0, "kdu_bkc_cap"]
    assert "1 have at least one flat step" in result(run(long), 4).detail


def test_check_5_is_descriptive_and_never_raises_a_warn_flag() -> None:
    assert result(run(make_long()), 5).is_descriptive


def test_check_5_counts_kreise_carrying_more_than_one_cap() -> None:
    assert result(run(make_long()), 5).n_violations == 1


def test_check_6_catches_a_missing_household_size() -> None:
    long = make_long()
    long.loc[2, "kdu_bkc_cap"] = np.nan
    assert result(run(long), 6).n_violations == 1


def test_check_7_catches_an_absolute_outlier() -> None:
    long = make_long()
    long.loc[0, "kdu_bkc_cap"] = ABSOLUTE_CAP_CEILING_EUR + 1
    assert result(run(long), 7).n_violations >= 1


def test_check_8_catches_one_source_giving_two_caps_for_one_region() -> None:
    long = make_long(n_municipalities=2)
    assert result(run(long), 8).n_violations == len(SIZES)


def test_check_9_catches_a_total_that_contradicts_its_components() -> None:
    long = make_long()
    long.loc[0, "net_cold_cap_total"] = 100.0
    long.loc[0, "cold_opex_cap_total"] = 50.0
    assert result(run(long), 9).n_violations == 1


def test_check_10_catches_an_ags_outside_the_gebietsstand() -> None:
    long = make_long()
    results = run_all_checks(
        long,
        geometry_ags=frozenset(long["ags"]),
        lookup_ags=frozenset(),
        source_valid_from={},
    )
    assert result(results, 10).n_violations == long["ags"].nunique()


def test_check_11_catches_a_gemeinde_without_geometry() -> None:
    long = make_long()
    results = run_all_checks(
        long,
        geometry_ags=frozenset(),
        lookup_ags=frozenset(long["ags"]),
        source_valid_from={},
    )
    assert result(results, 11).n_violations == long["ags"].nunique()


def test_check_12_catches_two_effective_dates_behind_one_citation() -> None:
    long = make_long()
    results = run_all_checks(
        long,
        geometry_ags=frozenset(long["ags"]),
        lookup_ags=frozenset(long["ags"]),
        source_valid_from={"Doc.pdf": frozenset({"2025-01-01", "2026-01-01"})},
    )
    assert result(results, 12).n_violations == len(long)


def test_add_warn_flags_never_adds_a_column_for_the_descriptive_check() -> None:
    flagged = add_warn_flags(make_long(), run(make_long()))
    assert "warn_within_region_dispersion" not in flagged.columns


def test_add_warn_flags_counts_the_violations_per_row() -> None:
    long = make_long()
    long.loc[0, "kdu_bkc_cap"] = 0.0
    flagged = add_warn_flags(long, run(long))
    assert flagged.loc[0, "n_warn_flags"] >= 1


def test_build_coverage_table_reports_one_row_per_bundesland() -> None:
    assert len(build_coverage_table(make_long())) == 1


def test_build_coverage_table_counts_the_main_sample() -> None:
    coverage = build_coverage_table(make_long())
    assert coverage.loc[0, "n_in_main_sample"] == 4


def test_build_data_dictionary_describes_every_column() -> None:
    long = make_long()
    dictionary = build_data_dictionary(long, {"ags": "the key"})
    assert len(dictionary) == len(long.columns)


def test_build_data_dictionary_carries_the_supplied_description() -> None:
    dictionary = build_data_dictionary(make_long(), {"ags": "the key"})
    assert dictionary.set_index("variable").loc["ags", "description"] == "the key"


def test_build_validation_worklist_includes_every_tier_c_observation() -> None:
    long = make_long()
    long["quality_tier"] = QualityTier.C.value
    worklist = build_validation_worklist(
        long,
        check_results=run(long),
        file_index={},
        text_index={},
        neighbour_jump_flags=make_jump_flags(long),
    )
    assert len(worklist) == len(long)


def test_build_validation_worklist_marks_an_uncheckable_row_manual() -> None:
    long = make_long()
    worklist = build_validation_worklist(
        long,
        check_results=run(long),
        file_index={},
        text_index={},
        neighbour_jump_flags=make_jump_flags(long),
    )
    assert (worklist["auto_check_result"] == "manual").all()


def test_build_validation_worklist_passes_a_row_it_can_verify(tmp_path: Path) -> None:
    long = make_long()
    text = tmp_path / "Doc.txt"
    text.write_text(
        "\n".join(f"{value:.2f}".replace(".", ",") for value in long["kdu_bkc_cap"]),
        encoding="utf-8",
    )
    worklist = build_validation_worklist(
        long,
        check_results=run(long),
        file_index={"doc.pdf": tmp_path / "Doc.pdf"},
        text_index={"doc": text},
        neighbour_jump_flags=make_jump_flags(long),
    )
    assert (worklist["auto_check_result"] == "pass").all()


def test_build_validation_worklist_names_the_figure_to_check() -> None:
    long = make_long()
    worklist = build_validation_worklist(
        long,
        check_results=run(long),
        file_index={},
        text_index={},
        neighbour_jump_flags=make_jump_flags(long),
    )
    assert worklist["figure_to_check"].str.contains("EUR").all()


def test_build_validation_worklist_is_reproducible_under_its_seed() -> None:
    long = make_long(n_municipalities=40)
    first = build_validation_worklist(
        long,
        check_results=run(long),
        file_index={},
        text_index={},
        neighbour_jump_flags=make_jump_flags(long),
    )
    second = build_validation_worklist(
        long,
        check_results=run(long),
        file_index={},
        text_index={},
        neighbour_jump_flags=make_jump_flags(long),
    )
    pd.testing.assert_frame_equal(first, second)


def test_build_validation_worklist_includes_a_flagged_neighbour_jump_row() -> None:
    """A row flagged in `neighbour_jump_flags` enters the worklist by name."""
    long = make_long()
    worklist = build_validation_worklist(
        long,
        check_results=run(long),
        file_index={},
        text_index={},
        neighbour_jump_flags=make_jump_flags(long, n_flagged=2),
    )
    flagged = worklist.loc[
        worklist["reason"].str.contains("large_neighbour_jump"),
        ["ags", "household_size"],
    ]
    assert sorted(flagged["household_size"]) == [1, 2]


def test_build_validation_worklist_omits_an_unflagged_neighbour_jump_row() -> None:
    """No row carries the `large_neighbour_jump` reason when nothing is flagged."""
    long = make_long()
    worklist = build_validation_worklist(
        long,
        check_results=run(long),
        file_index={},
        text_index={},
        neighbour_jump_flags=make_jump_flags(long),
    )
    assert not worklist["reason"].str.contains("large_neighbour_jump").any()


def test_build_quality_report_renders_a_self_contained_page() -> None:
    long = make_long()
    worklist = build_validation_worklist(
        long,
        check_results=run(long),
        file_index={},
        text_index={},
        neighbour_jump_flags=make_jump_flags(long),
    )
    html = build_quality_report(
        long,
        check_results=run(long),
        coverage=build_coverage_table(long),
        unmatched_sources=pd.DataFrame(
            {"source_document": ["Doc.pdf"], "has_any_file": [True]},
        ),
        disagreements=pd.DataFrame(columns=["ags"]),
        worklist=worklist,
    )
    assert html.startswith("<!doctype html>")


@pytest.mark.parametrize("check_id", range(1, 13))
def test_every_check_reports_the_rows_it_evaluated(check_id: int) -> None:
    assert result(run(make_long()), check_id).n_evaluated > 0
