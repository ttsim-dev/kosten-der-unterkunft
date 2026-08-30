import numpy as np
import pandas as pd
import pytest

from kdu.data_management.ba import (
    BG_TYPE_CATEGORIES,
    HOUSEHOLD_SIZE_CATEGORIES,
    BaWorkbookIdentity,
    add_bruttokaltmiete,
    add_jobcenter_id,
    average_over_months,
    build_ba_outcomes,
    build_jobcenter_kreis_crosswalk,
    check_jobcenter_kreis_stocks,
    fail_if_measure_names_suggest_payment,
    gather_categories,
    normalise_region_label,
    parse_ba_sheet,
    read_committed_extract,
    split_validation_samples,
    spread_categories,
    summarise_extended_sample,
)

IDENTITY = BaWorkbookIdentity(
    region_level="kreis",
    region_code="05334",
    region_label="Aachen, Städteregion",
    reference_month="2026-04",
)


def _sheet_rows() -> list[tuple[object, ...]]:
    """Reproduce the row shape of `Tabelle 1b HH Miete` with seven data columns."""
    return [
        (
            "Tabelle 1b: Wohn- und Wohnkostensituation",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ),
        ("Bestand Bedarfsgemeinschaften", None, None, None, None, None, None, None),
        ("     Bestand Bedarfsgemeinschaften (BG)", 700, 100, 100, 100, 100, 100, 200),
        ("     Anteil der jeweiligen Haushaltsgröße in %", 100, 14, 14, 14, 14, 14, 28),
        ("     durchschnittliche Wohnfläche pro BG 4)", 70, 50, 60, 70, 80, 90, 100),
        (
            "Lfd. Kosten der Unterkunft (in Euro) 2) 3) 4) 6)",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ),
        (
            "     Laufende tatsächliche Kosten der Unterkunft insgesamt",
            7000,
            1000,
            1000,
            1000,
            1000,
            1000,
            2000,
        ),
        ("     pro BG", 600, 500, 550, 600, 650, 700, 750),
        ("     pro qm", 10, 10, 10, 10, 10, 10, 10),
        ("     dav. Unterkunftskosten 7)", 4900, 700, 700, 700, 700, 700, 1400),
        ("          pro BG", 400, 300, 350, 400, 450, 500, 550),
        ("          pro qm", 7, 7, 7, 7, 7, 7, 7),
        ("     dav. laufende Betriebskosten 7)", 1400, 200, 200, 200, 200, 200, 400),
        ("          pro BG", 120, 100, 110, 120, 130, 140, 150),
        ("          pro qm", 2, 2, 2, 2, 2, 2, 2),
        ("     dav. Heizkosten", 700, 100, 100, 100, 100, 100, 200),
        ("          pro BG", 80, 70, 75, 80, 85, 90, 95),
        ("          pro qm", 1, 1, 1, 1, 1, 1, 1),
        (
            "     Laufende anerkannte Kosten der Unterkunft insgesamt",
            6800,
            950,
            950,
            950,
            950,
            950,
            1900,
        ),
        ("     pro BG", 570, 480, 520, 570, 620, 660, 700),
        ("     pro qm", 9, 9, 9, 9, 9, 9, 9),
        ("     dav. Unterkunftskosten 7)", 4700, 650, 650, 650, 650, 650, 1300),
        ("          pro BG", 380, 285, 330, 380, 430, 470, 500),
        ("          pro qm", 6, 6, 6, 6, 6, 6, 6),
        ("     dav. laufende Betriebskosten 7)", 1300, 190, 190, 190, 190, 190, 380),
        ("          pro BG", 110, 95, 100, 110, 120, 130, 140),
        ("          pro qm", 2, 2, 2, 2, 2, 2, 2),
        ("     dav. Heizkosten", 680, 95, 95, 95, 95, 95, 190),
        ("          pro BG", 75, 65, 70, 75, 80, 85, 90),
        ("          pro qm", 1, 1, 1, 1, 1, 1, 1),
    ]


@pytest.fixture
def long_frame() -> pd.DataFrame:
    return add_bruttokaltmiete(
        parse_ba_sheet(_sheet_rows(), "household_size", IDENTITY)
    )


def test_parse_ba_sheet_reads_indented_row_under_its_cost_component():
    frame = parse_ba_sheet(_sheet_rows(), "household_size", IDENTITY)
    value = frame.query(
        "measure == 'actual_unterkunftskosten_eur_per_bg' and category == '1_person'"
    )["value"]
    assert value.to_numpy() == pytest.approx([300.0])


