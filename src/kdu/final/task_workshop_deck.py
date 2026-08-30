"""Write the consolidated results text and the workshop figure selection.

The task reads only artefacts other tasks have already written, so the
document it produces is a view of the task graph rather than a second source of
numbers. `docs/results.md` is committed on purpose: it is the deliverable §22's
Gate 2 asks for, and keeping it under version control makes any drift between
the text and the task graph visible in a diff.
"""

from pathlib import Path
from typing import Annotated

import pandas as pd
from pytask import Product

from kdu.final.manifest import register_result
from kdu.final.workshop import (
    DECK_TABLE,
    INPUT_PATHS,
    RESULTS_DOCUMENT,
    ResultsInputs,
    build_deck_table,
    build_results_document,
    workshop_deck,
)

_MODULE = "src/kdu/final/task_workshop_deck.py"

# Every sentence of `docs/results.md` is written by `workshop.py`, but pytask
# hashes only the task module's own source. Declaring `workshop.py` as an input
# makes an edit to the prose invalidate the document instead of leaving a stale
# one behind a green build (A23).
WORKSHOP_MODULE = Path(__file__).with_name("workshop.py")


def task_workshop_deck(
    coverage_file: Path = INPUT_PATHS["coverage"],
    proxy_error_table_file: Path = INPUT_PATHS["proxy_error_table"],
    proxy_error_frame_file: Path = INPUT_PATHS["proxy_error_frame"],
    within_mietenstufe_file: Path = INPUT_PATHS["within_mietenstufe"],
    dispersion_file: Path = INPUT_PATHS["dispersion"],
    tilt_file: Path = INPUT_PATHS["tilt"],
    rank_stability_file: Path = INPUT_PATHS["rank_stability"],
    wogg_linked_check_file: Path = INPUT_PATHS["wogg_linked_check"],
    microsim_file: Path = INPUT_PATHS["microsim"],
    heating_file: Path = INPUT_PATHS["heating"],
    rent_grid_file: Path = INPUT_PATHS["rent_grid"],
    needs_file: Path = INPUT_PATHS["needs"],
    microsim_gemeinde_file: Path = INPUT_PATHS["microsim_gemeinde"],
    budget_curves_file: Path = INPUT_PATHS["budget_curves"],
    weighting_availability_file: Path = INPUT_PATHS["weighting_availability"],
    border_type_file: Path = INPUT_PATHS["border_jumps_by_border_type"],
    comparison_group_file: Path = INPUT_PATHS["border_jump_comparison_group"],
    ba_specifications_file: Path = INPUT_PATHS["ba_specifications"],
    ba_variation_file: Path = INPUT_PATHS["ba_regressor_variation"],
    ba_frame_file: Path = INPUT_PATHS["ba_validation_frame"],
    worklist_file: Path = INPUT_PATHS["validation_worklist"],
    manifest_file: Path = INPUT_PATHS["manifest"],
    workshop_module_file: Path = WORKSHOP_MODULE,  # noqa: ARG001
    results_file: Annotated[Path, Product] = RESULTS_DOCUMENT,
    deck_file: Annotated[Path, Product] = DECK_TABLE,
) -> None:
    """Write `docs/results.md` and the §19 workshop figure selection."""
    inputs = ResultsInputs(
        coverage=pd.read_csv(coverage_file),
        proxy_error_table=pd.read_csv(proxy_error_table_file),
        proxy_error_frame=pd.read_parquet(proxy_error_frame_file),
        within_mietenstufe=pd.read_csv(within_mietenstufe_file),
        dispersion=pd.read_csv(dispersion_file),
        tilt=pd.read_csv(tilt_file),
        rank_stability=pd.read_csv(rank_stability_file),
        wogg_linked_check=pd.read_csv(wogg_linked_check_file),
        microsim=pd.read_csv(microsim_file),
        heating=pd.read_csv(heating_file),
        rent_grid=pd.read_csv(rent_grid_file),
        needs=pd.read_csv(needs_file),
        microsim_gemeinde=pd.read_parquet(microsim_gemeinde_file),
        budget_curves=pd.read_parquet(budget_curves_file),
        weighting_availability=pd.read_csv(weighting_availability_file),
        border_jumps_by_border_type=pd.read_csv(border_type_file),
        border_jump_comparison_group=pd.read_csv(comparison_group_file),
        ba_specifications=pd.read_csv(ba_specifications_file),
        ba_regressor_variation=pd.read_csv(ba_variation_file),
        ba_validation_frame=pd.read_parquet(ba_frame_file),
        validation_worklist=pd.read_csv(worklist_file),
        manifest=_read_manifest(manifest_file),
    )

    deck = build_deck_table()
    deck_file.parent.mkdir(parents=True, exist_ok=True)
    deck.to_csv(deck_file, index=False)

    results_file.parent.mkdir(parents=True, exist_ok=True)
    results_file.write_text(build_results_document(inputs), encoding="utf-8")

    _register(deck)


def _read_manifest(path: Path) -> pd.DataFrame:
    """Read `results_manifest.csv`, which the §23 audit counts registrations from.

    It is a declared dependency so that a task registering a new output makes
    this one stale, rather than leaving a stale count behind a green pytask
    (A23). No task declares it a product — every task appends its own rows — so
    pytask cannot order this one after them; on a build from an empty `bld/`
    the count converges on the second run.
    """
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _register(deck: pd.DataFrame) -> None:
    chosen = len(workshop_deck())
    register_result(
        filename=DECK_TABLE.name,
        analysis_module="P0 consolidation",
        dataset="results_manifest.csv",
        script=_MODULE,
        interpretation=(
            f"{chosen} of the {len(deck)} §19 main figures are admitted to the "
            f"main workshop talk; the rest go to backup or annex."
        ),
        limitation=(
            "All eight §19 main figures are built, so the selection is a "
            "judgement about what carries an argument in a talk, not about "
            "what exists: the P1.1 and P1.2 figures are annex and backup "
            "because they answer a reviewer rather than lead one."
        ),
    )
