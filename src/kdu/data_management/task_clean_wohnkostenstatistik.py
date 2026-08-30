"""Write the Bundesagentur statistic on housing costs of Bedarfsgemeinschaften."""

from pathlib import Path
from typing import Annotated

from pytask import Product

from kdu.config import DATA, LEGAL_VINTAGE, catalog_path
from kdu.data_management.clean_wohnkostenstatistik import (
    build_wohnkostenstatistik,
    read_committed_extract,
)

REFERENCE_MONTH = LEGAL_VINTAGE.wohnkostenstatistik_reference_month.replace("-", "")
WOHNKOSTEN_EXTRACT = (
    DATA / "ba_wohnkosten" / f"ba_wohnkosten_{REFERENCE_MONTH}_household_size.csv"
)


def task_clean_wohnkostenstatistik(
    extract_file: Path = WOHNKOSTEN_EXTRACT,
    wohnkostenstatistik_file: Annotated[Path, Product] = catalog_path(
        "wohnkostenstatistik",
    ),
) -> None:
    """Reshape the committed extract into one row per Jobcenter and household size."""
    statistic = build_wohnkostenstatistik(read_committed_extract(extract_file))
    wohnkostenstatistik_file.parent.mkdir(parents=True, exist_ok=True)
    statistic.to_parquet(wohnkostenstatistik_file, index=False)
