"""Write the departure of local KdU caps from the statutory fallback."""

from pathlib import Path
from typing import Annotated

import pandas as pd
from pytask import Product

from kdu.config import catalog_path
from kdu.kdu_vs_wohngeld.cap_comparison import (
    attach_weights,
    bedarfsgemeinschaft_weights,
    build_cap_comparison,
    cap_ratio_spread_across_household_sizes,
    plot_cap_ratio_distribution,
    plot_cap_ratio_spread_distribution,
    stack_populations,
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
    table_file: Annotated[Path, Product] = catalog_path("cap_comparison_table"),
) -> None:
    """Compare every local cap with its statutory fallback and write the results."""
    frame = build_cap_comparison(
        pd.read_parquet(caps_file),
        pd.read_parquet(fallback_file),
        pd.read_parquet(gemeinden_file),
    )
    weighted = attach_weights(
        frame,
        bedarfsgemeinschaft_weights(pd.read_parquet(wohnkostenstatistik_file)),
    )
    by_population = stack_populations(weighted)
    spread = stack_populations(cap_ratio_spread_across_household_sizes(frame))

    table = pd.concat(
        [summarise_cap_ratio(by_population), summarise_cap_ratio_spread(spread)],
        ignore_index=True,
    )

    distribution_file.parent.mkdir(parents=True, exist_ok=True)
    plot_cap_ratio_distribution(by_population).write_html(distribution_file)
    plot_cap_ratio_spread_distribution(spread).write_html(spread_file)
    table.to_csv(table_file, index=False)
