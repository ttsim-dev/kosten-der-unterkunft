# kdu

Prototype choropleth maps of Germany at **Gemeinde** level (~11,000 municipalities),
filled with **placeholder data**. It proves out the render + join pipeline; the real
task swaps the fake values for your data, joined on the official AGS (`gem_code`) rather
than on names (which are not unique across Germany).

## Setup

```bash
pixi install
pixi run prepare-gemeinden    # only needed to (re)generate data/gemeinden.geo.json
```

`data/gemeinden.geo.json` is committed, so the notebook works without the download step.

## View the map

```bash
pixi run jupyter lab
```

Open `notebooks/germany_map.ipynb` and run all cells — the interactive Gemeinde map
renders inline.

## How it works

1. `scripts/prepare_gemeinden.py` downloads the OpenDataSoft `georef-germany-gemeinde`
   export (~58 MB, into the gitignored `bld/`) and simplifies it by snapping coordinates
   to a ~1 km grid, producing the slim committed `data/gemeinden.geo.json` (~9 MB).
1. `kdu.geodata.load_geojson` loads it and stamps each feature with a unique `fid` —
   region **names are not unique** in Germany, so the join must key on `fid` (or the
   AGS), never the name.
1. `kdu.maps` generates one random value per municipality and renders a Plotly
   `choropleth_map`.

## AGS lookup table

`data/gemeinde_lookup.arrow` maps each 12-digit AGS (`gem_code`) to its Gemeinde, Kreis,
and Bundesland names (~11k rows). Load it with `kdu.lookup.load_lookup`:

```python
from kdu.config import DATA
from kdu.lookup import load_lookup

lookup = load_lookup(
    DATA / "gemeinde_lookup.arrow"
)  # columns: ags, gemeinde, kreis, bundesland
```

Use it to attach names to your data, or to resolve ambiguous Gemeinde names to an AGS
via the Kreis/Bundesland.

## Swapping in real data

Replace `kdu.maps.build_fake_frame` with your data. The only requirement is one row per
geometry plus a join key that matches a GeoJSON property — the clean key is the AGS in
`gem_code`. Joining on names alone is lossy (duplicate "Neustadt"/"Münster", suffix and
umlaut variants).
