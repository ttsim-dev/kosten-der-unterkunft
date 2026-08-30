import numpy as np
import pandas as pd
import pytest

from kdu.config import ExclusionReason
from kdu.data_management.harmonise import (
    CalculationMethod,
    DerivedValueFlag,
    MainSampleExclusionReason,
    PrintedEvidence,
    QualityTier,
    QualityTierReason,
    aggregate_to_policy_region,
    apply_cold_opex_scenarios,
    assign_quality_tier,
    balanced_municipalities,
    build_analysis_samples,
    build_exclusion_log,
    build_geography,
    build_kdu_bkc_cap,
    classify_derived_values,
    classify_exclusion_reason,
    cold_opex_scenario_band,
    derive_ags_8,
    detect_wogg_linked,
    household_suffix,
    melt_to_long,
    wogg_link_disagreements,
)

SIZES = (1, 2, 3, 4, 5)


def make_wide(**overrides: object) -> pd.DataFrame:
    """Build a two-Gemeinde wide table with every column the melt needs."""
    row: dict[str, object] = {
        "ags_gemeinde": ["09999001", "09999002"],
        "gemeinde_name": ["Alpha", "Beta"],
        "ags_kreis": ["09999", "09999"],
        "kdu_region": ["Kreisgebiet", "Kreisgebiet"],
        "source_document": ["Doc.pdf", "Doc.pdf"],
        "valid_from": ["2026-01-01", "2026-01-01"],
        "notes": ["", ""],
        "wogg_mietstufe": [3.0, 3.0],
        "wogv_mietstufe": [3.0, 3.0],
        "haertefall_regelung": [np.nan, np.nan],
        "max_nettokaltmiete_eur_sqm": [np.nan, np.nan],
        "max_kalte_bk_eur_sqm": [np.nan, np.nan],
        "max_bruttokaltmiete_eur_sqm": [np.nan, np.nan],
        "max_bruttokaltmiete_eur_addl": [90.0, 90.0],
        "max_wohnflaeche_sqm_addl": [10.0, 10.0],
    }
    caps = [400.0, 500.0, 600.0, 700.0, 800.0]
    for position, size in enumerate(SIZES):
        suffix = household_suffix(size)
        row[f"max_wohnflaeche_sqm_{suffix}"] = [50.0 + 10 * position] * 2
        row[f"max_nettokaltmiete_eur_{suffix}"] = [np.nan, np.nan]
        row[f"max_kalte_bk_eur_{suffix}"] = [np.nan, np.nan]
        row[f"max_bruttokaltmiete_eur_{suffix}"] = [caps[position]] * 2
    for size in (1, 2, 4):
        row[f"wogg_hoechstbetrag_eur_{household_suffix(size)}"] = [500.0] * 2
    row.update(overrides)
    return pd.DataFrame(row)


def make_lookup() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ags": ["099990010000", "099990020000"],
            "gemeinde": ["Alpha", "Beta"],
            "gem_type": ["Gemeinde", "Gemeindefreies Gebiet"],
            "kreis": ["Musterkreis", "Musterkreis"],
            "bundesland": ["Musterland", "Musterland"],
        },
    )


def make_jobcenter_kreis() -> pd.DataFrame:
    """One Jobcenter serving the single Kreis of `make_lookup`."""
    return pd.DataFrame(
        {"jobcenter_id": ["09999"], "ags_kreis": ["09999"]},
    )


def make_benchmark(cap: float = 500.0) -> pd.DataFrame:
    """A Wohngeld benchmark for both Gemeinden and all five household sizes."""
    return pd.DataFrame(
        [
            {"ags": ags, "household_size": size, "wogg_base_cap": cap}
            for ags in ("09999001", "09999002")
            for size in SIZES
        ],
    )


def make_long(
    wide: pd.DataFrame | None = None,
    benchmark: pd.DataFrame | None = None,
) -> pd.DataFrame:
    wide = make_wide() if wide is None else wide
    long = (
        melt_to_long(wide)
        .merge(
            build_geography(make_lookup(), make_jobcenter_kreis()),
            on="ags",
            how="left",
        )
        .merge(
            make_benchmark() if benchmark is None else benchmark,
            on=["ags", "household_size"],
            how="left",
        )
    )
    return pd.concat([long, build_kdu_bkc_cap(long)], axis=1)


