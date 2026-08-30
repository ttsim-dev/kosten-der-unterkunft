"""Build the Zensus 2022 Bestandsmiete table (P1.3, §15)."""

from pathlib import Path
from typing import Annotated

import pandas as pd
from pytask import Product

from kdu.config import BLD, DATA
from kdu.data_management.zensus import (
    add_ags_eight_digit,
    build_zensus_rents,
    select_gemeinden,
)


def task_zensus_rents(
    extract: Path = DATA / "zensus" / "zensus2022_nettokaltmiete_gemeinden.csv",
    all_levels: Annotated[Path, Product] = BLD / "zensus_rents_all_levels.parquet",
    gemeinden: Annotated[Path, Product] = BLD / "zensus_rents_gemeinden.parquet",
) -> None:
    """Parse the committed Zensus extract into the long Bestandsmiete tables."""
    raw = pd.read_csv(extract, dtype=str, engine="pyarrow")
    long_frame = build_zensus_rents(raw)
    long_frame.to_parquet(all_levels, index=False)
    add_ags_eight_digit(select_gemeinden(long_frame)).to_parquet(gemeinden, index=False)
    # Both are datasets, not figures or tables, so they stay out of
    # results_manifest.csv, which §5.2 reserves for presented output.
