"""Run the §6.5 checks, build the §6.6 worklist, and render the Gate 1 report."""

import json
from pathlib import Path
from typing import Annotated, cast

import pandas as pd
from pytask import Product

from kdu.config import BLD, DATA_CATALOG, ROOT
from kdu.data_management.harmonise import derive_ags_8
from kdu.data_management.provenance import (
    index_converted_text,
    index_corpus_files,
    load_corpus_layout,
    normalise_name,
    split_source_document,
)
from kdu.data_management.quality import (
    add_warn_flags,
    build_coverage_table,
    build_data_dictionary,
    build_quality_report,
    build_validation_worklist,
    run_all_checks,
)

VARIABLE_DESCRIPTIONS_PATH = ROOT / "docs" / "data_dictionary_source.json"

_LONG_TABLE = cast("Path", DATA_CATALOG["kdu_municipality_household"])
_GEMEINDE_LOOKUP = cast("Path", DATA_CATALOG["gemeinde_lookup"])
_GEMEINDEN_GEOJSON = cast("Path", DATA_CATALOG["gemeinden_geojson"])
_GEMEINDE_POPULATION = cast("Path", DATA_CATALOG["gemeinde_population"])
_NEIGHBOUR_JUMP_FLAGS = cast("Path", DATA_CATALOG["neighbour_jump_flags"])
_SOURCE_MATCH_SUMMARY = BLD / "source_match_summary.csv"
_WOGG_LINK_DISAGREEMENTS = BLD / "wogg_link_disagreements.csv"
_QUALITY_REPORT = cast("Path", DATA_CATALOG["quality_report"])
_DATA_DICTIONARY = cast("Path", DATA_CATALOG["data_dictionary"])
_VALIDATION_WORKLIST = BLD / "validation_worklist.csv"
_COVERAGE_BY_STATE = BLD / "coverage_by_state.csv"
_QUALITY_CHECK_RESULTS = BLD / "quality_check_results.csv"
_WARN_FLAGS = BLD / "kdu_warn_flags.parquet"


def task_check_kdu_quality(
    long_path: Path = _LONG_TABLE,
    lookup_path: Path = _GEMEINDE_LOOKUP,
    geojson_path: Path = _GEMEINDEN_GEOJSON,
    population_path: Path = _GEMEINDE_POPULATION,
    match_summary_path: Path = _SOURCE_MATCH_SUMMARY,
    disagreement_path: Path = _WOGG_LINK_DISAGREEMENTS,
    neighbour_jump_flags_path: Path = _NEIGHBOUR_JUMP_FLAGS,
    report_path: Annotated[Path, Product] = _QUALITY_REPORT,
    dictionary_path: Annotated[Path, Product] = _DATA_DICTIONARY,
    worklist_path: Annotated[Path, Product] = _VALIDATION_WORKLIST,
    coverage_path: Annotated[Path, Product] = _COVERAGE_BY_STATE,
    checks_path: Annotated[Path, Product] = _QUALITY_CHECK_RESULTS,
    flagged_path: Annotated[Path, Product] = _WARN_FLAGS,
) -> None:
    """Produce every Gate 1 quality artefact from the harmonised long table."""
    long = pd.read_parquet(long_path)
    lookup = pd.read_feather(lookup_path)
    layout = load_corpus_layout()
    file_index = index_corpus_files(layout)
    text_index = index_converted_text(layout)
    manifest = pd.read_csv(layout.manifest, engine="pyarrow")

    results = run_all_checks(
        long,
        geometry_ags=_geometry_ags(geojson_path),
        lookup_ags=frozenset(lookup["ags"].map(derive_ags_8)),
        source_valid_from=_valid_from_by_document(long, manifest, file_index),
    )
    flagged = add_warn_flags(long, results)
    flagged.to_parquet(flagged_path, index=False)
    _checks_frame(results).to_csv(checks_path, index=False)

    coverage = build_coverage_table(long, pd.read_feather(population_path))
    coverage.to_csv(coverage_path, index=False)

    worklist = build_validation_worklist(
        long,
        check_results=results,
        file_index=file_index,
        text_index=text_index,
        neighbour_jump_flags=pd.read_parquet(neighbour_jump_flags_path),
    )
    worklist.to_csv(worklist_path, index=False)

    descriptions = json.loads(VARIABLE_DESCRIPTIONS_PATH.read_text(encoding="utf-8"))
    build_data_dictionary(flagged, descriptions).to_csv(dictionary_path, index=False)

    report = build_quality_report(
        long,
        check_results=results,
        coverage=coverage,
        unmatched_sources=pd.read_csv(match_summary_path),
        disagreements=pd.read_csv(disagreement_path, dtype={"ags": str}),
        worklist=worklist,
    )
    report_path.write_text(report, encoding="utf-8")


def _geometry_ags(path: Path) -> frozenset[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return frozenset(
        derive_ags_8(feature["properties"]["gem_code"]) for feature in raw["features"]
    )


def _valid_from_by_document(
    long: pd.DataFrame,
    manifest: pd.DataFrame,
    file_index,  # noqa: ANN001
) -> dict[str, frozenset[str]]:
    """Collect the Wirksamkeitsdaten of every document a citation resolves to."""
    dates = {
        normalise_name(str(record["filename"])): record["valid_from_iso"]
        for record in manifest.to_dict(orient="records")
        if isinstance(record.get("filename"), str)
    }
    by_document: dict[str, frozenset[str]] = {}
    for document in long["source_document"].dropna().unique():
        components = split_source_document(str(document), file_index)
        found = {
            dates[normalise_name(component)]
            for component in components
            if normalise_name(component) in dates
        }
        by_document[str(document)] = frozenset(
            value for value in found if isinstance(value, str)
        )
    return by_document


def _checks_frame(results) -> pd.DataFrame:  # noqa: ANN001
    return pd.DataFrame.from_records(
        [
            {
                "check_id": result.check_id,
                "name": result.name,
                "kind": "descriptive" if result.is_descriptive else "rule",
                "n_evaluated": result.n_evaluated,
                "n_violations": result.n_violations,
                "description": result.description,
                "detail": result.detail,
            }
            for result in results
        ],
    )
