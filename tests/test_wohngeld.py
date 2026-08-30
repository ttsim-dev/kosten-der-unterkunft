"""Tests for the Wohngeld benchmark (P0.2).

The official values asserted here are transcribed from

- Anlage 1 (zu § 12 Absatz 1) WoGG, in force 2025-01-01,
- § 12 Absatz 7 WoGG (Klimakomponente), in force 2023-01-01,
- § 12 Absatz 6 WoGG (Entlastung bei den Heizkosten), in force 2023-01-01,

and are repeated literally so that a change to `data/wogg_parameters.csv` cannot pass
unnoticed.
"""

import numpy as np
import pandas as pd
import pytest

from kdu.data_management.wohngeld import (
    HOUSEHOLD_SIZES,
    KDU_GEMEINDEN_PATH,
    WOGG_PARAMETERS_PATH,
    WoggParameters,
    build_wogg_benchmark,
    load_wogg_parameters,
    read_kdu_gemeinden,
    reshape_kdu_caps_to_long,
)

OFFICIAL_BASE_CAP = {
    1: (361, 408, 456, 511, 562, 615, 677),
    2: (437, 493, 551, 619, 680, 745, 820),
    3: (521, 587, 657, 737, 809, 887, 975),
    4: (608, 686, 766, 858, 946, 1035, 1139),
    5: (694, 782, 875, 982, 1080, 1183, 1302),
}
OFFICIAL_CLIMATE_COMPONENT = {1: 19.20, 2: 24.80, 3: 29.60, 4: 34.40, 5: 39.20}
OFFICIAL_HEATING_RELIEF = {1: 110.40, 2: 142.60, 3: 170.20, 4: 197.80, 5: 225.40}


@pytest.fixture(scope="module")
def parameters() -> WoggParameters:
    """The committed § 12 WoGG parameter table."""
    return load_wogg_parameters(WOGG_PARAMETERS_PATH)


@pytest.fixture(scope="module")
def raw_kdu() -> pd.DataFrame:
    """The committed wide KdU table with an eight-digit string AGS."""
    return read_kdu_gemeinden(KDU_GEMEINDEN_PATH)


@pytest.mark.parametrize("household_size", sorted(OFFICIAL_BASE_CAP))
@pytest.mark.parametrize("rent_level", range(1, 8))
def test_base_cap_matches_official_anlage_1(
    parameters: WoggParameters, rent_level: int, household_size: int
) -> None:
    """Every Mietenstufe and household size reproduces Anlage 1 WoGG."""
    expected = OFFICIAL_BASE_CAP[household_size][rent_level - 1]
    assert parameters.base_cap_for(rent_level, household_size) == expected


@pytest.mark.parametrize("household_size", sorted(OFFICIAL_CLIMATE_COMPONENT))
def test_climate_component_matches_statute(
    parameters: WoggParameters, household_size: int
) -> None:
    """The Klimakomponente reproduces § 12 Absatz 7 WoGG."""
    assert parameters.climate_component[household_size] == pytest.approx(
        OFFICIAL_CLIMATE_COMPONENT[household_size]
    )


@pytest.mark.parametrize("household_size", sorted(OFFICIAL_HEATING_RELIEF))
def test_heating_relief_matches_statute(
    parameters: WoggParameters, household_size: int
) -> None:
    """The Heizkostenentlastung reproduces § 12 Absatz 6 WoGG."""
    assert parameters.heating_relief[household_size] == pytest.approx(
        OFFICIAL_HEATING_RELIEF[household_size]
    )


def test_every_parameter_row_cites_a_legal_source(parameters: WoggParameters) -> None:
    """No parameter enters the benchmark without a citation and a vintage."""
    assert all(
        source and vintage for source, vintage in parameters.legal_sources.values()
    )


@pytest.mark.parametrize("household_size", [1, 2, 4])
def test_base_cap_reproduces_committed_hoechstbetrag_columns(
    parameters: WoggParameters, raw_kdu: pd.DataFrame, household_size: int
) -> None:
    """The reconstructed base cap equals `wogg_hoechstbetrag_eur_*` everywhere.

    Holds for every Gemeinde with a non-null `wogv_mietstufe`. A mismatch is a finding
    about the committed data, never a reason to change the parameter table.
    """
    benchmark = build_wogg_benchmark(raw_kdu, parameters)
    committed = raw_kdu.loc[
        raw_kdu["wogv_mietstufe"].notna(),
        ["ags", f"wogg_hoechstbetrag_eur_{household_size}p"],
    ]
    merged = committed.merge(
        benchmark.query("household_size == @household_size"),
        on="ags",
        how="left",
    )
    pd.testing.assert_series_equal(
        merged["wogg_base_cap"].astype("float64"),
        merged[f"wogg_hoechstbetrag_eur_{household_size}p"].astype("float64"),
        check_names=False,
    )


def test_bkc_cap_is_base_plus_climate(
    parameters: WoggParameters, raw_kdu: pd.DataFrame
) -> None:
    """`wogg_bkc_cap` is exactly the base Höchstbetrag plus the Klimakomponente."""
    benchmark = build_wogg_benchmark(raw_kdu, parameters)
    np.testing.assert_allclose(
        benchmark["wogg_bkc_cap"].dropna(),
        (benchmark["wogg_base_cap"] + benchmark["wogg_climate_component"]).dropna(),
        atol=1e-9,
    )


def test_heating_relief_never_enters_either_benchmark(
    parameters: WoggParameters, raw_kdu: pd.DataFrame
) -> None:
    """Neither the primary nor the robustness benchmark contains the heating relief."""
    benchmark = build_wogg_benchmark(raw_kdu, parameters).dropna(
        subset=["wogg_base_cap"]
    )
    difference = benchmark["wogg_bkc_cap"] - benchmark["wogg_base_cap"]
    assert (difference < benchmark["wogg_heating_relief"]).all()


