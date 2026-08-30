"""Prepare the Gemeinde data artifacts from the OpenDataSoft source.

Fetches the raw ``georef-germany-gemeinde`` export (~58 MB) into ``bld/``
(gitignored) and writes two committed files under ``data/``:

- `gemeinden.geo.json` — boundaries simplified to a ~1 km grid.
- `gemeinde_lookup.arrow` — AGS → (Gemeinde, Kreis, Bundesland) table.

Re-run to regenerate:

    python scripts/prepare_gemeinden.py
"""

import json
import urllib.request
from typing import Any

from kdu.config import BLD, DATA
from kdu.geodata import simplify_feature_collection
from kdu.lookup import build_gemeinde_lookup

SOURCE_URL = (
    "https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    "georef-germany-gemeinde/exports/geojson?limit=-1"
)
# Grid resolution for simplification (2 ≈ 1 km), keeping the file < 10 MB.
DECIMALS = 2


def main() -> None:
    """Download the raw boundaries, simplify them, and write the slim file."""
    BLD.mkdir(exist_ok=True)
    DATA.mkdir(exist_ok=True)
    raw_path = BLD / "gemeinden_raw.geojson"
    if not raw_path.exists():
        print(f"downloading {SOURCE_URL}")
        urllib.request.urlretrieve(SOURCE_URL, raw_path)
    raw = json.loads(raw_path.read_text(encoding="utf-8"))

    slim = _slim_properties(simplify_feature_collection(raw, decimals=DECIMALS))
    geojson_path = DATA / "gemeinden.geo.json"
    geojson_path.write_text(json.dumps(slim), encoding="utf-8")
    size_mb = geojson_path.stat().st_size / 1e6
    print(f"{len(slim['features'])} Gemeinden → {geojson_path} ({size_mb:.1f} MB)")

    lookup = build_gemeinde_lookup(raw)
    lookup_path = DATA / "gemeinde_lookup.arrow"
    lookup.to_feather(lookup_path)
    print(f"{len(lookup)} rows → {lookup_path}")


def _slim_properties(geojson: dict[str, Any]) -> dict[str, Any]:
    """Keep only the AGS and name; the source carries a dozen fields."""
    features = []
    for feature in geojson["features"]:
        properties = feature["properties"]
        code = properties.get("gem_code")
        name = properties.get("gem_name_short") or properties.get("gem_name")
        features.append(
            {
                "type": "Feature",
                "geometry": feature["geometry"],
                "properties": {
                    "gem_code": code[0] if isinstance(code, list) else code,
                    "gem_name": name[0] if isinstance(name, list) else name,
                },
            },
        )
    return {"type": "FeatureCollection", "features": features}


if __name__ == "__main__":
    main()
