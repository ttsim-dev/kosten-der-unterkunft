"""Project paths."""

from pathlib import Path

from pytask import DataCatalog

SRC = Path(__file__).parent.resolve()
ROOT = SRC.parent.parent
BLD = ROOT / "bld"
DATA = ROOT / "data"

DATA_CATALOG = DataCatalog(name="kdu")
DATA_CATALOG.add("gemeinden_geojson", DATA / "gemeinden.geo.json")
DATA_CATALOG.add("gemeinde_lookup", DATA / "gemeinde_lookup.arrow")
DATA_CATALOG.add("kdu_gemeinden", DATA / "kdu_gemeinden.csv")
DATA_CATALOG.add("germany_map", BLD / "germany_map.html")
