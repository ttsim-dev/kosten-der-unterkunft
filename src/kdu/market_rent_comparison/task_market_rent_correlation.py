"""Write the correlation of each cap with the local market rent."""

from pathlib import Path
from typing import Annotated

import pandas as pd
from pytask import Product

from kdu.config import catalog_path
from kdu.figure_export import write_presentation_png
from kdu.market_rent_comparison.market_rent_correlation import (
    build_analysis_frame,
    correlation_table,
    market_rent_correlation_figure,
)

KDU_CAPS = catalog_path("kdu_caps")
WOHNGELD_FALLBACK = catalog_path("wohngeld_fallback")
ZENSUS_RENTS = catalog_path("zensus_rents")
CORRELATION_TABLE = catalog_path("market_rent_correlation_table")
CORRELATION_FIGURE = catalog_path("market_rent_correlation_figure")
CORRELATION_FIGURE_PNG = catalog_path("market_rent_correlation_figure_png")


def task_market_rent_correlation(
    kdu_caps_file: Path = KDU_CAPS,
    wohngeld_fallback_file: Path = WOHNGELD_FALLBACK,
    zensus_rents_file: Path = ZENSUS_RENTS,
    table_file: Annotated[Path, Product] = CORRELATION_TABLE,
    figure_file: Annotated[Path, Product] = CORRELATION_FIGURE,
    figure_png_file: Annotated[Path, Product] = CORRELATION_FIGURE_PNG,
) -> None:
    """Correlate both caps with the Zensus rent level, overall and within a stufe."""
    frame = build_analysis_frame(
        pd.read_parquet(kdu_caps_file),
        pd.read_parquet(wohngeld_fallback_file),
        pd.read_parquet(zensus_rents_file),
    )
    table = correlation_table(frame)
    figure = market_rent_correlation_figure(table)

    table.to_csv(table_file, index=False)
    figure.write_html(figure_file, include_plotlyjs="cdn")
    write_presentation_png(figure, figure_png_file)
