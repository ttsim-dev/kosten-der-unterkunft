"""Write the Gemeinde table: name, Kreis, Bundesland, and population."""

from pathlib import Path
from typing import Annotated

from pytask import Product

from kdu.config import catalog_path
from kdu.data_management.clean_gemeinden import (
    build_gemeinden,
    load_lookup,
    load_population,
)


def task_clean_gemeinden(
    lookup_file: Path = catalog_path("gemeinde_lookup"),
    population_file: Path = catalog_path("gemeinde_population"),
    gemeinden_file: Annotated[Path, Product] = catalog_path("gemeinden"),
) -> None:
    """Join the committed lookup and population tables into one Gemeinde table."""
    gemeinden = build_gemeinden(
        load_lookup(lookup_file),
        load_population(population_file),
    )
    gemeinden_file.parent.mkdir(parents=True, exist_ok=True)
    gemeinden.to_parquet(gemeinden_file, index=False)