def test_parse_ba_sheet_reads_top_level_row_under_the_cost_concept():
    frame = parse_ba_sheet(_sheet_rows(), "household_size", IDENTITY)
    value = frame.query(
        "measure == 'recognised_kdu_total_eur_per_bg' and category == '2_persons'"
    )["value"]
    assert value.to_numpy() == pytest.approx([520.0])


def test_parse_ba_sheet_labels_every_category_of_the_breakdown():
    frame = parse_ba_sheet(_sheet_rows(), "household_size", IDENTITY)
    assert tuple(frame["category"].unique()) == HOUSEHOLD_SIZE_CATEGORIES


def test_parse_ba_sheet_uses_bg_type_categories_for_the_second_breakdown():
    frame = parse_ba_sheet(_sheet_rows(), "bg_type", IDENTITY)
    assert tuple(frame["category"].unique()) == BG_TYPE_CATEGORIES


def test_parse_ba_sheet_ignores_percentage_share_rows():
    frame = parse_ba_sheet(_sheet_rows(), "household_size", IDENTITY)
    assert not frame["measure"].str.contains("Anteil").any()


def test_parse_ba_sheet_reads_a_withheld_value_as_missing():
    rows = [
        ("     Bestand Bedarfsgemeinschaften (BG)", 700, "*", 100, 100, 100, 100, 200)
    ]
    frame = parse_ba_sheet(rows, "household_size", IDENTITY)
    value = frame.query("category == '1_person'")["value"]
    assert np.isnan(value.to_numpy()[0])


def test_parse_ba_sheet_reads_a_dash_as_zero():
    rows = [
        ("     Bestand Bedarfsgemeinschaften (BG)", 700, "–", 100, 100, 100, 100, 200)
    ]
    frame = parse_ba_sheet(rows, "household_size", IDENTITY)
    assert frame.query("category == '1_person'")["value"].to_numpy() == pytest.approx(
        [0.0]
    )


def test_parse_ba_sheet_rejects_an_unknown_breakdown():
    with pytest.raises(ValueError, match="breakdown must be"):
        parse_ba_sheet(_sheet_rows(), "by_bundesland", IDENTITY)


def test_add_bruttokaltmiete_sums_unterkunftskosten_and_kalte_betriebskosten(
    long_frame,
):
    value = long_frame.query(
        "measure == 'actual_bruttokaltmiete_eur_per_bg' and category == '4_persons'"
    )["value"]
    assert value.to_numpy() == pytest.approx([450.0 + 130.0])


def test_add_bruttokaltmiete_leaves_heizkosten_out(long_frame):
    per_sqm = long_frame.query(
        "measure == 'recognised_bruttokaltmiete_eur_per_sqm' and category == 'total'"
    )["value"]
    assert per_sqm.to_numpy() == pytest.approx([6.0 + 2.0])


def test_build_ba_outcomes_reports_the_euro_gap_between_the_two_cost_concepts(
    long_frame,
):
    outcome = build_ba_outcomes(long_frame).query(
        "outcome == 'ba_gap_eur' and cost_component == 'kdu_total' "
        "and basis == 'per_bg' and category == '1_person'"
    )["value"]
    assert outcome.to_numpy() == pytest.approx([500.0 - 480.0])


def test_build_ba_outcomes_reports_the_recognition_rate(long_frame):
    outcome = build_ba_outcomes(long_frame).query(
        "outcome == 'ba_recognition_rate' and cost_component == 'kdu_total' "
        "and basis == 'per_bg' and category == '1_person'"
    )["value"]
    assert outcome.to_numpy() == pytest.approx([480.0 / 500.0])


def test_build_ba_outcomes_reports_the_non_recognised_share(long_frame):
    outcome = build_ba_outcomes(long_frame).query(
        "outcome == 'ba_non_recognised_share' and cost_component == 'kdu_total' "
        "and basis == 'per_bg' and category == '1_person'"
    )["value"]
    assert outcome.to_numpy() == pytest.approx([1.0 - 480.0 / 500.0])


def test_build_ba_outcomes_does_not_invent_categories_across_breakdowns():
    both = pd.concat(
        [
            parse_ba_sheet(_sheet_rows(), "household_size", IDENTITY),
            parse_ba_sheet(_sheet_rows(), "bg_type", IDENTITY),
        ],
        ignore_index=True,
    )
    outcomes = build_ba_outcomes(add_bruttokaltmiete(both))
    household = outcomes.query("breakdown == 'household_size'")
    assert set(household["category"]) == set(HOUSEHOLD_SIZE_CATEGORIES)


