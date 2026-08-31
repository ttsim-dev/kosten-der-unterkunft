"""Write the departure of local KdU caps from the statutory fallback."""

from pathlib import Path
from typing import Annotated

import pandas as pd
from pytask import Product

from kdu.config import catalog_path
from kdu.figure_export import write_presentation_png
from kdu.kdu_vs_wohngeld.cap_comparison import (
    allocate_bedarfsgemeinschaften_to_gemeinden,
    attach_weights,
    bedarfsgemeinschaft_weights,
    build_cap_comparison,
    cap_ratio_spread_across_household_sizes,
    plot_cap_ratio_distribution,
    plot_cap_ratio_spread_distribution,
    summarise_cap_difference_eur,
    summarise_cap_ratio,
    summarise_cap_ratio_spread,
)


def task_cap_comparison(
    caps_file: Path = catalog_path("kdu_caps"),
    fallback_file: Path = catalog_path("wohngeld_fallback"),
    gemeinden_file: Path = catalog_path("gemeinden"),
    wohnkostenstatistik_file: Path = catalog_path("wohnkostenstatistik"),
    distribution_file: Annotated[Path, Product] = catalog_path(
        "cap_comparison_distribution",
    ),
    spread_file: Annotated[Path, Product] = catalog_path(
        "cap_ratio_spread_distribution",
    ),
    distribution_png_file: Annotated[Path, Product] = catalog_path(
        "cap_comparison_distribution_png",
    ),
    spread_png_file: Annotated[Path, Product] = catalog_path(
        "cap_ratio_spread_distribution_png",
    ),
    table_file: Annotated[Path, Product] = catalog_path("cap_comparison_table"),
) -> None:
    """Compare every local cap with its statutory fallback and write the results."""
    gemeinden = pd.read_parquet(gemeinden_file)
    frame = build_cap_comparison(
        pd.read_parquet(caps_file),
        pd.read_parquet(fallback_file),
        gemeinden,
    )
    weighted = attach_weights(
        frame,
        allocate_bedarfsgemeinschaften_to_gemeinden(
            bedarfsgemeinschaft_weights(pd.read_parquet(wohnkostenstatistik_file)),
            gemeinden,
        ),
    )
    spread = cap_ratio_spread_across_household_sizes(frame)

    table = pd.concat(
        [
            summarise_cap_ratio(weighted),
            summarise_cap_difference_eur(weighted),
            summarise_cap_ratio_spread(spread),
        ],
        ignore_index=True,
    )

    distribution_figure = plot_cap_ratio_distribution(weighted)
    spread_figure = plot_cap_ratio_spread_distribution(spread)

    distribution_figure.write_html(distribution_file)
    spread_figure.write_html(spread_file)
    write_presentation_png(distribution_figure, distribution_png_file)
    write_presentation_png(spread_figure, spread_png_file)
    table.to_csv(table_file, index=False)
