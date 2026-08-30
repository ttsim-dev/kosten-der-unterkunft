"""Write the Wohngeld benchmark, long by Gemeinde and household size (P0.2)."""

from pathlib import Path
from typing import Annotated

from pytask import Product

from kdu.config import BLD
from kdu.data_management.wohngeld import (
    KDU_GEMEINDEN_PATH,
    WOGG_PARAMETERS_PATH,
    build_wogg_benchmark,
    load_wogg_parameters,
    read_kdu_gemeinden,
    reshape_kdu_caps_to_long,
)


def task_wogg_benchmark(
    kdu_gemeinden: Path = KDU_GEMEINDEN_PATH,
    wogg_parameters: Path = WOGG_PARAMETERS_PATH,
    benchmark: Annotated[Path, Product] = BLD / "wogg_benchmark.parquet",
) -> None:
    """Join the § 12 WoGG parameters onto every Gemeinde and household size."""
    parameters = load_wogg_parameters(wogg_parameters)
    gemeinden = read_kdu_gemeinden(kdu_gemeinden)
    result = build_wogg_benchmark(
        gemeinden,
        parameters,
        kdu_caps=reshape_kdu_caps_to_long(gemeinden),
    )
    benchmark.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(benchmark, index=False)
