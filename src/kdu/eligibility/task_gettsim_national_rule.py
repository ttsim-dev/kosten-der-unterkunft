"""Write what GETTSIM's own national housing rule recognises, per household size."""

from pathlib import Path
from typing import Annotated

import pandas as pd
from pytask import Product

from kdu.config import ELIGIBILITY, catalog_path
from kdu.eligibility.gettsim_national_rule import gettsim_comparison_table
from kdu.eligibility.microsimulation import national_heizkosten_eur_per_month


def task_gettsim_national_rule(
    kdu_caps_file: Path = catalog_path("kdu_caps"),
    wohngeld_fallback_file: Path = catalog_path("wohngeld_fallback"),
    wohnkostenstatistik_file: Path = catalog_path("wohnkostenstatistik"),
    table_file: Annotated[Path, Product] = (
        ELIGIBILITY / "gettsim_national_rule_comparison.csv"
    ),
) -> None:
    """Compare GETTSIM's rule, the local cap and the Wohngeld fallback."""
    heating = national_heizkosten_eur_per_month(
        pd.read_parquet(wohnkostenstatistik_file),
    )
    comparison = gettsim_comparison_table(
        caps=pd.read_parquet(kdu_caps_file),
        fallback=pd.read_parquet(wohngeld_fallback_file),
        heating=heating,
    )
    comparison.to_csv(table_file, index=False)
