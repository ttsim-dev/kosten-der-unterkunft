"""P0.6 — build the regionalised administrative Bruttokaltbedarf of §11."""

from pathlib import Path
from typing import Annotated

import pandas as pd
from pytask import Product

from kdu.config import BLD, MODEL_HOUSEHOLDS, catalog_path
from kdu.simulation.needs_level import (
    administrative_need,
    regelbedarf_components,
    summarise_need,
)

# Columns of the municipality crosswalk the §11.3 breakdowns are taken over.
BREAKDOWN_COLUMNS: tuple[str, ...] = (
    "bundesland",
    "mietenstufe",
    "gemeinde_size_class",
)

# Carried from the analysis sample rather than the crosswalk. Under D15 the
# WoGG-linked Gemeinden have a need difference of zero by construction, so the
# `False` group is the reading with them set aside.
LINKAGE_COLUMN = "wogg_linked_flag"


def task_needs_level(
    analysis_sample: Path = catalog_path("analysis_sample_main"),
    crosswalk: Path = catalog_path("municipality_crosswalk"),
    need_path: Annotated[Path, Product] = BLD / "needs_level_gemeinde.parquet",
    components_path: Annotated[Path, Product] = (
        BLD / "needs_level_components.parquet"
    ),
    summary_path: Annotated[Path, Product] = BLD / "needs_level_summary.parquet",
) -> None:
    """Compute `B^K` and `B^W` per Gemeinde and Modellhaushalt, and summarise them."""
    sample = pd.read_parquet(analysis_sample)
    municipalities = pd.read_parquet(crosswalk)
    need = build_need_table(sample, municipalities)
    need.to_parquet(need_path, index=False)
    build_components_table().to_parquet(components_path, index=False)
    build_summary_table(need).to_parquet(summary_path, index=False)


def build_need_table(
    sample: pd.DataFrame,
    municipalities: pd.DataFrame,
) -> pd.DataFrame:
    """Stack the per-household need frames and attach the §11.3 breakdown keys."""
    stacked = pd.concat(
        [administrative_need(sample, household_key=key) for key in MODEL_HOUSEHOLDS],
        ignore_index=True,
    )
    keys = municipalities.loc[
        :,
        ["ags", "policy_region_id", "kreis", *BREAKDOWN_COLUMNS, "population"],
    ]
    linkage = (
        sample.loc[:, ["ags", LINKAGE_COLUMN]]
        .drop_duplicates(subset="ags")
        .astype({LINKAGE_COLUMN: "boolean"})
    )
    return stacked.merge(keys, on="ags", how="left", validate="many_to_one").merge(
        linkage,
        on="ags",
        how="left",
        validate="many_to_one",
    )


def build_components_table() -> pd.DataFrame:
    """Report `R` and `M` per Modellhaushalt, the national part of the measure."""
    return pd.DataFrame(
        [
            {
                "household_key": entry.household_key,
                "household_label": MODEL_HOUSEHOLDS[entry.household_key].label,
                "household_size": MODEL_HOUSEHOLDS[entry.household_key].household_size,
                "regelbedarf_m": entry.regelbedarf_m,
                "mehrbedarf_m": entry.mehrbedarf_m,
                "standard_need_m": entry.standard_need_m,
            }
            for entry in regelbedarf_components().values()
        ],
    )


def build_summary_table(need: pd.DataFrame) -> pd.DataFrame:
    """Summarise nationally and by every §11.3 breakdown, in one long table."""
    frames = [summarise_need(need).assign(breakdown="all", group="all")]
    for column in (*BREAKDOWN_COLUMNS, LINKAGE_COLUMN):
        summary = summarise_need(need, by=[column])
        frames.append(
            summary.rename(columns={column: "group"}).assign(
                breakdown=column,
                group=lambda frame: frame["group"].astype("string"),
            ),
        )
    return pd.concat(frames, ignore_index=True)
