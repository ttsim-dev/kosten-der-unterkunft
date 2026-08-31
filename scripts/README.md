# scripts/

Refresh the data under `data/` by running the four scripts in order:

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

The published sources are far too large to store here:

| source                                 | download                                                                                    |
| -------------------------------------- | ------------------------------------------------------------------------------------------- |
| BA "Wohn- und Kostensituation"         | roughly 1.5 GB across a few thousand requests — one workbook per region and reference month |
| OpenDataSoft `georef-germany-gemeinde` | ~58 MB of full-resolution boundaries                                                        |
| Zensus 2022 Regionaltabelle            | a 21 MB workbook                                                                            |
| Destatis GV-ISys Jahresausgabe         | two annual editions                                                                         |

What is committed is the extract, not the original: 3.2 MB of BA CSVs instead of 1.5 GB
of Excel, an 8.2 MB boundary file simplified to a ~1 km grid instead of 58 MB of raw
geometry. Downloads land in `bld/` (gitignored).

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