def test_derive_ags_8_keeps_leading_zeros() -> None:
    assert derive_ags_8("010010000000") == "01001000"


def test_build_geography_uses_the_kreis_as_the_policy_region() -> None:
    geography = build_geography(make_lookup(), make_jobcenter_kreis())
    assert geography.loc[0, "policy_region_id"] == "09999"


def test_build_geography_fills_the_jobcenter_of_the_kreis() -> None:
    """Every Gemeinde carries the id of the one Jobcenter serving its Kreis."""
    geography = build_geography(make_lookup(), make_jobcenter_kreis())
    assert (geography["jobcenter_id"] == "09999").all()


def test_build_geography_leaves_jobcenter_missing_where_a_kreis_has_several() -> None:
    """A Kreis served by several Jobcenter gets no id: none of them describes it."""
    berlin = pd.DataFrame(
        {"jobcenter_id": ["09999A", "09999B"], "ags_kreis": ["09999", "09999"]},
    )
    geography = build_geography(make_lookup(), berlin)
    assert geography["jobcenter_id"].isna().all()


def test_melt_to_long_yields_one_row_per_gemeinde_and_household_size() -> None:
    assert len(melt_to_long(make_wide())) == 2 * len(SIZES)


def test_melt_to_long_carries_the_household_specific_area() -> None:
    long = melt_to_long(make_wide())
    row = long.query("ags == '09999001' and household_size == 3")
    assert row["max_area_sqm"].to_numpy()[0] == 70.0


def test_build_kdu_bkc_cap_takes_a_published_gross_cold_total_unchanged() -> None:
    caps = build_kdu_bkc_cap(melt_to_long(make_wide()))
    assert caps["kdu_bkc_cap"].to_numpy()[0] == 400.0


def test_build_kdu_bkc_cap_labels_a_published_total() -> None:
    caps = build_kdu_bkc_cap(melt_to_long(make_wide()))
    assert (
        caps["calculation_method"].to_numpy()[0]
        == CalculationMethod.PUBLISHED_GROSS_COLD_TOTAL.value
    )


def test_build_kdu_bkc_cap_sums_published_components() -> None:
    wide = make_wide(
        max_bruttokaltmiete_eur_1p=[np.nan, np.nan],
        max_nettokaltmiete_eur_1p=[300.0, 300.0],
        max_kalte_bk_eur_1p=[80.0, 80.0],
    )
    caps = build_kdu_bkc_cap(melt_to_long(wide))
    at_h1 = melt_to_long(wide)["household_size"].eq(1)
    assert caps.loc[at_h1, "kdu_bkc_cap"].to_numpy()[0] == 380.0


def test_build_kdu_bkc_cap_never_multiplies_out_a_per_sqm_figure() -> None:
    wide = make_wide(
        max_bruttokaltmiete_eur_1p=[np.nan, np.nan],
        max_nettokaltmiete_eur_sqm=[7.0, 7.0],
        max_kalte_bk_eur_sqm=[2.0, 2.0],
    )
    caps = build_kdu_bkc_cap(melt_to_long(wide))
    at_h1 = melt_to_long(wide)["household_size"].eq(1)
    assert caps.loc[at_h1, "kdu_bkc_cap"].isna().all()


def test_classify_derived_values_calls_a_component_sum_computed() -> None:
    wide = make_wide(
        max_bruttokaltmiete_eur_1p=[380.0, 380.0],
        max_nettokaltmiete_eur_1p=[300.0, 300.0],
        max_kalte_bk_eur_1p=[80.0, 80.0],
    )
    long = make_long(wide)
    flags = classify_derived_values(long, printed_evidence=None)
    at_h1 = long["household_size"].eq(1)
    assert (
        flags.loc[at_h1, "derived_value_flag"].to_numpy()[0]
        == DerivedValueFlag.COMPUTED.value
    )


def test_classify_derived_values_calls_a_located_amount_printed() -> None:
    long = make_long()
    evidence = {("Doc.pdf", 400.0): PrintedEvidence.FOUND_IN_TEXT.value}
    flags = classify_derived_values(long, evidence)
    at_h1 = long["household_size"].eq(1)
    assert (
        flags.loc[at_h1, "derived_value_flag"].to_numpy()[0]
        == DerivedValueFlag.PRINTED.value
    )