def test_fail_if_measure_names_suggest_payment_rejects_a_benefit_name():
    with pytest.raises(ValueError, match="must not suggest disbursed benefits"):
        fail_if_measure_names_suggest_payment(pd.Series(["kdu_benefit_eur_per_bg"]))


def test_fail_if_measure_names_suggest_payment_accepts_the_recognised_name():
    fail_if_measure_names_suggest_payment(
        pd.Series(["recognised_bruttokaltmiete_eur_per_bg"])
    )


def test_spread_categories_round_trips_through_gather_categories(long_frame):
    wide = spread_categories(long_frame, "household_size")
    recovered = gather_categories(wide, "household_size")
    expected = long_frame.sort_values(["measure", "category"]).reset_index(drop=True)
    actual = recovered.sort_values(["measure", "category"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(actual[expected.columns], expected, check_dtype=False)


def test_average_over_months_averages_matching_cells():
    january = parse_ba_sheet(_sheet_rows(), "household_size", IDENTITY)
    february = january.assign(reference_month="2026-05", value=january["value"] + 10.0)
    averaged = average_over_months([january, february], "2026-04..2026-05")
    value = averaged.query(
        "measure == 'actual_kdu_total_eur_per_bg' and category == '1_person'"
    )["value"]
    assert value.to_numpy() == pytest.approx([505.0])


def test_average_over_months_counts_the_contributing_months():
    january = parse_ba_sheet(_sheet_rows(), "household_size", IDENTITY)
    february = january.assign(reference_month="2026-05")
    averaged = average_over_months([january, february], "2026-04..2026-05")
    counts = averaged.query("measure == 'actual_kdu_total_eur_per_bg'")["n_months"]
    assert set(counts) == {2}


def _regions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "region_level": ["kreis", "kreis", "jobcenter", "jobcenter"],
            "region_code": ["05334", "05370", "t31108", "t31109"],
            "region_label": [
                "Aachen, Städteregion",
                "Düren",
                "Aachen, Städteregion, JC",
                "Düren, JC",
            ],
        }
    )


def test_build_jobcenter_kreis_crosswalk_matches_a_jobcenter_to_its_kreis():
    crosswalk = build_jobcenter_kreis_crosswalk(_regions())
    row = crosswalk.query("jobcenter_id == 't31108'")
    assert row["ags_kreis"].to_numpy() == np.array(["05334"])


def test_build_jobcenter_kreis_crosswalk_counts_one_policy_region_per_jobcenter():
    crosswalk = build_jobcenter_kreis_crosswalk(_regions())
    assert set(crosswalk["n_policy_regions"]) == {1}


def test_split_validation_samples_puts_a_single_region_jobcenter_in_the_main_sample():
    crosswalk = build_jobcenter_kreis_crosswalk(_regions())
    samples = split_validation_samples(crosswalk, kreisfrei_ags=[], uniform_caps={})
    assert set(samples["sample"]) == {"main"}


def test_split_validation_samples_puts_a_multi_region_jobcenter_in_the_extended_sample():
    crosswalk = pd.DataFrame(
        {
            "jobcenter_id": ["t1", "t1"],
            "jobcenter_label": ["Doppelkreis, JC", "Doppelkreis, JC"],
            "kreis_label": ["A", "B"],
            "ags_kreis": ["01001", "01002"],
            "n_policy_regions": [2, 2],
        }
    )
    samples = split_validation_samples(crosswalk, kreisfrei_ags=[], uniform_caps={})
    assert set(samples["sample"]) == {"extended"}


def test_split_validation_samples_keeps_a_uniform_rule_jobcenter_in_the_main_sample():
    crosswalk = pd.DataFrame(
        {
            "jobcenter_id": ["t1", "t1"],
            "jobcenter_label": ["Doppelkreis, JC", "Doppelkreis, JC"],
            "kreis_label": ["A", "B"],
            "ags_kreis": ["01001", "01002"],
            "n_policy_regions": [2, 2],
        }
    )
    samples = split_validation_samples(
        crosswalk, kreisfrei_ags=[], uniform_caps={"01001": 400.0, "01002": 400.0}
    )
    assert set(samples["sample"]) == {"main"}


def test_summarise_extended_sample_weights_the_cap_by_population():
    crosswalk = pd.DataFrame(
        {
            "jobcenter_id": ["t1", "t1"],
            "jobcenter_label": ["Doppelkreis, JC", "Doppelkreis, JC"],
            "kreis_label": ["A", "B"],
            "ags_kreis": ["01001", "01002"],
            "n_policy_regions": [2, 2],
            "sample": ["extended", "extended"],
        }
    )
    kdu = pd.DataFrame(
        {
            "ags_kreis": ["01001", "01002"],
            "population": [300.0, 100.0],
            "cap": [400.0, 800.0],
        }
    )
    summary = summarise_extended_sample(crosswalk, kdu, "cap")
    assert summary["kdu_mean_weighted"].to_numpy() == pytest.approx([500.0])


