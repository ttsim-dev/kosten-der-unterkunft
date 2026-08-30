"""Fetch the Zensus 2022 Gemeinde rents once and commit the extract.

Run this by hand, not from the pytask graph:

```bash
pixi run python scripts/fetch_zensus_mieten.py
```

The source is the Regionaltabelle "Gebäude und Wohnungen", a 21 MB workbook that
Destatis serves without registration. Its `CSV-Wohnungen` sheet is the only free
Gemeinde-level release of the Zensus 2022 Nettokaltmiete. This script keeps the
rent, floor-area and dwelling-count columns and writes them to
`data/zensus/zensus2022_nettokaltmiete_gemeinden.csv` together with a manifest
recording the source URL, the retrieval date and the SHA-256 of the workbook.

The mean Nettokaltmiete *within* a floor-area class lives only in the
Zensusdatenbank, whose API returns 403 to unauthenticated requests. See
the Zensus 2022 release notes.
"""

import csv
import datetime as dt
import hashlib
import sys
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kdu.data_management.clean_zensus_rents import (
    RENT_CLASS_MEASURES,
    SCALAR_MEASURES,
)

# Dwelling counts by floor-area class. The cleaning layer does not read these,
# but they are extracted so the committed table carries the full Zensus record.
FLOOR_AREA_CLASS_MEASURES: Mapping[str, str] = MappingProxyType(
    {
        "WOHNFLAECHE_20S__01": "dwellings_floor_area_sqm_under_40",
        "WOHNFLAECHE_20S__02": "dwellings_floor_area_sqm_40_to_59",
        "WOHNFLAECHE_20S__03": "dwellings_floor_area_sqm_60_to_79",
        "WOHNFLAECHE_20S__04": "dwellings_floor_area_sqm_80_to_99",
        "WOHNFLAECHE_20S__05": "dwellings_floor_area_sqm_100_to_119",
        "WOHNFLAECHE_20S__06": "dwellings_floor_area_sqm_120_to_139",
        "WOHNFLAECHE_20S__07": "dwellings_floor_area_sqm_140_to_159",
        "WOHNFLAECHE_20S__08": "dwellings_floor_area_sqm_160_to_179",
        "WOHNFLAECHE_20S__09": "dwellings_floor_area_sqm_180_to_199",
        "WOHNFLAECHE_20S__10": "dwellings_floor_area_sqm_200_and_more",
    },
)

SOURCE_URL = (
    "https://www.destatis.de/static/DE/zensus/gitterdaten/"
    "Regionaltabelle_Gebaeude_Wohnungen.xlsx"
)
SHEET = "CSV-Wohnungen"

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "zensus"
CACHE_DIR = ROOT / "bld" / "zensus_downloads"

KEY_COLUMNS = ("Berichtszeitpunkt", "_RS", "Name", "Regionalebene")


def main() -> None:
    """Download the Regionaltabelle and write the committed extract."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    retrieved = dt.date.today().isoformat()

    workbook = CACHE_DIR / "Regionaltabelle_Gebaeude_Wohnungen.xlsx"
    payload = _download(SOURCE_URL, workbook)
    print(f"{workbook.name}: {len(payload):,} bytes")

    raw = _read_sheet(workbook)
    wanted = [
        *KEY_COLUMNS,
        *SCALAR_MEASURES,
        *RENT_CLASS_MEASURES,
        *FLOOR_AREA_CLASS_MEASURES,
    ]
    extract = raw[list(wanted)]
    extract_path = DATA_DIR / "zensus2022_nettokaltmiete_gemeinden.csv"
    extract.to_csv(extract_path, index=False)
    print(f"wrote {extract_path} ({len(extract):,} rows)")

    manifest_path = DATA_DIR / "zensus_download_manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source",
                "sheet",
                "source_url",
                "retrieved_date",
                "n_bytes",
                "sha256",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "source": (
                    "Statistisches Bundesamt, Zensus 2022, Regionaltabelle "
                    "Gebäude und Wohnungen"
                ),
                "sheet": SHEET,
                "source_url": SOURCE_URL,
                "retrieved_date": retrieved,
                "n_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    print(f"wrote {manifest_path}")


def _read_sheet(path: Path) -> pd.DataFrame:
    import openpyxl

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows = list(workbook[SHEET].iter_rows(values_only=True))
    finally:
        workbook.close()
    header, *body = rows
    return pd.DataFrame(body, columns=[str(c) for c in header])


def _download(url: str, path: Path) -> bytes:
    if path.exists():
        return path.read_bytes()
    request = urllib.request.Request(url, headers={"User-Agent": "kdu-research/1.0"})
    with urllib.request.urlopen(request, timeout=600) as response:
        payload = response.read()
    path.write_bytes(payload)
    return payload


if __name__ == "__main__":
    main()
