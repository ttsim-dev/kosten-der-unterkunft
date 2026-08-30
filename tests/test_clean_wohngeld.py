"""The statutory benchmark each local KdU cap is measured against."""

from types import MappingProxyType

import pandas as pd
import pytest

from kdu.data_management.clean_wohngeld import (
    WohngeldParameters,
    build_hoechstbetrag_only,
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
    result = build_hoechstbetrag_only(_mietenstufen(), _parameters())
    row = result.query("ags == '01001000' and household_size == 2")
    assert row["wohngeld_hoechstbetrag"].iloc[0] == pytest.approx(600.0)


def test_fallback_cap_is_the_hoechstbetrag_plus_ten_percent() -> None:
    """The BSG fallback on a Höchstbetrag of 500 € is 550 €."""
    suspected = pd.DataFrame(
        {"ags": ["01001000"], "wohngeld_rule_suspected": [False]},
    )
    result = build_wohngeld_fallback(_mietenstufen(), _parameters(), suspected)
    row = result.query("ags == '01001000' and household_size == 1")
    assert row["wohngeld_fallback_cap"].iloc[0] == pytest.approx(550.0)


def test_a_gemeinde_without_a_mietenstufe_keeps_its_rows_with_no_benchmark() -> None:
    """A gemeindefreies Gebiet has no statutory Mietenstufe and is never dropped."""
    mietenstufen = pd.DataFrame(
        {
            "ags": pd.array(["09999999"], dtype="string"),
            "mietenstufe": pd.array([None], dtype="Int64"),
        },
    )
    suspected = pd.DataFrame({"ags": [], "wohngeld_rule_suspected": []})
    result = build_wohngeld_fallback(mietenstufen, _parameters(), suspected)
    assert set(result["ags"]) == {"09999999"}
    assert result["wohngeld_fallback_cap"].isna().all()


def test_a_gemeinde_absent_from_the_suspicion_table_is_not_suspected() -> None:
    """Absence of evidence is recorded as no suspicion, never as missing."""
    suspected = pd.DataFrame({"ags": [], "wohngeld_rule_suspected": []})
    result = build_wohngeld_fallback(_mietenstufen(), _parameters(), suspected)
    assert not result["wohngeld_rule_suspected"].any()
