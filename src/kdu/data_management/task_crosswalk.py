"""Write the Gemeinde crosswalk required by §5.2."""

from pathlib import Path
from typing import Annotated, cast

import pandas as pd
from pytask import Product

from kdu.config import BLD, DATA_CATALOG
from kdu.data_management.ba import add_jobcenter_id
from kdu.data_management.crosswalk import build_crosswalk

_KDU_GEMEINDEN = cast("Path", DATA_CATALOG["kdu_gemeinden"])
_GEMEINDE_LOOKUP = cast("Path", DATA_CATALOG["gemeinde_lookup"])
_GEMEINDE_POPULATION = cast("Path", DATA_CATALOG["gemeinde_population"])
_MUNICIPALITY_CROSSWALK = cast("Path", DATA_CATALOG["municipality_crosswalk"])
_JOBCENTER_KREIS = BLD / "jobcenter_kreis_crosswalk.parquet"


def task_crosswalk(
    kdu_gemeinden_file: Path = _KDU_GEMEINDEN,
    gemeinde_lookup_file: Path = _GEMEINDE_LOOKUP,
    gemeinde_population_file: Path = _GEMEINDE_POPULATION,
    jobcenter_kreis_file: Path = _JOBCENTER_KREIS,
    crosswalk_file: Annotated[Path, Product] = _MUNICIPALITY_CROSSWALK,
) -> None:
    """Join geography, policy region, population, and Jobcenter into one table.

    `jobcenter_id` is filled here rather than in the BA module so that the
    crosswalk has exactly one producer. Berlin keeps a missing id: twelve
    Bezirks-Jobcenter serve the single Gemeinde, and no one id describes it.
    """
    kdu_gemeinden = pd.read_csv(
        kdu_gemeinden_file,
        dtype=str,
        keep_default_na=False,
        engine="pyarrow",
    )
    gemeinde_lookup = pd.read_feather(gemeinde_lookup_file)
    gemeinde_population = pd.read_feather(gemeinde_population_file)

    jobcenter_kreis = pd.read_parquet(jobcenter_kreis_file)

    crosswalk = add_jobcenter_id(
        build_crosswalk(kdu_gemeinden, gemeinde_lookup, gemeinde_population),
        jobcenter_kreis,
    )

    crosswalk_file.parent.mkdir(parents=True, exist_ok=True)
    crosswalk.to_parquet(crosswalk_file, index=False)
