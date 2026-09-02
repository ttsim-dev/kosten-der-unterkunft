"""Write the transfer-exit thresholds under the local cap and under the Grenze.

The Grenze is the Angemessenheitsgrenze ohne schlüssiges Konzept: the cap BSG
case law prescribes where a Kreis has published no schlüssiges Konzept.
"""

from pathlib import Path
from typing import Annotated

import pandas as pd
from pytask import Product

from kdu.config import ELIGIBILITY, catalog_path
from kdu.eligibility.microsimulation import (
    ENTITLEMENT_PROFILE_AGS,
    entitlement_profile,
    exit_threshold_by_gemeinde,
    national_heizkosten_eur_per_month,
    plot_entitlement_profile,
    plot_exit_threshold_distribution,
    summarise_exit_thresholds,
)
from kdu.figure_export import write_presentation_png


def task_eligibility(
    kdu_caps_file: Path = catalog_path("kdu_caps"),
    wohngeld_fallback_file: Path = catalog_path("wohngeld_fallback"),
    wohnkostenstatistik_file: Path = catalog_path("wohnkostenstatistik"),
    gemeinde_file: Annotated[Path, Product] = catalog_path("exit_threshold_gemeinde"),
    table_file: Annotated[Path, Product] = catalog_path("exit_threshold_table"),
    figure_file: Annotated[Path, Product] = catalog_path(
        "exit_threshold_distribution",
    ),
    figure_png_file: Annotated[Path, Product] = catalog_path(
        "exit_threshold_distribution_png",
    ),
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
        pd.read_parquet(wohnkostenstatistik_file),
    )
    thresholds = exit_threshold_by_gemeinde(sample, heating)

    thresholds.to_parquet(gemeinde_file, index=False)
    summarise_exit_thresholds(thresholds).to_csv(table_file, index=False)
    figure = plot_exit_threshold_distribution(thresholds)
    figure.write_html(figure_file, include_plotlyjs="cdn")
    write_presentation_png(figure, figure_png_file)


def task_entitlement_profile(
    kdu_caps_file: Path = catalog_path("kdu_caps"),
    wohngeld_fallback_file: Path = catalog_path("wohngeld_fallback"),
    wohnkostenstatistik_file: Path = catalog_path("wohnkostenstatistik"),
    gemeinden_file: Path = catalog_path("gemeinden"),
    figure_file: Annotated[Path, Product] = (ELIGIBILITY / "entitlement_profile.html"),
    figure_png_file: Annotated[Path, Product] = (
        ELIGIBILITY / "entitlement_profile.png"
    ),
) -> None:
    """Draw one Gemeinde's claim falling to zero under each of the two caps.

    The Gemeinde's name is read from the cleaned Gemeinde table rather than
    written here, so the figure cannot name one Gemeinde while plotting another.
    """
    caps = pd.read_parquet(kdu_caps_file)
    fallback = pd.read_parquet(wohngeld_fallback_file)
    sample = caps.merge(
        fallback,
        on=["ags", "household_size"],
        how="inner",
        validate="one_to_one",
    )
    heating = national_heizkosten_eur_per_month(
        pd.read_parquet(wohnkostenstatistik_file),
    )
    profile = entitlement_profile(sample, heating)
    gemeinden = pd.read_parquet(gemeinden_file)
    name = gemeinden.set_index("ags").loc[ENTITLEMENT_PROFILE_AGS, "municipality_name"]
    figure = plot_entitlement_profile(profile, gemeinde_name=str(name))
    figure.write_html(figure_file, include_plotlyjs="cdn")
    write_presentation_png(figure, figure_png_file)
