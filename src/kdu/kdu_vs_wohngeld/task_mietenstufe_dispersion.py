"""Write how much local KdU variation the statutory Mietenstufe accounts for."""

from pathlib import Path
from typing import Annotated

import pandas as pd
from pytask import Product

from kdu.config import catalog_path
from kdu.figure_export import write_presentation_png
from kdu.kdu_vs_wohngeld.cap_comparison import build_cap_comparison
from kdu.kdu_vs_wohngeld.mietenstufe_dispersion import (
    dispersion_within_mietenstufe,
    plot_mietenstufe_dispersion,
    variance_shares,
)


def task_mietenstufe_dispersion(
    caps_file: Path = catalog_path("kdu_caps"),
    fallback_file: Path = catalog_path("wohngeld_fallback"),
    gemeinden_file: Path = catalog_path("gemeinden"),
    figure_file: Annotated[Path, Product] = catalog_path(
        "mietenstufe_dispersion_figure",
    ),
    figure_png_file: Annotated[Path, Product] = catalog_path(
        "mietenstufe_dispersion_figure_png",
    ),
    shares_file: Annotated[Path, Product] = catalog_path("mietenstufe_variance_shares"),
) -> None:
    """Measure the dispersion inside each Mietenstufe and write the results."""
    frame = build_cap_comparison(
        pd.read_parquet(caps_file),
        pd.read_parquet(fallback_file),
        pd.read_parquet(gemeinden_file),
    )
    shares = variance_shares(frame)
    dispersion = dispersion_within_mietenstufe(frame)

    figure = plot_mietenstufe_dispersion(frame, shares)

    figure.write_html(figure_file)
    write_presentation_png(figure, figure_png_file)
    pd.concat(
        [
            dispersion.assign(measure="dispersion_within_mietenstufe"),
            shares.assign(measure="variance_share_between_groups"),
        ],
        ignore_index=True,
    ).to_csv(shares_file, index=False)
