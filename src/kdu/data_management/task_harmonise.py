"""Build the source register, the long KdU table, and the two analysis samples.

Reads the committed wide CSV and the AGS lookup, resolves every citation
against the Sciebo corpus, and writes the §5.2 artefacts P0.1 owns.
"""

from pathlib import Path
from typing import Annotated, cast

import pandas as pd
from pytask import Product

from kdu.config import (
    BLD,
    DATA_CATALOG,
    HOUSEHOLD_SIZES,
    MAIN_SAMPLE_HOUSEHOLD_SIZES,
)
from kdu.data_management.harmonise import (
    CalculationMethod,
    DerivedValueFlag,
    QualityTier,
    aggregate_to_policy_region,
    apply_cold_opex_scenarios,
    assign_quality_tier,
    balanced_municipalities,
    build_analysis_samples,
    build_exclusion_log,
    build_geography,
    build_kdu_bkc_cap,
    classify_derived_values,
    cold_opex_scenario_band,
    detect_wogg_linked,
    load_kdu_wide,
    melt_to_long,
    wogg_link_disagreements,
)
from kdu.data_management.provenance import (
    build_component_map,
    build_source_register,
    count_unmatched_documents,
    index_converted_text,
    index_corpus_files,
    load_corpus_layout,
    normalise_name,
    responsible_institutions,
    scan_printed_amounts,
    split_source_document,
)

EXPECTED_MAIN_MUNICIPALITIES = 9_442
EXPECTED_MAIN_POLICY_REGIONS = 357

_KDU_GEMEINDEN = cast("Path", DATA_CATALOG["kdu_gemeinden"])
_GEMEINDE_LOOKUP = cast("Path", DATA_CATALOG["gemeinde_lookup"])
_WOGG_BENCHMARK = BLD / "wogg_benchmark.parquet"
_JOBCENTER_KREIS = BLD / "jobcenter_kreis_crosswalk.parquet"
_LONG_TABLE = cast("Path", DATA_CATALOG["kdu_municipality_household"])
_POLICY_REGION_TABLE = cast("Path", DATA_CATALOG["kdu_policy_region_household"])
_ANALYSIS_SAMPLE_MAIN = cast("Path", DATA_CATALOG["analysis_sample_main"])
_ANALYSIS_SAMPLE_EXTENDED = cast("Path", DATA_CATALOG["analysis_sample_extended"])
_SOURCE_REGISTER = cast("Path", DATA_CATALOG["source_register"])
_EXCLUSION_LOG = cast("Path", DATA_CATALOG["exclusion_log"])
_SOURCE_MATCH_SUMMARY = BLD / "source_match_summary.csv"
_WOGG_LINK_DISAGREEMENTS = BLD / "wogg_link_disagreements.csv"


def task_harmonise_kdu(
    kdu_path: Path = _KDU_GEMEINDEN,
    lookup_path: Path = _GEMEINDE_LOOKUP,
    benchmark_path: Path = _WOGG_BENCHMARK,
    jobcenter_kreis_path: Path = _JOBCENTER_KREIS,
    long_path: Annotated[Path, Product] = _LONG_TABLE,
    region_path: Annotated[Path, Product] = _POLICY_REGION_TABLE,
    main_path: Annotated[Path, Product] = _ANALYSIS_SAMPLE_MAIN,
    extended_path: Annotated[Path, Product] = _ANALYSIS_SAMPLE_EXTENDED,
    register_path: Annotated[Path, Product] = _SOURCE_REGISTER,
    exclusion_path: Annotated[Path, Product] = _EXCLUSION_LOG,
    unmatched_path: Annotated[Path, Product] = _SOURCE_MATCH_SUMMARY,
    disagreement_path: Annotated[Path, Product] = _WOGG_LINK_DISAGREEMENTS,
) -> None:
    """Harmonise the wide KdU table into every P0.1 artefact."""
    BLD.mkdir(parents=True, exist_ok=True)
    kdu = load_kdu_wide(kdu_path)
    lookup = pd.read_feather(lookup_path)
    benchmark = pd.read_parquet(benchmark_path)

    layout = load_corpus_layout()
    file_index = index_corpus_files(layout)
    text_index = index_converted_text(layout)
    manifest = pd.read_csv(layout.manifest, engine="pyarrow")
    region_to_kreis = pd.read_csv(layout.region_to_kreis, engine="pyarrow")

    geography = build_geography(lookup, pd.read_parquet(jobcenter_kreis_path))
    component_map = build_component_map(kdu["source_document"], file_index)
    kreis_names = dict(
        zip(geography["district_ags"], geography["district_name"], strict=True),
    )
    register = build_source_register(
        component_map,
        file_index,
        manifest,
        responsible_institutions(kdu, component_map, kreis_names),
    )
    register["has_converted_text"] = _has_converted_text(component_map, text_index)
    register.to_csv(register_path, index=False)
    count_unmatched_documents(component_map).to_csv(unmatched_path, index=False)

    long = build_long_table(
        kdu=kdu,
        geography=geography,
        component_map=component_map,
        register=register,
        region_to_kreis=region_to_kreis,
        benchmark=benchmark,
        file_index=file_index,
        text_index=text_index,
    )
    long.to_parquet(long_path, index=False)
    aggregate_to_policy_region(long).to_parquet(region_path, index=False)
    wogg_link_disagreements(long).to_csv(disagreement_path, index=False)

    main, extended = build_analysis_samples(long)
    _fail_if_main_sample_is_wrong(main)
    main.to_parquet(main_path, index=False)
    extended.to_parquet(extended_path, index=False)
    build_exclusion_log(long).to_csv(exclusion_path, index=False)


