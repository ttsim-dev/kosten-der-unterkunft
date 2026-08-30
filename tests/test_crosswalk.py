import pandas as pd
import pytest

from kdu.config import catalog_path
from kdu.data_management.crosswalk import (
    CROSSWALK_COLUMNS,
    LOOKUP_ONLY_AGS,
    build_crosswalk,
    pad_ags,
    to_gemeinde_ags,
)

EXPECTED_GEMEINDEN = 10_980
EXPECTED_POLICY_REGIONS = 400


@pytest.fixture(scope="module")
def crosswalk() -> pd.DataFrame:
    kdu_gemeinden = pd.read_csv(
        catalog_path("kdu_gemeinden"),
        dtype=str,
        keep_default_na=False,
        engine="pyarrow",
    )
    gemeinde_lookup = pd.read_feather(catalog_path("gemeinde_lookup"))
    gemeinde_population = pd.read_feather(catalog_path("gemeinde_population"))
    return build_crosswalk(kdu_gemeinden, gemeinde_lookup, gemeinde_population)


def test_crosswalk_has_the_documented_schema(crosswalk: pd.DataFrame) -> None:
    assert tuple(crosswalk.columns) == CROSSWALK_COLUMNS


def test_crosswalk_has_one_row_per_gemeinde(crosswalk: pd.DataFrame) -> None:
    assert len(crosswalk) == EXPECTED_GEMEINDEN


def test_policy_region_is_the_kreis(crosswalk: pd.DataFrame) -> None:
    pd.testing.assert_series_equal(
        crosswalk["policy_region_id"],
        crosswalk["ags_kreis"],
        check_names=False,
    )


def test_there_are_four_hundred_policy_regions(crosswalk: pd.DataFrame) -> None:
    assert crosswalk["policy_region_id"].nunique() == EXPECTED_POLICY_REGIONS


def test_policy_region_is_the_first_five_digits_of_the_ags(
    crosswalk: pd.DataFrame,
) -> None:
    assert (crosswalk["ags"].str[:5] == crosswalk["policy_region_id"]).all()


def test_ags_keeps_its_leading_zeros(crosswalk: pd.DataFrame) -> None:
    assert (crosswalk["ags"].str.len() == 8).all()


def test_schleswig_holstein_ags_survive_the_csv_round_trip(
    crosswalk: pd.DataFrame,
) -> None:
    assert crosswalk["ags"].str.startswith("01").sum() > 0


def test_population_is_attached_to_every_gemeinde(crosswalk: pd.DataFrame) -> None:
    assert crosswalk["population"].notna().all()


def test_kreisfrei_flags_the_expected_number_of_staedte(
    crosswalk: pd.DataFrame,
) -> None:
    assert crosswalk["is_kreisfrei"].sum() == 106


def test_every_kreisfreie_stadt_is_alone_in_its_policy_region(
    crosswalk: pd.DataFrame,
) -> None:
    sizes = crosswalk.groupby("policy_region_id")["ags"].transform("size")
    assert (sizes[crosswalk["is_kreisfrei"]] == 1).all()


def test_mietenstufe_stays_within_the_statutory_range(crosswalk: pd.DataFrame) -> None:
    values = crosswalk["mietenstufe"].dropna()
    assert values.between(1, 7).all()


def test_jobcenter_id_is_an_unfilled_string_column(crosswalk: pd.DataFrame) -> None:
    assert crosswalk["jobcenter_id"].isna().all()


def test_bundesland_is_never_missing(crosswalk: pd.DataFrame) -> None:
    assert crosswalk["bundesland"].notna().all()


def test_to_gemeinde_ags_drops_the_verbandsgemeinde_digits() -> None:
    codes = pd.Series(["146270060060", "010010000000"], dtype="string")
    assert list(to_gemeinde_ags(codes)) == ["14627060", "01001000"]


def test_pad_ags_restores_a_stripped_leading_zero() -> None:
    assert pad_ags(pd.Series(["1059126"], dtype="string")).item() == "01059126"


def test_build_crosswalk_raises_when_an_input_covers_other_gemeinden() -> None:
    kdu = pd.DataFrame(
        {"ags_gemeinde": ["01001000"], "ags_kreis": ["01001"], "wogv_mietstufe": ["3"]},
    )
    lookup = pd.DataFrame(
        {
            "ags": ["010010000000"],
            "gemeinde": ["Flensburg"],
            "kreis": ["Kreisfreie Stadt Flensburg"],
            "bundesland": ["Schleswig-Holstein"],
        },
    )
    population = pd.DataFrame(
        {"ags": ["01002000"], "population": [1], "area_sqkm": [1.0]}
    )
    with pytest.raises(ValueError, match="same Gemeinden"):
        build_crosswalk(kdu, lookup, population)


def test_build_crosswalk_drops_only_the_named_lookup_only_ags(
    crosswalk: pd.DataFrame,
) -> None:
    assert not crosswalk["ags"].isin(LOOKUP_ONLY_AGS).any()