def test_summarise_extended_sample_reports_the_within_jobcenter_spread():
    crosswalk = pd.DataFrame(
        {
            "jobcenter_id": ["t1", "t1"],
            "jobcenter_label": ["Doppelkreis, JC", "Doppelkreis, JC"],
            "kreis_label": ["A", "B"],
            "ags_kreis": ["01001", "01002"],
            "n_policy_regions": [2, 2],
            "sample": ["extended", "extended"],
        }
    )
    kdu = pd.DataFrame(
        {
            "ags_kreis": ["01001", "01002"],
            "population": [300.0, 100.0],
            "cap": [400.0, 800.0],
        }
    )
    summary = summarise_extended_sample(crosswalk, kdu, "cap")
    assert summary["kdu_max"].to_numpy() - summary["kdu_min"].to_numpy() == (
        pytest.approx([400.0])
    )


def test_normalise_region_label_folds_hyphen_spacing_and_the_jc_suffix():
    folded = normalise_region_label(pd.Series(["Alb - Donau - Kreis, JC"]))
    assert folded.to_list() == ["alb-donau-kreis"]


def test_build_jobcenter_kreis_crosswalk_matches_across_a_stadt_qualifier():
    regions = pd.DataFrame(
        {
            "region_level": ["kreis", "jobcenter"],
            "region_code": ["05114", "t36102"],
            "region_label": ["Krefeld, Stadt", "Krefeld, JC"],
        }
    )
    crosswalk = build_jobcenter_kreis_crosswalk(regions)
    assert crosswalk["ags_kreis"].to_list() == ["05114"]


def test_build_jobcenter_kreis_crosswalk_expands_a_multi_kreis_jobcenter():
    regions = pd.DataFrame(
        {
            "region_level": ["kreis"] * 4 + ["jobcenter"],
            "region_code": ["07311", "07314", "07318", "07338", "t52302"],
            "region_label": [
                "Frankenthal (Pfalz), Stadt",
                "Ludwigshafen am Rhein, Stadt",
                "Speyer, Stadt",
                "Rhein - Pfalz - Kreis",
                "Vorderpfalz - Ludwigshafen, JC",
            ],
        }
    )
    crosswalk = build_jobcenter_kreis_crosswalk(regions)
    assert crosswalk["ags_kreis"].to_list() == ["07311", "07314", "07318", "07338"]


def test_build_jobcenter_kreis_crosswalk_maps_every_berlin_jobcenter_to_one_kreis():
    regions = pd.DataFrame(
        {
            "region_level": ["kreis", "jobcenter", "jobcenter"],
            "region_code": ["11000", "t96204", "t95504"],
            "region_label": ["Berlin, Stadt", "Mitte, JC", "Pankow, JC"],
        }
    )
    crosswalk = build_jobcenter_kreis_crosswalk(regions)
    assert set(crosswalk["ags_kreis"]) == {"11000"}


def test_build_jobcenter_kreis_crosswalk_counts_one_policy_region_for_a_berlin_bezirk():
    regions = pd.DataFrame(
        {
            "region_level": ["kreis", "jobcenter", "jobcenter"],
            "region_code": ["11000", "t96204", "t95504"],
            "region_label": ["Berlin, Stadt", "Mitte, JC", "Pankow, JC"],
        }
    )
    crosswalk = build_jobcenter_kreis_crosswalk(regions)
    assert set(crosswalk["n_policy_regions"]) == {1}


def _stock_rows(codes_and_stocks: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "region_code": list(codes_and_stocks),
            "value": list(codes_and_stocks.values()),
            "measure": "bg_stock",
            "breakdown": "household_size",
            "category": "total",
        }
    )


def test_check_jobcenter_kreis_stocks_finds_no_gap_when_territories_tile():
    crosswalk = pd.DataFrame(
        {
            "jobcenter_id": ["t1", "t1"],
            "jobcenter_label": ["Zwei, JC", "Zwei, JC"],
            "ags_kreis": ["01001", "01002"],
            "kreis_label": ["A", "B"],
            "n_policy_regions": [2, 2],
        }
    )
    stocks = _stock_rows({"t1": 300.0, "01001": 100.0, "01002": 200.0})
    check = check_jobcenter_kreis_stocks(crosswalk, stocks)
    assert check["difference"].to_numpy() == pytest.approx([0.0])