def test_classify_derived_values_stays_unknown_without_evidence() -> None:
    long = make_long()
    flags = classify_derived_values(long, printed_evidence={})
    assert (flags["derived_value_flag"] == DerivedValueFlag.UNKNOWN.value).all()


def test_classify_derived_values_records_why_it_could_not_decide() -> None:
    long = make_long()
    flags = classify_derived_values(long, printed_evidence={})
    assert (
        flags["printed_evidence"].to_numpy()[0]
        == PrintedEvidence.NO_TEXT_AVAILABLE.value
    )


def test_detect_wogg_linked_fires_on_the_ten_percent_markup() -> None:
    wide = make_wide()
    for size in SIZES:
        wide[f"max_bruttokaltmiete_eur_{household_suffix(size)}"] = [550.0, 550.0]
    assert detect_wogg_linked(make_long(wide))["wogg_linked_ratio"].all()


def test_detect_wogg_linked_stays_silent_when_the_ratio_is_not_the_markup() -> None:
    assert not detect_wogg_linked(make_long())["wogg_linked_ratio"].any()


def test_detect_wogg_linked_fires_on_the_notes_wording() -> None:
    wide = make_wide(
        notes=["WoGG-Tabelle + 10% Sicherheitszuschlag", "Eigenes Konzept"],
    )
    detected = detect_wogg_linked(make_long(wide))
    assert detected["wogg_linked_notes"].tolist() == [True, False]


def test_detect_wogg_linked_marks_a_detector_disagreement() -> None:
    wide = make_wide(notes=["WoGG-Tabelle + 10% Sicherheitszuschlag", ""])
    detected = detect_wogg_linked(make_long(wide))
    assert detected["wogg_link_detectors_agree"].tolist() == [False, True]


def test_wogg_link_disagreements_lists_the_gemeinde_for_review() -> None:
    wide = make_wide(notes=["WoGG-Tabelle + 10% Sicherheitszuschlag", ""])
    long = make_long(wide)
    long = long.merge(detect_wogg_linked(long), on="ags", how="left")
    assert wogg_link_disagreements(long)["ags"].tolist() == ["09999001"]


def _tier_input(long: pd.DataFrame, **overrides: object) -> pd.DataFrame:
    frame = long.copy()
    frame["derived_value_flag"] = DerivedValueFlag.PRINTED.value
    frame["household_sizes_complete"] = True
    frame["region_assignment_high_confidence"] = True
    frame["has_primary_document"] = True
    for key, value in overrides.items():
        frame[key] = value
    return frame


def test_assign_quality_tier_gives_a_verified_printed_cap_tier_a() -> None:
    tiers = assign_quality_tier(_tier_input(make_long()))
    assert (tiers["quality_tier"] == QualityTier.A.value).all()


def test_assign_quality_tier_gives_a_component_sum_tier_b() -> None:
    frame = _tier_input(
        make_long(),
        derived_value_flag=DerivedValueFlag.COMPUTED.value,
    )
    tiers = assign_quality_tier(frame)
    assert (tiers["quality_tier"] == QualityTier.B.value).all()


def test_assign_quality_tier_keeps_an_unverified_held_document_in_tier_b() -> None:
    frame = _tier_input(
        make_long(),
        derived_value_flag=DerivedValueFlag.UNKNOWN.value,
    )
    tiers = assign_quality_tier(frame)
    assert (
        tiers["quality_tier_reason"] == QualityTierReason.GROSS_COLD_UNVERIFIED.value
    ).all()


def test_assign_quality_tier_drops_a_citation_without_a_document_to_tier_c() -> None:
    frame = _tier_input(make_long(), has_primary_document=False)
    tiers = assign_quality_tier(frame)
    assert (tiers["quality_tier"] == QualityTier.C.value).all()


def test_cold_opex_scenario_band_is_ordered() -> None:
    band = cold_opex_scenario_band(
        make_wide(max_kalte_bk_eur_sqm=[1.2, 2.4]),
    )
    assert band["low"] <= band["mid"] <= band["high"]


