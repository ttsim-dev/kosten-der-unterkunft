"""Write the Zensus 2022 rents of each Gemeinde's rented housing stock."""

from pathlib import Path
from typing import Annotated

from pytask import Product

from kdu.config import DATA, catalog_path
from kdu.data_management.clean_zensus_rents import (
    build_zensus_rents,
    read_zensus_extract,
)

ZENSUS_EXTRACT = DATA / "zensus" / "zensus2022_nettokaltmiete_gemeinden.csv"


def task_clean_zensus_rents(
    extract_file: Path = ZENSUS_EXTRACT,
    zensus_rents_file: Annotated[Path, Product] = catalog_path("zensus_rents"),
) -> None:
    """Parse the committed Zensus extract into one row per Gemeinde."""
    rents = build_zensus_rents(read_zensus_extract(extract_file))
    zensus_rents_file.parent.mkdir(parents=True, exist_ok=True)
    rents.to_parquet(zensus_rents_file, index=False)
