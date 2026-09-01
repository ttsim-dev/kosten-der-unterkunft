"""Write what GETTSIM's own national housing rule recognises, per household size."""

from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import pandas as pd
from pytask import Product

from kdu.config import ELIGIBILITY, catalog_path
from kdu.eligibility.gettsim_national_rule import (
    ILLUSTRATIVE_DWELLING_BRUTTOKALTMIETE_EUR_PER_MONTH,
    ILLUSTRATIVE_DWELLING_HEIZKOSTEN_EUR_PER_MONTH,
    ILLUSTRATIVE_DWELLING_WOHNFLAECHE_SQM,
    compare_separate_caps_to_monthly_ceiling,
    gettsim_comparison_table,
    median_local_cap_eur_per_month,
)
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


def task_separate_caps_comparison(
    kdu_caps_file: Path = catalog_path("kdu_caps"),
    table_file: Annotated[Path, Product] = (
        ELIGIBILITY / "separate_caps_comparison.csv"
    ),
) -> None:
    """Write the illustrative dwelling under both functional forms.

    The monthly Bruttokaltmiete ceiling the dwelling is held against is the
    median one-person cap of the collected Richtlinien, read off the cap table
    rather than fixed here, so the figure moves with the collected data.

    Every component is written on its own: GETTSIM's side is a single warm
    amount, the Richtlinie's side is a recognised cold amount beside a
    separately recognised heating amount, and merging them would erase the
    difference the comparison exists to show.
    """
    caps = pd.read_parquet(kdu_caps_file)
    comparison = compare_separate_caps_to_monthly_ceiling(
        wohnflaeche_sqm=ILLUSTRATIVE_DWELLING_WOHNFLAECHE_SQM,
        bruttokaltmiete_m=ILLUSTRATIVE_DWELLING_BRUTTOKALTMIETE_EUR_PER_MONTH,
        heizkosten_m=ILLUSTRATIVE_DWELLING_HEIZKOSTEN_EUR_PER_MONTH,
        local_bruttokaltmiete_cap_m=median_local_cap_eur_per_month(caps, 1),
    )
    pd.DataFrame([asdict(comparison)]).to_csv(table_file, index=False)