def test_apply_cold_opex_scenarios_only_touches_netto_only_rows() -> None:
    long = make_long()
    scenarios = apply_cold_opex_scenarios(long, {"low": 1.0, "mid": 2.0, "high": 3.0})
    assert not scenarios["cold_opex_scenario_applied"].any()


def test_apply_cold_opex_scenarios_adds_the_band_to_a_netto_only_cap() -> None:
    wide = make_wide()
    for size in SIZES:
        suffix = household_suffix(size)
        wide[f"max_bruttokaltmiete_eur_{suffix}"] = [np.nan, np.nan]
        wide[f"max_nettokaltmiete_eur_{suffix}"] = [300.0, 300.0]
    long = make_long(wide)
    scenarios = apply_cold_opex_scenarios(long, {"low": 1.0, "mid": 2.0, "high": 3.0})
    at_h1 = long["household_size"].eq(1)
    assert scenarios.loc[at_h1, "kdu_bkc_cap_scenario_low"].to_numpy()[0] == 350.0


def test_balanced_municipalities_requires_every_listed_size() -> None:
    wide = make_wide()
    wide.loc[0, "max_bruttokaltmiete_eur_3p"] = np.nan
    long = make_long(wide)
    assert balanced_municipalities(long, (1, 2, 3, 4)).tolist() == ["09999002"]


def test_build_analysis_samples_restricts_the_main_sample_to_h1_to_h4() -> None:
    main, _ = build_analysis_samples(make_long())
    assert sorted(main["household_size"].unique()) == [1, 2, 3, 4]


def test_build_analysis_samples_labels_the_extended_strata() -> None:
    _, extended = build_analysis_samples(make_long())
    assert set(extended["sample_stratum"]) == {"main_balanced_h1_h4"}


def test_aggregate_to_policy_region_summarises_one_row_per_kreis_and_size() -> None:
    aggregated = aggregate_to_policy_region(
        make_long().assign(wogg_linked_flag=False, quality_tier=QualityTier.A.value),
    )
    assert len(aggregated) == len(SIZES)


def test_aggregate_to_policy_region_reports_within_region_uniformity() -> None:
    aggregated = aggregate_to_policy_region(
        make_long().assign(wogg_linked_flag=False, quality_tier=QualityTier.A.value),
    )
    assert aggregated["is_uniform_within_region"].all()


def test_build_exclusion_log_flags_an_unbalanced_gemeinde() -> None:
    wide = make_wide()
    wide.loc[0, "max_bruttokaltmiete_eur_3p"] = np.nan
    log = build_exclusion_log(make_long(wide))
    assert log.loc[0, "exclusion_reason"] == (
        MainSampleExclusionReason.HAUSHALTSGROESSEN_UNVOLLSTAENDIG.value
    )


def test_build_exclusion_log_flags_a_netto_only_gemeinde() -> None:
    wide = make_wide()
    for size in SIZES:
        suffix = household_suffix(size)
        wide.loc[0, f"max_bruttokaltmiete_eur_{suffix}"] = np.nan
        wide.loc[0, f"max_nettokaltmiete_eur_{suffix}"] = 300.0
    log = build_exclusion_log(make_long(wide))
    assert log.loc[0, "exclusion_reason"] == (
        MainSampleExclusionReason.NUR_NETTOKALTMIETE.value
    )


def test_classify_exclusion_reason_reads_the_gemeinde_type_not_the_notes() -> None:
    reason = classify_exclusion_reason("", "Gemeindefreies Gebiet")
    assert reason == ExclusionReason.GEMEINDEFREIES_GEBIET.value


def test_classify_exclusion_reason_recognises_an_ableitungsverbot() -> None:
    reason = classify_exclusion_reason(
        "Aktuelle Beträge wegen Ableitungsverbot leer.",
        "Gemeinde",
    )
    assert reason == ExclusionReason.ABLEITUNGSVERBOT.value


def test_classify_exclusion_reason_defaults_to_kein_dokument() -> None:
    assert classify_exclusion_reason(None, "Gemeinde") == (
        ExclusionReason.KEIN_DOKUMENT.value
    )


@pytest.mark.parametrize("size", SIZES)
def test_household_suffix_matches_the_wide_column_names(size: int) -> None:
    assert f"max_bruttokaltmiete_eur_{household_suffix(size)}" in make_wide().columns
