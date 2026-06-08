@.ai-instructions/profiles/tier-b-research.md

# AGENTS.md

This file provides guidance to AI coding tools (Claude Code, Gemini CLI, Codex, Copilot,
Cursor) when working with code in this repository.

## Overview

kdu is a prototype that draws choropleth maps of Germany at **Gemeinde** level (~11k
municipalities) using Plotly. It currently fills the map with placeholder data; the
intended next step is to join real data on the official AGS (`gem_code`) rather than on
municipality names, which are not unique.

## Build & Test

```bash
pixi install                       # create the environment
pixi run prepare-gemeinden         # download + simplify boundaries → data/gemeinden.geo.json
pixi run tests                     # pytest
pixi run ty                        # type checking
pixi run prek run --all-files      # pre-commit hooks
```

Open `notebooks/germany_map.ipynb` (via `pixi run jupyter lab`) to view the figure.

## Architecture

- `src/kdu/geodata.py` — load boundary GeoJSON, stamp a unique `fid` per feature, and
  simplify geometry by snapping coordinates to a coarse grid (pure functions).
- `src/kdu/maps.py` — build placeholder data and the Plotly `choropleth_map` figure.
- `src/kdu/config.py` — project path constants (`SRC`, `ROOT`, `BLD`, `DATA`).
- `scripts/prepare_gemeinden.py` — one-off: fetch the ~58 MB OpenDataSoft export into
  `bld/` and write the slim, committed `data/gemeinden.geo.json`.
- `notebooks/germany_map.ipynb` — loads the slim boundaries and renders the map.

The join key is `fid` (a synthetic per-feature index), never the name. Region names
repeat across Germany; the clean real-data key is the AGS carried in `gem_code`.
