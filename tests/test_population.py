import json
from datetime import date

import pandas as pd
import pytest

from kdu.config import SMALL_GEMEINDE_THRESHOLD, catalog_path
from kdu.data_management.crosswalk import to_gemeinde_ags
from kdu.data_management.population import (
    POPULATION_COLUMNS,
    MergerReversal,
    assign_size_class,
    build_gemeinde_population,
    load_gemeinde_population,
    parse_gv_rows,
)

EXPECTED_GEMEINDEN = 10_980


@pytest.fixture(scope="module")
def population() -> pd.DataFrame:
    return load_gemeinde_population(catalog_path("gemeinde_population"))


@pytest.fixture(scope="module")
def boundary_ags() -> pd.Series:
    raw = json.loads(
        catalog_path("gemeinden_geojson").read_text(encoding="utf-8"),
    )
    codes = pd.Series(
        [feature["properties"]["gem_code"] for feature in raw["features"]],
        dtype="string",
    )
    return to_gemeinde_ags(codes)


def test_population_table_has_the_documented_schema(population: pd.DataFrame) -> None:
    assert tuple(population.columns) == POPULATION_COLUMNS


def test_population_table_covers_the_boundary_ags_exactly(
    population: pd.DataFrame, boundary_ags: pd.Series
) -> None:
    assert set(population["ags"]) == set(boundary_ags)


def test_population_table_has_one_row_per_gemeinde(population: pd.DataFrame) -> None:
    assert len(population) == EXPECTED_GEMEINDEN


def test_population_ags_keep_their_leading_zeros(population: pd.DataFrame) -> None:
    assert (population["ags"].str.len() == 8).all()


def test_population_is_never_missing(population: pd.DataFrame) -> None:
    assert population["population"].notna().all()


def test_area_is_strictly_positive(population: pd.DataFrame) -> None:
    assert (population["area_sqkm"] > 0).all()


def test_small_gemeinde_flag_matches_the_ten_thousand_split(
    population: pd.DataFrame,
) -> None:
    expected = population["population"] < SMALL_GEMEINDE_THRESHOLD
    pd.testing.assert_series_equal(
        population["is_small_gemeinde"],
        expected,
        check_names=False,
    )


def test_reconciled_rows_carry_the_backfill_reference_date(
    population: pd.DataFrame,
) -> None:
    restored = population.loc[
        population["ags"].isin(["01059101", "01059141", "09374451"]),
        "population_reference_date",
    ]
    assert set(restored) == {"2022-12-31"}


def test_reversing_the_huerup_merger_conserves_population(
    population: pd.DataFrame,
) -> None:
    absorbed = population.loc[
        population["ags"].isin(["01059101", "01059141"]),
        "population",
    ].sum()
    huerup = population.loc[population["ags"] == "01059126", "population"].item()
    assert huerup + absorbed == 2394


def test_parse_gv_rows_builds_the_eight_digit_ags_without_the_verbandsgemeinde() -> (
    None
):
    rows = [("60", "61", "01", "0", "01", "0000", "000", "Flensburg", 56.73, 92550)]
    assert parse_gv_rows(rows)["ags"].item() == "01001000"


def test_parse_gv_rows_ignores_non_gemeinde_record_types() -> None:
    rows = [("40", "41", "01", "0", "01", None, None, "Flensburg", None, None)]
    assert parse_gv_rows(rows).empty


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1_999, "under 2,000"),
        (2_000, "2,000-4,999"),
        (9_999, "5,000-9,999"),
        (10_000, "10,000-19,999"),
        (49_999, "20,000-49,999"),
        (50_000, "50,000 and over"),
    ],
)
def test_assign_size_class_bins_at_the_documented_breaks(
    value: int, expected: str
) -> None:
    assert assign_size_class(pd.Series([value])).item() == expected


def test_build_gemeinde_population_raises_when_an_ags_cannot_be_covered() -> None:
    base = pd.DataFrame(
        {
            "ags": ["01001000"],
            "gemeinde_name": ["Flensburg"],
            "population": [92_550],
            "area_sqkm": [56.73],
        },
    )
    with pytest.raises(ValueError, match="1 missing"):
        build_gemeinde_population(
            base=base,
            backfill=base,
            boundary_ags=pd.Series(["01001000", "01002000"], dtype="string"),
            reversals=(),
            base_reference_date=date(2023, 12, 31),
            backfill_reference_date=date(2022, 12, 31),
        )


def test_build_gemeinde_population_nets_a_reversal_out_of_its_successor() -> None:
    base = pd.DataFrame(
        {
            "ags": ["01059126"],
            "gemeinde_name": ["Hürup"],
            "population": [2_394],
            "area_sqkm": [28.07],
        },
    )
    backfill = pd.DataFrame(
        {
            "ags": ["01059101"],
            "gemeinde_name": ["Tastrup"],
            "population": [385],
            "area_sqkm": [4.16],
        },
    )
    result = build_gemeinde_population(
        base=base,
        backfill=backfill,
        boundary_ags=pd.Series(["01059126", "01059101"], dtype="string"),
        reversals=(
            MergerReversal(
                absorbed_ags=("01059101",),
                successor_ags="01059126",
                note="test",
            ),
        ),
        base_reference_date=date(2023, 12, 31),
        backfill_reference_date=date(2022, 12, 31),
    )
    assert result.loc[result["ags"] == "01059126", "population"].item() == 2_009
