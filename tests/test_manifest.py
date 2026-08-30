from datetime import date
from pathlib import Path

import pytest

from kdu.config import ANALYSIS_DATE
from kdu.final.manifest import (
    MANIFEST_COLUMNS,
    ResultEntry,
    read_manifest,
    register_result,
    upsert,
    write_manifest,
)

FILENAME = "fig_proxy_error_h1.html"
MODULE = "P0.3"
DATASET = "analysis_sample_main.parquet"
SCRIPT = "src/kdu/final/task_figures_proxy_error.py"
INTERPRETATION = "Median K exceeds W by 10 %, with a wide within-Mietenstufe spread."
LIMITATION = "12.9 % of Gemeinden are WoGG-linked, where the 10 % is an identity."


@pytest.fixture
def manifest_path(tmp_path: Path) -> Path:
    return tmp_path / "results_manifest.csv"


def register(
    path: Path,
    filename: str = FILENAME,
    analysis_module: str = MODULE,
    interpretation: str = INTERPRETATION,
    created: date | None = None,
) -> Path:
    return register_result(
        filename=filename,
        analysis_module=analysis_module,
        dataset=DATASET,
        script=SCRIPT,
        interpretation=interpretation,
        limitation=LIMITATION,
        created=created,
        manifest_path=path,
    )


def test_register_result_writes_the_seven_required_fields(manifest_path: Path) -> None:
    register(manifest_path)
    assert tuple(read_manifest(manifest_path).columns) == MANIFEST_COLUMNS


def test_register_result_records_the_entry(manifest_path: Path) -> None:
    register(manifest_path)
    assert read_manifest(manifest_path)["filename"].item() == FILENAME


def test_register_result_defaults_the_creation_date_to_the_stichtag(
    manifest_path: Path,
) -> None:
    register(manifest_path)
    assert read_manifest(manifest_path)["created"].item() == ANALYSIS_DATE.isoformat()


def test_register_result_accepts_an_explicit_creation_date(manifest_path: Path) -> None:
    register(manifest_path, created=date(2026, 1, 2))
    assert read_manifest(manifest_path)["created"].item() == "2026-01-02"


def test_registering_the_same_filename_twice_replaces_the_row(
    manifest_path: Path,
) -> None:
    register(manifest_path)
    register(manifest_path, analysis_module="P0.5")
    assert len(read_manifest(manifest_path)) == 1


def test_registering_a_second_output_keeps_the_first(manifest_path: Path) -> None:
    register(manifest_path)
    register(manifest_path, filename="tab_2.csv")
    assert len(read_manifest(manifest_path)) == 2


def test_interpretation_with_a_comma_survives_the_round_trip(
    manifest_path: Path,
) -> None:
    text = "Caps rise with h, but not proportionally."
    register(manifest_path, interpretation=text)
    assert read_manifest(manifest_path)["interpretation"].item() == text


def test_read_manifest_returns_an_empty_frame_when_nothing_is_registered(
    manifest_path: Path,
) -> None:
    assert read_manifest(manifest_path).empty


def test_write_manifest_creates_the_header_for_an_empty_manifest(
    manifest_path: Path,
) -> None:
    write_manifest(read_manifest(manifest_path), manifest_path)
    assert manifest_path.read_text(encoding="utf-8").splitlines()[0].count(",") == 6


def test_upsert_sorts_entries_by_module_then_filename(manifest_path: Path) -> None:
    manifest = read_manifest(manifest_path)
    for module, filename in (("P0.5", "b.csv"), ("P0.3", "a.csv")):
        manifest = upsert(
            manifest,
            ResultEntry(
                filename=filename,
                analysis_module=module,
                dataset=DATASET,
                script=SCRIPT,
                interpretation=INTERPRETATION,
                limitation=LIMITATION,
            ),
        )
    assert list(manifest["filename"]) == ["a.csv", "b.csv"]