def test_benchmark_is_keyed_by_ags_and_household_size(
    parameters: WoggParameters, raw_kdu: pd.DataFrame
) -> None:
    """The long table has exactly one row per Gemeinde and household size."""
    benchmark = build_wogg_benchmark(raw_kdu, parameters)
    assert len(benchmark) == len(raw_kdu) * len(HOUSEHOLD_SIZES)
    assert not benchmark.duplicated(subset=["ags", "household_size"]).any()


def test_rent_level_is_read_from_wogv_mietstufe_not_wogg_mietstufe(
    parameters: WoggParameters,
) -> None:
    """A KdU document's Mietstufe never overrides the statutory one."""
    frame = pd.DataFrame(
        {
            "ags": pd.array(["01001000"], dtype="string"),
            "wogv_mietstufe": pd.array([3], dtype="Int64"),
            "wogg_mietstufe": pd.array([7], dtype="Int64"),
        }
    )
    benchmark = build_wogg_benchmark(frame, parameters)
    assert benchmark.query("household_size == 1")["wogg_rent_level"].item() == 3


def test_rent_level_is_not_derived_from_kreis_or_population(
    parameters: WoggParameters,
) -> None:
    """Neither Kreis membership nor population may enter the Mietenstufe lookup.

    Two Gemeinden in the same Kreis with different statutory Mietenstufen keep their own
    rent level, and the benchmark builds on a frame that carries no Kreis and no
    population column at all.
    """
    frame = pd.DataFrame(
        {
            "ags": pd.array(["09171111", "09171222"], dtype="string"),
            "wogv_mietstufe": pd.array([1, 6], dtype="Int64"),
        }
    )
    benchmark = build_wogg_benchmark(frame, parameters).query("household_size == 1")
    assert benchmark["wogg_base_cap"].tolist() == [361, 615]


def test_missing_rent_level_is_flagged_and_kept(parameters: WoggParameters) -> None:
    """A Gemeinde without a statutory Mietenstufe is kept with a null cap and a flag."""
    frame = pd.DataFrame(
        {
            "ags": pd.array(["09999999"], dtype="string"),
            "wogv_mietstufe": pd.array([None], dtype="Int64"),
        }
    )
    benchmark = build_wogg_benchmark(frame, parameters)
    assert benchmark["wogg_rent_level_missing"].all()
    assert benchmark["wogg_base_cap"].isna().all()


def test_parameter_vintage_is_recorded_on_every_row(
    parameters: WoggParameters, raw_kdu: pd.DataFrame
) -> None:
    """`wogg_parameter_vintage` labels the Rechtsstand of every benchmark row."""
    benchmark = build_wogg_benchmark(raw_kdu, parameters)
    vintages = set(benchmark["wogg_parameter_vintage"])
    assert len(vintages) == 1
    assert "2025-01-01" in vintages.pop()


def test_kdu_vs_wogg_pct_primary_measures_against_the_base_cap_alone(
    parameters: WoggParameters,
) -> None:
    """The primary proxy error divides by `wogg_base_cap`, per D6."""
    frame = pd.DataFrame(
        {
            "ags": pd.array(["09171111"], dtype="string"),
            "wogv_mietstufe": pd.array([1], dtype="Int64"),
            "max_bruttokaltmiete_eur_1p": pd.array([397.1], dtype="Float64"),
        }
    )
    kdu_caps = reshape_kdu_caps_to_long(frame)
    benchmark = build_wogg_benchmark(frame, parameters, kdu_caps=kdu_caps)
    row = benchmark.query("household_size == 1").iloc[0]
    assert row["kdu_vs_wogg_pct_primary"] == pytest.approx(10.0, abs=1e-6)


def test_kdu_vs_wogg_pct_klima_measures_against_base_plus_climate(
    parameters: WoggParameters,
) -> None:
    """The robustness proxy error divides by `wogg_bkc_cap`."""
    frame = pd.DataFrame(
        {
            "ags": pd.array(["09171111"], dtype="string"),
            "wogv_mietstufe": pd.array([1], dtype="Int64"),
            "max_bruttokaltmiete_eur_1p": pd.array([380.2], dtype="Float64"),
        }
    )
    kdu_caps = reshape_kdu_caps_to_long(frame)
    benchmark = build_wogg_benchmark(frame, parameters, kdu_caps=kdu_caps)
    row = benchmark.query("household_size == 1").iloc[0]
    expected = 100 * (380.2 / (361 + 19.20) - 1)
    assert row["kdu_vs_wogg_pct_klima"] == pytest.approx(expected, abs=1e-6)


def test_reshape_kdu_caps_to_long_covers_all_five_household_sizes(
    raw_kdu: pd.DataFrame,
) -> None:
    """Every household size 1 to 5 appears in the long KdU cap table."""
    long_caps = reshape_kdu_caps_to_long(raw_kdu)
    assert sorted(long_caps["household_size"].unique()) == list(HOUSEHOLD_SIZES)


def test_primary_cap_is_the_base_cap_times_the_safety_markup(
    parameters: WoggParameters, raw_kdu: pd.DataFrame
) -> None:
    """`wogg_primary_cap` is the § 12 WoGG table plus the Sicherheitszuschlag (D15)."""
    benchmark = build_wogg_benchmark(raw_kdu, parameters)
    np.testing.assert_allclose(
        benchmark["wogg_primary_cap"].dropna(),
        benchmark["wogg_base_cap"].dropna() * 1.10,
        atol=1e-9,
    )
