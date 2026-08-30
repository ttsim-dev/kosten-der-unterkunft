"""Write the transfer-exit thresholds under the local cap and under the fallback."""

from pathlib import Path
from typing import Annotated

import pandas as pd
from pytask import Product

from kdu.config import DATA, LEGAL_VINTAGE, catalog_path
from kdu.eligibility.microsimulation import (
    exit_threshold_by_gemeinde,
    national_heizkosten_eur_per_month,
    plot_exit_threshold_distribution,
    summarise_exit_thresholds,
)

REFERENCE_MONTH = LEGAL_VINTAGE.wohnkostenstatistik_reference_month.replace("-", "")
WOHNKOSTEN_EXTRACT = (
    DATA / "ba_wohnkosten" / f"ba_wohnkosten_{REFERENCE_MONTH}_household_size.csv"
)


def task_eligibility(
    kdu_caps_file: Path = catalog_path("kdu_caps"),
    wohngeld_fallback_file: Path = catalog_path("wohngeld_fallback"),
    wohnkosten_extract_file: Path = WOHNKOSTEN_EXTRACT,
    gemeinde_file: Annotated[Path, Product] = catalog_path("exit_threshold_gemeinde"),
    table_file: Annotated[Path, Product] = catalog_path("exit_threshold_table"),
    figure_file: Annotated[Path, Product] = catalog_path("exit_threshold_distribution"),
) -> None:
    """Simulate both scenarios and write the threshold frame, table and figure."""
    caps = pd.read_parquet(kdu_caps_file)
    fallback = pd.read_parquet(wohngeld_fallback_file)
    sample = caps.merge(
        fallback,
        on=["ags", "household_size"],
        how="inner",
        validate="one_to_one",
    )
    heating = national_heizkosten_eur_per_month(
        pd.read_csv(wohnkosten_extract_file, engine="pyarrow"),
    )
    thresholds = exit_threshold_by_gemeinde(sample, heating)

    gemeinde_file.parent.mkdir(parents=True, exist_ok=True)
    thresholds.to_parquet(gemeinde_file, index=False)
    summarise_exit_thresholds(thresholds).to_csv(table_file, index=False)
    plot_exit_threshold_distribution(thresholds).write_html(
        figure_file,
        include_plotlyjs="cdn",
    )
