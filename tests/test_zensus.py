import numpy as np
import pandas as pd
import pytest

from kdu.data_management.zensus import (
    FLOOR_AREA_CLASS_MEASURES,
    RENT_CLASS_MEASURES,
    SCALAR_MEASURES,
    ZENSUS_REFERENCE_DATE,
    add_ags_eight_digit,
    build_zensus_rents,
    fail_if_measure_names_claim_availability,
    normalise_regionalschluessel,
    select_gemeinden,
)


def _raw() -> pd.DataFrame:
    columns = {
        "_RS": ["1", "1001", "10010000000"],
        "Name": ["Schleswig-Holstein", "Flensburg, Stadt", "Flensburg, Stadt"],
        "Regionalebene": [
            "Land",
            "Stadtkreis/kreisfreie Stadt/Landkreis",
            "Gemeinde",
        ],
    }
    frame = pd.DataFrame(columns)
    numeric = {**SCALAR_MEASURES, **RENT_CLASS_MEASURES, **FLOOR_AREA_CLASS_MEASURES}
    for position, code in enumerate(numeric, start=1):
        frame[code] = [str(position), str(position * 2), str(position * 2)]
    frame["QMMIETE"] = ["7.41", "6.96", "6.96"]
    frame["MIETE_EURM2_2__01"] = ["1000", "–", "–"]
    frame["MIETE_EURM2_2__02"] = ["2000", ".", "."]
    return frame


def test_build_zensus_rents_keeps_the_mean_nettokaltmiete_per_square_metre():
    long_frame = build_zensus_rents(_raw())
    value = long_frame.query(
        "ags == '010010000000' "
        "and measure == 'bestandsmiete_nettokalt_eur_per_sqm_mean'"
    )["value"]
    assert value.to_numpy() == pytest.approx([6.96])


def test_build_zensus_rents_stamps_the_census_reference_date():
    long_frame = build_zensus_rents(_raw())
    assert set(long_frame["reference_date"]) == {ZENSUS_REFERENCE_DATE}


def test_build_zensus_rents_classifies_a_kreis_row_by_its_label_prefix():
    long_frame = build_zensus_rents(_raw())
    levels = long_frame.query("region_name == 'Flensburg, Stadt'")["region_level"]
    assert set(levels) == {"kreis", "gemeinde"}


def test_build_zensus_rents_reads_a_dash_as_zero():
    long_frame = build_zensus_rents(_raw())
    value = long_frame.query(
        "ags == '010010000000' "
        "and measure == 'dwellings_bestandsmiete_eur_per_sqm_under_4'"
    )["value"]
    assert value.to_numpy() == pytest.approx([0.0])


def test_build_zensus_rents_reads_a_withheld_value_as_missing():
    long_frame = build_zensus_rents(_raw())
    value = long_frame.query(
        "ags == '010010000000' "
        "and measure == 'dwellings_bestandsmiete_eur_per_sqm_4_to_6'"
    )["value"]
    assert np.isnan(value.to_numpy()[0])


def test_normalise_regionalschluessel_restores_the_leading_zero_of_a_land():
    padded = normalise_regionalschluessel(pd.Series(["1"]), pd.Series(["land"]))
    assert padded.to_list() == ["01"]


def test_normalise_regionalschluessel_pads_a_gemeinde_to_twelve_digits():
    padded = normalise_regionalschluessel(
        pd.Series(["10010000000"]), pd.Series(["gemeinde"])
    )
    assert padded.to_list() == ["010010000000"]


def test_select_gemeinden_drops_the_kreis_row_of_a_kreisfreie_stadt():
    gemeinden = select_gemeinden(build_zensus_rents(_raw()))
    assert set(gemeinden["region_level"]) == {"gemeinde"}


def test_add_ags_eight_digit_drops_the_verbandsschluessel():
    gemeinden = add_ags_eight_digit(select_gemeinden(build_zensus_rents(_raw())))
    assert set(gemeinden["ags_gemeinde"]) == {"01001000"}


def test_fail_if_measure_names_claim_availability_rejects_an_availability_name():
    with pytest.raises(ValueError, match="must not claim availability"):
        fail_if_measure_names_claim_availability(
            pd.Series(["share_of_available_dwellings"])
        )


def test_fail_if_measure_names_claim_availability_rejects_an_angebotsmiete_name():
    with pytest.raises(ValueError, match="must not claim availability"):
        fail_if_measure_names_claim_availability(
            pd.Series(["angebotsmiete_eur_per_sqm"])
        )


def test_fail_if_measure_names_claim_availability_accepts_the_bestandsmiete_name():
    fail_if_measure_names_claim_availability(
        pd.Series(["bestandsmiete_nettokalt_eur_per_sqm_mean"])
    )
