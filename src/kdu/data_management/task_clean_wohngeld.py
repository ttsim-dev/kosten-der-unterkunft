"""Write the Grenze ohne schlüssiges Konzept for every Gemeinde and size."""

from pathlib import Path
from typing import Annotated

from pytask import Product

from kdu.config import catalog_path
from kdu.data_management.clean_wohngeld import (
    build_wohngeld_fallback,
    load_wohngeld_parameters,
    read_mietenstufen,
)


def task_clean_wohngeld(
    kdu_gemeinden_file: Path = catalog_path("kdu_gemeinden"),
    wohngeld_parameters_file: Path = catalog_path("wohngeld_parameters"),
    wohngeld_fallback_file: Annotated[Path, Product] = catalog_path(
        "wohngeld_fallback",
    ),
) -> None:
    """Join the § 12 WoGG parameters onto every Gemeinde and household size."""
    parameters = load_wohngeld_parameters(wohngeld_parameters_file)
    mietenstufen = read_mietenstufen(kdu_gemeinden_file)

    build_wohngeld_fallback(mietenstufen, parameters).to_parquet(
        wohngeld_fallback_file,
        index=False,
    )
