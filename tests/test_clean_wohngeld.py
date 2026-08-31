"""The statutory benchmark each local KdU cap is measured against."""

from types import MappingProxyType

import pandas as pd
import pytest

from kdu.data_management.clean_wohngeld import (
    WohngeldParameters,
    build_wohngeld_fallback,
)


def _parameters() -> WohngeldParameters:
    """Two Mietenstufen at two household sizes, with round amounts."""
    return WohngeldParameters(
        hoechstbetrag=MappingProxyType(
            {
                (1, 1): 400.0,
                (1, 2): 480.0,
                (3, 1): 500.0,
                (3, 2): 600.0,
            },
        ),
        klimakomponente=MappingProxyType({1: 20.0, 2: 25.0}),
        legal_sources=MappingProxyType({"base_cap": ("Anlage 1 WoGG", "2025-01-01")}),
    )


def _mietenstufen() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ags": pd.array(["01001000", "01002000"], dtype="string"),
            "mietenstufe": pd.array([3, 1], dtype="Int64"),
        },
    )


def test_hoechstbetrag_is_looked_up_by_mietenstufe_and_household_size() -> None:
    """Mietenstufe 3 at household size 2 reads 600 € from the Anlage 1 table."""
    result = build_wohngeld_fallback(_mietenstufen(), _parameters())
    row = result.query("ags == '01001000' and household_size == 2")
    assert row["wohngeld_hoechstbetrag"].iloc[0] == pytest.approx(600.0)


def test_fallback_cap_adds_the_klimakomponente_before_the_ten_percent() -> None:
    """A Höchstbetrag of 500 € plus a Klimakomponente of 20 € gives 572 €."""
    result = build_wohngeld_fallback(_mietenstufen(), _parameters())
    row = result.query("ags == '01001000' and household_size == 1")
    assert row["wohngeld_fallback_cap"].iloc[0] == pytest.approx(572.0)


def test_klimakomponente_is_carried_alongside_the_hoechstbetrag() -> None:
    """The two parts of the benchmark stay separately readable in the table."""
    result = build_wohngeld_fallback(_mietenstufen(), _parameters())
    row = result.query("ags == '01001000' and household_size == 2")
    assert row["wohngeld_klimakomponente"].iloc[0] == pytest.approx(25.0)


def test_klimakomponente_does_not_vary_by_mietenstufe() -> None:
    """§ 12 Absatz 7 WoGG sets one amount per household size for every Mietenstufe."""
    result = build_wohngeld_fallback(_mietenstufen(), _parameters())
    at_size_one = result.query("household_size == 1")["wohngeld_klimakomponente"]
    assert set(at_size_one) == {20.0}


def test_a_gemeinde_without_a_mietenstufe_keeps_its_rows_with_no_benchmark() -> None:
    """A gemeindefreies Gebiet has no statutory Mietenstufe and is never dropped."""
    mietenstufen = pd.DataFrame(
        {
            "ags": pd.array(["09999999"], dtype="string"),
            "mietenstufe": pd.array([None], dtype="Int64"),
        },
    )
    result = build_wohngeld_fallback(mietenstufen, _parameters())
    assert set(result["ags"]) == {"09999999"}
    assert result["wohngeld_fallback_cap"].isna().all()
