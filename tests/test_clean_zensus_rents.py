"""Reading the Zensus 2022 rents at the resolution the local caps are set at."""

import pandas as pd
import pytest

from kdu.data_management.clean_zensus_rents import (
    _to_numeric,
    fail_if_measure_names_claim_availability,
    to_gemeinde_ags,
)


def test_regionalschluessel_reduces_to_the_eight_digit_ags() -> None:
    """Flensburg's `010010000000` is the AGS `01001000`."""
    result = to_gemeinde_ags(pd.Series(["010010000000"]))
    assert result.iloc[0] == "01001000"


def test_a_dash_means_nothing_to_report_and_becomes_zero() -> None:
    """The Zensus writes `–` where a rent class holds no dwelling."""
    assert _to_numeric(pd.Series(["–"])).iloc[0] == pytest.approx(0.0)


def test_a_dot_marks_an_unpublished_value_and_becomes_missing() -> None:
    """A withheld cell is missing, never zero: the dwellings exist but are not counted."""
    assert pd.isna(_to_numeric(pd.Series(["."])).iloc[0])


def test_a_german_decimal_comma_is_read_as_a_decimal_point() -> None:
    """`6,96` euro per square metre is 6.96, not 696."""
    assert _to_numeric(pd.Series(["6,96"])).iloc[0] == pytest.approx(6.96)


def test_a_measure_name_claiming_availability_is_rejected() -> None:
    """A Bestandsmiete carries no statement about what a searching household finds."""
    with pytest.raises(ValueError, match="availability"):
        fail_if_measure_names_claim_availability(pd.Series(["dwellings_available"]))
