"""Write the long table of local KdU caps and the documents it cites."""

from pathlib import Path
from typing import Annotated

from pytask import Product

from kdu.config import catalog_path
from kdu.data_management.clean_kdu_regions import (
    build_kdu_caps,
    build_kdu_sources,
    read_kdu_gemeinden,
)


def task_clean_kdu_regions(
    kdu_gemeinden_file: Path = catalog_path("kdu_gemeinden"),
    kdu_caps_file: Annotated[Path, Product] = catalog_path("kdu_caps"),
    kdu_sources_file: Annotated[Path, Product] = catalog_path("kdu_sources"),
) -> None:
    """Reshape the committed wide table into the cap and document tables."""
    wide = read_kdu_gemeinden(kdu_gemeinden_file)
    kdu_caps_file.parent.mkdir(parents=True, exist_ok=True)
    build_kdu_caps(wide).to_parquet(kdu_caps_file, index=False)
    build_kdu_sources(wide).to_parquet(kdu_sources_file, index=False)
