"""Build the BA Wohnkosten tables, outcomes and Jobcenter crosswalk (P1.2, §14)."""

from pathlib import Path
from typing import Annotated

import pandas as pd
from pytask import Product

from kdu.config import BLD, DATA
from kdu.data_management.ba import (
    build_ba_outcomes,
    build_jobcenter_kreis_crosswalk,
    check_jobcenter_kreis_stocks,
    gather_categories,
    read_committed_extract,
    split_validation_samples,
)

BA_DIR = DATA / "ba_wohnkosten"
REFERENCE_MONTH = "202604"
ANNUAL_MEAN_WINDOW = "202505_202604"


def task_ba_wohnkosten(
    household_size: Path = BA_DIR
    / f"ba_wohnkosten_{REFERENCE_MONTH}_household_size.csv",
    bg_type: Path = BA_DIR / f"ba_wohnkosten_{REFERENCE_MONTH}_bg_type.csv",
    annual_household_size: Path = BA_DIR
    / f"ba_wohnkosten_annual_mean_{ANNUAL_MEAN_WINDOW}_household_size.csv",
    annual_bg_type: Path = BA_DIR
    / f"ba_wohnkosten_annual_mean_{ANNUAL_MEAN_WINDOW}_bg_type.csv",
    reference_long: Annotated[Path, Product] = BLD / "ba_wohnkosten_long.parquet",
    annual_long: Annotated[Path, Product] = BLD
    / "ba_wohnkosten_annual_mean_long.parquet",
    outcomes: Annotated[Path, Product] = BLD / "ba_validation_outcomes.parquet",
) -> None:
    """Melt the committed extracts and derive the §14.2 validation outcomes."""
    reference = _read_long(household_size, bg_type)
    annual = _read_long(annual_household_size, annual_bg_type)
    reference.to_parquet(reference_long, index=False)
    annual.to_parquet(annual_long, index=False)
    build_ba_outcomes(reference).to_parquet(outcomes, index=False)
    # These three are datasets, not figures or tables, so they stay out of
    # results_manifest.csv, which §5.2 reserves for presented output.


def task_ba_jobcenter_crosswalk(
    household_size: Path = BA_DIR
    / f"ba_wohnkosten_{REFERENCE_MONTH}_household_size.csv",
    kdu_gemeinden: Path = DATA / "kdu_gemeinden.csv",
    crosswalk: Annotated[Path, Product] = BLD / "jobcenter_kreis_crosswalk.parquet",
    stock_check: Annotated[Path, Product] = BLD / "jobcenter_kreis_stock_check.parquet",
) -> None:
    """Map Jobcenter to Kreise and split them into the two §14.3 samples.

    Under D1 the policy region is the Kreis, so a Jobcenter serving one Kreis serves
    one policy region. Whether its territory carries a *uniform* KdU rule is a
    separate question that `data/kdu_gemeinden.csv` answers: a Kreis whose Gemeinden
    all share one Bruttokaltmiete cap for a single-person household has one rule.
    """
    frame = read_committed_extract(household_size, "household_size")
    mapping = build_jobcenter_kreis_crosswalk(frame)

    kdu = pd.read_csv(kdu_gemeinden, dtype=str, engine="pyarrow")
    kdu = kdu.assign(ags_kreis=kdu["ags_kreis"].str.zfill(5))
    kreisfrei = _kreisfreie_staedte(kdu)
    uniform = _uniform_cap_per_kreis(kdu)

    samples = split_validation_samples(mapping, kreisfrei, uniform)
    samples.to_parquet(crosswalk, index=False)
    check_jobcenter_kreis_stocks(
        mapping, gather_categories(frame, "household_size")
    ).to_parquet(stock_check, index=False)


def _read_long(household_size: Path, bg_type: Path) -> pd.DataFrame:
    frames = [
        gather_categories(read_committed_extract(path, breakdown), breakdown)
        for path, breakdown in (
            (household_size, "household_size"),
            (bg_type, "bg_type"),
        )
    ]
    return pd.concat(frames, ignore_index=True)


def _kreisfreie_staedte(kdu: pd.DataFrame) -> list[str]:
    """Return the AGS of Kreise that hold exactly one Gemeinde.

    A kreisfreie Stadt is its own Kreis, so it is the only Gemeinde in it.
    """
    per_kreis = kdu.groupby("ags_kreis")["ags_gemeinde"].nunique()
    return per_kreis[per_kreis == 1].index.tolist()


def _uniform_cap_per_kreis(kdu: pd.DataFrame) -> dict[str, float]:
    """Return the single single-person cap of each Kreis that carries exactly one.

    D1 records that 210 of 400 Kreise define Vergleichsräume and therefore carry
    several caps. Those are absent from the result, as are Kreise with no cap at
    all, so a Jobcenter covering one of them cannot claim a uniform rule.
    """
    caps = kdu.dropna(subset=["max_bruttokaltmiete_eur_1p"])
    grouped = caps.groupby("ags_kreis")["max_bruttokaltmiete_eur_1p"]
    single = grouped.nunique() == 1
    return grouped.first()[single].astype(float).to_dict()
