@.ai-instructions/profiles/tier-b-research.md

# AGENTS.md

This file provides guidance to AI coding tools (Claude Code, Gemini CLI, Codex, Copilot,
Cursor) when working with this repository.

## Overview

`kdu` builds an interactive Plotly choropleth of Germany at Gemeinde level. It joins
10,980 geometries to the 35-column `data/kdu_gemeinden.csv` table by AGS and provides a
dropdown over 15 KdU, Mietstufe, and Wohngeld measures. The pytask graph contains one
task, which writes `bld/germany_map.html`.

## Build and test

```bash
pixi install                       # create the environment
pixi run pytask                    # build bld/germany_map.html
pixi run pytest                    # run tests
pixi run ty                        # type checking
pixi run prek run --all-files      # pre-commit hooks
```

Run `pixi run prepare-gemeinden` only to regenerate the committed boundaries and AGS
lookup from OpenDataSoft.

## Architecture

- `data/kdu_gemeinden.csv` — the single map table, keyed by eight-digit Gemeinde AGS.
  See `data/kdu_codebook.md` for all 35 column definitions.
- `data/gemeinden.geo.json` — simplified Gemeinde-level boundaries.
- `data/gemeinde_lookup.arrow` — 12-digit AGS to Gemeinde, Gemeinde type, Kreis, and
  Bundesland metadata.
- `src/kdu/config.py` — project paths and the four-entry pytask data catalog.
- `src/kdu/geodata.py` — load boundary GeoJSON, stamp a unique `fid` per feature, and
  simplify geometry by snapping coordinates to a coarse grid.
- `src/kdu/lookup.py` — build and load the AGS lookup table.
- `src/kdu/measures.py` — define the 15 selectable measures and their display metadata
  and colour ranges.
- `src/kdu/maps.py` — join the CSV and lookup to the boundaries and build the Plotly
  choropleth with its measure dropdown.
- `src/kdu/final/task_map.py` — the single pytask task; read the three map inputs and
  write `bld/germany_map.html`.
- `scripts/prepare_gemeinden.py` — fetch the OpenDataSoft export and write the committed
  GeoJSON and lookup files.

The map join key is the official AGS derived from `gem_code`; region names are never
used as keys because they repeat across Germany. The synthetic `fid` connects the joined
frame to Plotly's GeoJSON features.
