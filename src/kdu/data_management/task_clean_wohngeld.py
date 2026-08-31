"""Write the statutory benchmark each local KdU cap is measured against."""

from pathlib import Path
from typing import Annotated

import pandas as pd
from pytask import Product

from kdu.config import catalog_path
from kdu.data_management.clean_kdu_regions import (
    detect_wohngeld_rule,
    notes_by_row,
    read_kdu_gemeinden,
)
from kdu.data_management.clean_wohngeld import (
    build_hoechstbetrag_only,
    build_wohngeld_fallback,
    load_wohngeld_parameters,
    read_mietenstufen,
)


def task_clean_wohngeld(
    kdu_gemeinden_file: Path = catalog_path("kdu_gemeinden"),
    wohngeld_parameters_file: Path = catalog_path("wohngeld_parameters"),
    kdu_caps_file: Path = catalog_path("kdu_caps"),
    wohngeld_fallback_file: Annotated[Path, Product] = catalog_path(
        "wohngeld_fallback",
    ),
) -> None:
    """Join the § 12 WoGG parameters onto every Gemeinde and household size."""
    parameters = load_wohngeld_parameters(wohngeld_parameters_file)
    mietenstufen = read_mietenstufen(kdu_gemeinden_file)
    caps = pd.read_parquet(kdu_caps_file)

    hoechstbetrag = build_hoechstbetrag_only(mietenstufen, parameters)
    aligned = caps[["ags", "household_size"]].merge(
        hoechstbetrag,
        on=["ags", "household_size"],
        how="left",
        validate="one_to_one",
    )
    suspected = detect_wohngeld_rule(
        caps,
        aligned,
        notes_by_row(read_kdu_gemeinden(kdu_gemeinden_file), caps),
    )

    wohngeld_fallback_file.parent.mkdir(parents=True, exist_ok=True)
    build_wohngeld_fallback(mietenstufen, parameters, suspected).to_parquet(
        wohngeld_fallback_file,
        index=False,
    )
