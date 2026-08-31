"""Write the share of each Gemeinde's rented stock priced above each cap."""

from pathlib import Path
from typing import Annotated

import pandas as pd
from pytask import Product

from kdu.config import catalog_path
from kdu.market_rent_comparison.share_of_stock_above_cap import (
    build_gemeinde_shares,
    share_of_stock_above_cap_figure,
    summarise_shares,
)

KDU_CAPS = catalog_path("kdu_caps")
WOHNGELD_FALLBACK = catalog_path("wohngeld_fallback")
ZENSUS_RENTS = catalog_path("zensus_rents")
GEMEINDEN = catalog_path("gemeinden")
WOHNKOSTENSTATISTIK = catalog_path("wohnkostenstatistik")
GEMEINDE_SHARES = catalog_path("share_of_stock_above_cap_gemeinde")
SHARES_TABLE = catalog_path("share_of_stock_above_cap_table")
SHARES_FIGURE = catalog_path("share_of_stock_above_cap_figure")


def task_share_of_stock_above_cap(
    kdu_caps_file: Path = KDU_CAPS,
    wohngeld_fallback_file: Path = WOHNGELD_FALLBACK,
    zensus_rents_file: Path = ZENSUS_RENTS,
    gemeinden_file: Path = GEMEINDEN,
    wohnkostenstatistik_file: Path = WOHNKOSTENSTATISTIK,
    gemeinde_file: Annotated[Path, Product] = GEMEINDE_SHARES,
    table_file: Annotated[Path, Product] = SHARES_TABLE,
    figure_file: Annotated[Path, Product] = SHARES_FIGURE,
) -> None:
    """Count the rented dwellings each cap prices above itself, per Gemeinde."""
    gemeinde_shares = build_gemeinde_shares(
        pd.read_parquet(kdu_caps_file),
        pd.read_parquet(wohngeld_fallback_file),
        pd.read_parquet(zensus_rents_file),
        pd.read_parquet(gemeinden_file),
        pd.read_parquet(wohnkostenstatistik_file),
    )
    summary = summarise_shares(gemeinde_shares)
    figure = share_of_stock_above_cap_figure(gemeinde_shares)

    gemeinde_shares.to_parquet(gemeinde_file, index=False)
    summary.to_csv(table_file, index=False)
    figure.write_html(figure_file, include_plotlyjs="cdn")