def test_check_jobcenter_kreis_stocks_sums_several_jobcenter_over_one_kreis():
    crosswalk = pd.DataFrame(
        {
            "jobcenter_id": ["t1", "t2"],
            "jobcenter_label": ["Mitte, JC", "Pankow, JC"],
            "ags_kreis": ["11000", "11000"],
            "kreis_label": ["Berlin, Stadt", "Berlin, Stadt"],
            "n_policy_regions": [1, 1],
        }
    )
    stocks = _stock_rows({"t1": 40.0, "t2": 60.0, "11000": 100.0})
    check = check_jobcenter_kreis_stocks(crosswalk, stocks)
    assert check["difference"].to_numpy() == pytest.approx([0.0])


def test_check_jobcenter_kreis_stocks_reports_a_missing_kreis():
    crosswalk = pd.DataFrame(
        {
            "jobcenter_id": ["t1"],
            "jobcenter_label": ["Zwei, JC"],
            "ags_kreis": ["01001"],
            "kreis_label": ["A"],
            "n_policy_regions": [1],
        }
    )
    stocks = _stock_rows({"t1": 300.0, "01001": 100.0})
    check = check_jobcenter_kreis_stocks(crosswalk, stocks)
    assert check["difference"].to_numpy() == pytest.approx([200.0])


def test_split_validation_samples_keeps_differing_caps_in_the_extended_sample():
    crosswalk = pd.DataFrame(
        {
            "jobcenter_id": ["t1", "t1"],
            "jobcenter_label": ["Doppelkreis, JC", "Doppelkreis, JC"],
            "kreis_label": ["A", "B"],
            "ags_kreis": ["01001", "01002"],
            "n_policy_regions": [2, 2],
        }
    )
    samples = split_validation_samples(
        crosswalk, kreisfrei_ags=[], uniform_caps={"01001": 400.0, "01002": 800.0}
    )
    assert set(samples["sample"]) == {"extended"}


def test_split_validation_samples_never_splits_one_jobcenter_across_samples():
    crosswalk = pd.DataFrame(
        {
            "jobcenter_id": ["t1", "t1"],
            "jobcenter_label": ["Doppelkreis, JC", "Doppelkreis, JC"],
            "kreis_label": ["A", "B"],
            "ags_kreis": ["01001", "01002"],
            "n_policy_regions": [2, 2],
        }
    )
    samples = split_validation_samples(
        crosswalk, kreisfrei_ags=["01001"], uniform_caps={"01001": 400.0}
    )
    assert samples["sample"].nunique() == 1


def test_add_jobcenter_id_fills_a_gemeinde_from_its_kreis():
    gemeinden = pd.DataFrame({"ags": ["01001000"], "ags_kreis": ["01001"]})
    mapping = pd.DataFrame({"ags_kreis": ["01001"], "jobcenter_id": ["t11111"]})
    filled = add_jobcenter_id(gemeinden, mapping)
    assert filled["jobcenter_id"].to_list() == ["t11111"]


def test_add_jobcenter_id_leaves_berlin_missing():
    gemeinden = pd.DataFrame({"ags": ["11000000"], "ags_kreis": ["11000"]})
    mapping = pd.DataFrame(
        {"ags_kreis": ["11000", "11000"], "jobcenter_id": ["t96204", "t95504"]}
    )
    filled = add_jobcenter_id(gemeinden, mapping)
    assert filled["jobcenter_id"].isna().all()


def test_read_committed_extract_keeps_the_leading_zero_of_a_kreis_code(tmp_path):
    path = tmp_path / "extract.csv"
    path.write_text(
        "reference_month,region_level,region_code,region_label,"
        "accommodation_scope,measure,total,1_person,2_persons,3_persons,"
        "4_persons,5_persons,6_or_more_persons\n"
        "2026-04,kreis,01001,Flensburg,miete,bg_stock,7,1,1,1,1,1,2\n",
        encoding="utf-8",
    )
    frame = read_committed_extract(path, "household_size")
    assert frame["region_code"].to_list() == ["01001"]


def test_read_committed_extract_reads_category_columns_as_numbers(tmp_path):
    path = tmp_path / "extract.csv"
    path.write_text(
        "reference_month,region_level,region_code,region_label,"
        "accommodation_scope,measure,total,1_person,2_persons,3_persons,"
        "4_persons,5_persons,6_or_more_persons\n"
        "2026-04,kreis,01001,Flensburg,miete,bg_stock,7,1,1,1,1,1,2\n",
        encoding="utf-8",
    )
    frame = read_committed_extract(path, "household_size")
    assert frame["total"].to_numpy() == pytest.approx([7.0])
