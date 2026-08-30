"""Write the comparison of the collected caps with the Bundesagentur record."""

from pathlib import Path
from typing import Annotated

import pandas as pd
from pytask import Product

from kdu.config import catalog_path
from kdu.validation.validate_against_wohnkostenstatistik import (
    build_district_market_pressure,
    validate_against_wohnkostenstatistik,
)

KDU_CAPS_FILE = catalog_path("kdu_caps")
GEMEINDEN_FILE = catalog_path("gemeinden")
ZENSUS_RENTS_FILE = catalog_path("zensus_rents")
WOHNKOSTENSTATISTIK_FILE = catalog_path("wohnkostenstatistik")
VALIDATION_FILE = catalog_path("wohnkostenstatistik_validation")


def task_validate_against_wohnkostenstatistik(
    kdu_caps_file: Path = KDU_CAPS_FILE,
    gemeinden_file: Path = GEMEINDEN_FILE,
    zensus_rents_file: Path = ZENSUS_RENTS_FILE,
    wohnkostenstatistik_file: Path = WOHNKOSTENSTATISTIK_FILE,
    validation_file: Annotated[Path, Product] = VALIDATION_FILE,
) -> None:
    """Compare cap tightness with the share of housing costs left unrecognised."""
    market_pressure = build_district_market_pressure(
        pd.read_parquet(kdu_caps_file),
        pd.read_parquet(gemeinden_file),
        pd.read_parquet(zensus_rents_file),
    )
    table = validate_against_wohnkostenstatistik(
        pd.read_parquet(wohnkostenstatistik_file),
        market_pressure,
    )
    validation_file.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(validation_file, index=False)
