# P1.1 — requests to files outside the module's scope

P1.1 (`src/kdu/analysis/border_jumps.py`, `task_border_jumps.py`,
`src/kdu/final/task_figures_border_jumps.py`) is complete and builds. Three changes it
could not make itself, because they belong to files it may not edit.

## 1. No new package dependency is needed

`shapely`, `geopandas`, `pyproj` and `libpysal` are all absent from the environment.
None was added. The module implements what §13 needs directly on NumPy:

- the ellipsoidal Lambert azimuthal equal-area projection of ETRS89/LAEA Europe
  (EPSG:3035) in `project_laea`, verified against the projection's own false origin and
  against the spherical area of a lon/lat quadrangle;
- polygon area and centroid by the shoelace formula in that projection;
- adjacency by exact shared-edge matching on the source topology.

The last of these is only sound because the boundary source is a valid
planar partition: no edge in `bld/gemeinden_raw.geojson` is shared by more than two
polygons, and 10,963 of its 10,981 polygons have at least one neighbour. Had it not
been a valid partition, a geometry library would have been required. If a future module needs
overlay, buffering or a distance-to-boundary measure, `shapely` becomes unavoidable —
it is not needed for §13.

## 2. `src/kdu/config.py` — two catalog entries

The task falls back to plain `BLD / ...` paths, which works, but the D5 rule is that
every artefact is registered in `DATA_CATALOG`. Requested additions:

```python
DATA_CATALOG.add("gemeinden_raw_geojson", BLD / "gemeinden_raw.geojson")
DATA_CATALOG.add("neighbour_pairs", BLD / "neighbour_pairs.parquet")
DATA_CATALOG.add("border_jumps", BLD / "border_jumps.parquet")
DATA_CATALOG.add("neighbour_jump_flags", BLD / "neighbour_jump_flags.parquet")
```

`bld/gemeinden_raw.geojson` is the unsimplified OpenDataSoft export that
`pixi run prepare-gemeinden` downloads. It is gitignored, so a fresh clone must run that
command once before `task_border_jumps` can build. The task raises a `FileNotFoundError`
naming the command when the file is absent.

## 3. `src/kdu/data_management/quality.py` — replace the surrogate neighbour flag

A8's carried defect. `_neighbour_jumps` currently ranks Kreise within a Bundesland by
their median h=1 cap and flags consecutive steps above the 95th percentile, because true
adjacency did not exist. It does now, in `bld/neighbour_jump_flags.parquet`.

What the owner of `quality.py` and `task_quality.py` must change:

1. **`task_quality.py`** — add a dependency
   `neighbour_jump_flags_path: Path = BLD / "neighbour_jump_flags.parquet"` (or the
   catalog entry once it exists), read it with `pd.read_parquet`, and pass the frame into
   `_collect_worklist_strata`. There is no cycle: `task_border_jumps` reads
   `analysis_sample_main` and `proxy_error_gemeinde_household`, neither of which depends
   on `task_quality`.

2. **`quality.py`** — replace the body of `_neighbour_jumps` with a selection on the
   flag, and delete `NEIGHBOUR_JUMP_PERCENTILE` and `NEIGHBOUR_JUMP_THRESHOLD`, which the
   surrogate needed and the real flag does not:

   ```python
   def _neighbour_jumps(long: pd.DataFrame, flags: pd.DataFrame) -> pd.DataFrame:
       """Flag Gemeinden whose cap steps unusually far across a real shared border."""
       flagged = flags.loc[flags["large_neighbour_jump"], ["ags", "household_size"]]
       selected = long.merge(flagged, on=["ags", "household_size"], how="inner")
       return _label(selected, "large_neighbour_jump")
   ```

   The stratum label stays `large_neighbour_jump`, so `validation_worklist.csv` keeps its
   schema.

3. **`tests/test_quality.py`** — the surrogate's test fixture builds a within-Bundesland
   cap ladder. Replace it with a two-row flag frame; the function no longer computes a
   threshold, so the test becomes a selection test.

### What the flag now means

`bld/neighbour_jump_flags.parquet` is keyed `ags × household_size` over the full
`analysis_sample_main` (37,768 rows, h = 1…4) and carries:

| column | meaning |
|---|---|
| `max_cross_border_jump_eur` | largest `\|K_i − K_j\|` to any directly adjacent Gemeinde in a different policy region, across a shared border of at least 250 m |
| `jump_threshold_eur` | the 95th percentile of all such cross-border steps at that household size |
| `large_neighbour_jump` | `max_cross_border_jump_eur > jump_threshold_eur` |
| `has_cross_border_neighbour` | `False` for a Gemeinde with no eligible cross-border neighbour — an island, or one whose whole Kreis boundary is a suspected geometry artefact. Those rows are `large_neighbour_jump = False`, and the distinction matters: no evidence is not evidence of no jump |
| `threshold_quantile` | 0.95, recorded so the cut-off is visible in the artefact |

Roughly 6.9 % of `ags × household_size` rows are flagged. The stratum it feeds is a
worklist of rows worth looking at, not a list of rows that are wrong: a large step across
a Kreis boundary is exactly what §13 documents as normal.

### Also worth re-deriving

A8 asks for the affected worklist stratum to be re-derived once P1.1 lands. Note that the
surrogate and the real flag select *different kinds* of row: the surrogate picked one row
per flagged policy region, the real flag picks Gemeinden. The worklist will grow, and its
`n` should be reported as a change in the Methodenanhang rather than silently absorbed.