def build_long_table(
    *,
    kdu: pd.DataFrame,
    geography: pd.DataFrame,
    component_map: pd.DataFrame,
    register: pd.DataFrame,
    region_to_kreis: pd.DataFrame,
    benchmark: pd.DataFrame,
    file_index,  # noqa: ANN001
    text_index,  # noqa: ANN001
) -> pd.DataFrame:
    """Assemble the §6.2 long table from the wide CSV and the provenance."""
    long = (
        melt_to_long(kdu)
        .merge(geography, on="ags", how="left", validate="many_to_one")
        .merge(
            _benchmark_block(benchmark),
            on=["ags", "household_size"],
            how="left",
            validate="one_to_one",
        )
    )
    long = pd.concat([long, build_kdu_bkc_cap(long)], axis=1)

    amounts = _amounts_by_document(long)
    evidence = scan_printed_amounts(amounts, file_index, text_index)
    long = pd.concat([long, classify_derived_values(long, evidence)], axis=1)
    # A Bruttokaltmiete that is exactly its two printed components is §6.3's
    # rule 2, whichever column of the wide table happens to carry it.
    long.loc[
        long["derived_value_flag"].eq(DerivedValueFlag.COMPUTED.value),
        "calculation_method",
    ] = CalculationMethod.SUM_OF_PUBLISHED_COMPONENTS.value

    long = long.merge(
        detect_wogg_linked(long),
        on="ags",
        how="left",
        validate="many_to_one",
    )

    long = long.merge(
        _primary_source(component_map, register),
        on="source_document",
        how="left",
        validate="many_to_one",
    )
    long["has_primary_document"] = long["source_type"].notna()
    long["region_assignment_high_confidence"] = ~long["policy_region_id"].isin(
        _low_confidence_regions(region_to_kreis),
    )
    # §6.4's "Haushaltsgrößen vollständig" is read against h = 1…4, the sizes the
    # main analysis is defined on (D3). A Gemeinde whose document stops at four
    # people is complete for that analysis; the separate h = 5 gap is carried by
    # `all_household_sizes_complete` and reported with its own N.
    n_caps = long.groupby("ags")["kdu_bkc_cap"].transform("count")
    n_main_caps = (
        long[long["household_size"].isin(MAIN_SAMPLE_HOUSEHOLD_SIZES)]
        .groupby("ags")["kdu_bkc_cap"]
        .count()
    )
    long["household_sizes_complete"] = (
        long["ags"].map(n_main_caps).fillna(0).eq(len(MAIN_SAMPLE_HOUSEHOLD_SIZES))
    )
    long["all_household_sizes_complete"] = n_caps.eq(len(HOUSEHOLD_SIZES))
    long["wogg_rent_level_missing"] = (
        long["wogg_rent_level_missing"]
        .fillna(
            value=True,
        )
        .astype(bool)
    )

    long = pd.concat([long, assign_quality_tier(long)], axis=1)
    band = cold_opex_scenario_band(kdu)
    long = pd.concat([long, apply_cold_opex_scenarios(long, band)], axis=1)
    long.loc[
        long["cold_opex_scenario_applied"],
        "calculation_method",
    ] = CalculationMethod.NETTO_ONLY_SCENARIO.value
    return pd.concat([long, _raw_value_block(long)], axis=1)


def _benchmark_block(benchmark: pd.DataFrame) -> pd.DataFrame:
    """Take the P0.2 Wohngeld benchmark for all five household sizes (D6, A2)."""
    columns = [
        "ags",
        "household_size",
        "wogg_rent_level",
        "wogg_rent_level_missing",
        "wogg_base_cap",
        "wogg_climate_component",
        "wogg_heating_relief",
        "wogg_bkc_cap",
        "wogg_primary_cap",
        "wogg_parameter_vintage",
    ]
    block = benchmark[columns].copy()
    block["household_size"] = block["household_size"].astype("int64")
    block["ags"] = block["ags"].astype("string")
    return block


