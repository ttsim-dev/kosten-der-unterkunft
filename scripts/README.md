# scripts/

Refresh scripts for the committed inputs under `data/`. They are the only code in the
repository that touches the network, and they are run by hand — never from the pytask
graph.

```bash
pixi run python scripts/prepare_gemeinden.py
pixi run python scripts/fetch_gemeinde_population.py
pixi run python scripts/fetch_zensus_mieten.py
pixi run python scripts/fetch_ba_wohnkosten.py
```

Each script downloads a published source, keeps the few columns the project reads, and
writes a small extract into `data/`, which is committed. `pixi run pytask` then builds
everything from those extracts alone, offline and reproducibly.

## Why the originals are not under version control

The published sources are far too large to store here, and Git would keep every vintage
of them forever:

| source                                 | download                                                                                    |
| -------------------------------------- | ------------------------------------------------------------------------------------------- |
| BA "Wohn- und Kostensituation"         | roughly 1.5 GB across a few thousand requests — one workbook per region and reference month |
| OpenDataSoft `georef-germany-gemeinde` | ~58 MB of full-resolution boundaries                                                        |
| Zensus 2022 Regionaltabelle            | a 21 MB workbook                                                                            |
| Destatis GV-ISys Jahresausgabe         | two annual editions                                                                         |

What is committed is the extract, not the original: 3.2 MB of BA CSVs instead of 1.5 GB
of Excel, an 8.2 MB boundary file simplified to a ~1 km grid instead of 58 MB of raw
geometry. Downloads land in `bld/` (gitignored) and are reused on a re-run, so a second
invocation costs no bandwidth. Deleting `bld/` costs only the time to fetch again.

Because the originals are gone, provenance is carried by the manifests
`data/ba_wohnkosten/ba_download_manifest.csv` and
`data/zensus/zensus_download_manifest.csv`, which record the source URL, the retrieval
date, the byte size and the SHA-256 of every file that went into an extract. Any
original can be fetched again and checked against what was parsed here.

The one exception is `data/ba_wohnkosten/kdu-d-0-<month>-xlsx.xlsx`, the national BA
workbook, kept verbatim because its `Hinweis_SGB-II_Wohnkosten` sheet carries the BA's
own methodological notes and nothing else reproduces them.

## What each script writes

| script                         | writes                                                                                                                |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| `prepare_gemeinden.py`         | `data/gemeinden.geo.json`, `data/gemeinde_lookup.arrow`                                                               |
| `fetch_gemeinde_population.py` | `data/gemeinde_population.arrow`                                                                                      |
| `fetch_zensus_mieten.py`       | `data/zensus/zensus2022_nettokaltmiete_gemeinden.csv` and its manifest                                                |
| `fetch_ba_wohnkosten.py`       | `data/ba_wohnkosten/` — the reference-month extract, the twelve-month average, the national workbook and the manifest |

`prepare_gemeinden.py` must run before `fetch_gemeinde_population.py`: the population
table is reconciled against the AGS actually drawn in `gemeinden.geo.json`.

The two underscore-prefixed modules hold the pure logic the fetch scripts call, so it
can be tested without a network:

- `_gemeindeverzeichnis.py` — parse the GV-ISys workbook, reconcile two Gebietsstände
  against the boundary file, derive the Gemeindegrößenklassen.
- `_wohnkosten_workbooks.py` — parse the BA workbooks and derive the Bruttokaltmiete
  from the cost components the BA reports separately.

## Refreshing to a new vintage

The vintage each script targets is a module-level constant, not a command-line argument,
so that the committed extract and the code that produced it move together in one commit:

- `fetch_ba_wohnkosten.py` — `REFERENCE_MONTH` and `ANNUAL_MEAN_MONTHS`.
- `fetch_gemeinde_population.py` — `BASE_REFERENCE_DATE`, `BACKFILL_REFERENCE_DATE` and
  `MERGER_REVERSALS`. No single published Gebietsstand reproduces the AGS of the
  boundary export exactly, so a new edition generally needs the reversals revisited; the
  build raises unless the result covers the boundary AGS exactly.

After a refresh, commit the changed files in `data/` together with the constants that
produced them, and check that the Rechtsstand and Gebietsstand in `src/kdu/config.py`
still describe what was fetched.
