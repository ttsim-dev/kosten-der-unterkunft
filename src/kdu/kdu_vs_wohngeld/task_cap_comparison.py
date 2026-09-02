"""Write the departure of local KdU caps from the Grenze ohne schlüssiges Konzept."""

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
    cap_ratio_pairs_across_household_sizes,
    cap_ratio_spread_across_household_sizes,
    plot_cap_difference_distribution,
    plot_cap_ratio_by_household_size,
    plot_cap_ratio_distribution,
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
    difference_file: Annotated[Path, Product] = catalog_path(
        "cap_difference_distribution",
    ),
    ratio_by_size_file: Annotated[Path, Product] = catalog_path(
        "cap_ratio_by_household_size",
    ),
    distribution_png_file: Annotated[Path, Product] = catalog_path(
        "cap_comparison_distribution_png",
    ),
    difference_png_file: Annotated[Path, Product] = catalog_path(
        "cap_difference_distribution_png",
    ),
    ratio_by_size_png_file: Annotated[Path, Product] = catalog_path(
        "cap_ratio_by_household_size_png",
    ),
    table_file: Annotated[Path, Product] = catalog_path("cap_comparison_table"),
) -> None:
    """Compare every local cap with that Grenze and write the results."""
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
    difference_figure = plot_cap_difference_distribution(frame)
    ratio_by_size_figure = plot_cap_ratio_by_household_size(
        cap_ratio_pairs_across_household_sizes(frame),
    )

    distribution_figure.write_html(distribution_file)
    difference_figure.write_html(difference_file)
    ratio_by_size_figure.write_html(ratio_by_size_file)
    write_presentation_png(distribution_figure, distribution_png_file)
    write_presentation_png(difference_figure, difference_png_file)
    write_presentation_png(ratio_by_size_figure, ratio_by_size_png_file)
    table.to_csv(table_file, index=False)