def _raw_value_block(long: pd.DataFrame) -> pd.DataFrame:
    """Record what the source states, before any harmonisation."""
    gross = long["gross_cold_cap_total"]
    net = long["net_cold_cap_total"]
    raw = pd.DataFrame(index=long.index)
    raw["kdu_value_raw"] = gross.where(gross.notna(), net)
    raw["kdu_unit_raw"] = pd.Series(
        "eur_per_month",
        index=long.index,
        dtype="string",
    ).where(raw["kdu_value_raw"].notna())
    raw["cost_concept_raw"] = (
        pd.Series("bruttokaltmiete", index=long.index, dtype="string")
        .where(gross.notna())
        .fillna(
            pd.Series("nettokaltmiete", index=long.index, dtype="string").where(
                net.notna(),
            ),
        )
    )
    notes = long["notes"].fillna("")
    raw["product_theory_flag"] = (
        notes.str.contains("produkttheorie", case=False, regex=False)
        | (long["max_area_sqm"].notna() & long["net_cold_cap_per_sqm"].notna())
    ).to_numpy()
    raw["exception_text"] = notes.where(
        notes.str.contains(
            r"h(?:ä|ae)rtefall|einzelfall|ausnahme|zuschlag",
            case=False,
            regex=True,
        ),
    ).replace("", pd.NA)
    return raw


def _amounts_by_document(long: pd.DataFrame) -> dict[str, frozenset[float]]:
    with_cap = long.dropna(subset=["source_document", "kdu_bkc_cap"])
    grouped = with_cap.groupby("source_document")["kdu_bkc_cap"]
    return {
        str(document): frozenset(float(value) for value in amounts.unique())
        for document, amounts in grouped
    }


def _primary_source(
    component_map: pd.DataFrame,
    register: pd.DataFrame,
) -> pd.DataFrame:
    """Pick one register row per citation: the first component that is a file."""
    ranked = component_map.merge(register, on="source_id", how="left")
    ranked["_is_file"] = ranked["source_type"].notna().astype(int)
    ranked = ranked.sort_values(
        ["source_document", "_is_file", "component_position"],
        ascending=[True, False, True],
    )
    primary = ranked.drop_duplicates(subset="source_document")
    columns = [
        "source_document",
        "source_id",
        "source_title",
        "source_institution",
        "source_type",
        "source_location",
        "publication_date",
        "retrieval_date",
        "source_hash",
    ]
    primary = primary[columns].copy()
    primary["source_id_all"] = (
        component_map.groupby("source_document")["source_id"]
        .apply(lambda ids: "|".join(sorted(ids)))
        .reindex(primary["source_document"])
        .to_numpy()
    )
    return primary


def _low_confidence_regions(region_to_kreis: pd.DataFrame) -> frozenset[str]:
    """Kreise whose region-to-Kreis mapping the crosswalk does not call `high`.

    A Kreis absent from the crosswalk is not low confidence: the crosswalk maps
    document region labels, while the Gemeinde-to-Kreis assignment in the CSV
    runs on the AGS itself and is exact.
    """
    kreis = region_to_kreis["kreis_ags"].astype("string").str.zfill(5)
    low = region_to_kreis["confidence"].ne("high")
    return frozenset(kreis[low].dropna())


def _has_converted_text(component_map: pd.DataFrame, text_index) -> pd.Series:  # noqa: ANN001
    unique = component_map.drop_duplicates(subset="source_id").sort_values("source_id")
    return (
        unique["component"]
        .map(lambda name: normalise_name(Path(name).stem) in text_index)
        .to_numpy()
    )


def _fail_if_main_sample_is_wrong(main: pd.DataFrame) -> None:
    n_municipalities = main["ags"].nunique()
    n_regions = main["policy_region_id"].nunique()
    if n_municipalities != EXPECTED_MAIN_MUNICIPALITIES:
        msg = (
            f"analysis_sample_main must hold {EXPECTED_MAIN_MUNICIPALITIES} "
            f"Gemeinden balanced over h={MAIN_SAMPLE_HOUSEHOLD_SIZES} (D3); "
            f"got {n_municipalities}"
        )
        raise ValueError(msg)
    if n_regions != EXPECTED_MAIN_POLICY_REGIONS:
        msg = (
            f"analysis_sample_main must cover {EXPECTED_MAIN_POLICY_REGIONS} "
            f"Kreise (D3); got {n_regions}"
        )
        raise ValueError(msg)


__all__ = [
    "QualityTier",
    "balanced_municipalities",
    "build_long_table",
    "split_source_document",
    "task_harmonise_kdu",
]
