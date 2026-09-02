"""Write the local cap read against its own Gemeinde's mean Bestandsmiete."""

from pathlib import Path
from typing import Annotated

import pandas as pd
from pytask import Product

from kdu.config import catalog_path
from kdu.figure_export import write_presentation_png
from kdu.market_rent_comparison.cap_over_bestandsmiete import (
    build_cap_over_bestandsmiete,
    cap_over_bestandsmiete_figure,
    summarise_cap_over_bestandsmiete,
)

GEMEINDE_SHARES = catalog_path("share_of_stock_above_cap_gemeinde")
ZENSUS_RENTS = catalog_path("zensus_rents")
FIGURE = catalog_path("cap_over_bestandsmiete")
FIGURE_PNG = catalog_path("cap_over_bestandsmiete_png")
TABLE = catalog_path("cap_over_bestandsmiete_table")


def task_cap_over_bestandsmiete(
    gemeinde_shares_file: Path = GEMEINDE_SHARES,
    zensus_rents_file: Path = ZENSUS_RENTS,
    figure_file: Annotated[Path, Product] = FIGURE,
    figure_png_file: Annotated[Path, Product] = FIGURE_PNG,
    table_file: Annotated[Path, Product] = TABLE,
) -> None:
    """Compare each local cap with the mean Bestandsmiete of its own Gemeinde."""
    frame = build_cap_over_bestandsmiete(
        pd.read_parquet(gemeinde_shares_file),
        pd.read_parquet(zensus_rents_file),
    )
    summary = summarise_cap_over_bestandsmiete(frame)
    figure = cap_over_bestandsmiete_figure(frame)

    summary.to_csv(table_file, index=False)
    figure.write_html(figure_file, include_plotlyjs="cdn")
    write_presentation_png(figure, figure_png_file)
