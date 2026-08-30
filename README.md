# kdu

This repo provides a plotly choropleth of Germany at Gemeinde level. It depics the
maximum Kosten der Unterkunft at the Gemeindelevel and compares it with the maximum
Wohngeld rent.

Data is stored in `data/kdu_gemeinden.csv` and indexed at the Amtlicher
Gemeindeschlüssel (AGS) level.

Much of this is based on Harald Thomé's
[KdU-Richtlinien und Mietobergrenzen](https://harald-thome.de/informationen/bundesweite-dienstanweisungen-kdu.html)
collection of Jobcenter and Sozialamt directives on angemessene Unterkunftskosten.

## Installation and use

```bash
pixi install
pixi run pytask             # build bld/germany_map.html
pixi run pytest
pixi run ty
pixi run prek run --all-files
```

## Data and map

- `data/kdu_gemeinden.csv` is the single map table, with one row per geometry. It
  contains the KdU measures, Mietstufen, Wohngeld Höchstbeträge, comparisons, source
  documents, validity dates, and notes. Empty measure cells mean that the cited KdU
  document does not state the value.
- `data/gemeinden.geo.json` contains boundaries simplified to a roughly 1 km grid,
  together with each geometry's 12-digit `gem_code` and Gemeinde name.
- `data/gemeinde_lookup.arrow` maps the 12-digit code to Gemeinde, Gemeinde type, Kreis,
  and Bundesland.
- `data/kdu_codebook.md` defines all CSV columns, rent concepts, empty-cell semantics,
  and known limitations.

## Sources

- **[KdU-Richtlinien und Mietobergrenzen](https://harald-thome.de/informationen/bundesweite-dienstanweisungen-kdu.html)**
  — Harald Thomé's nationwide collection of Jobcenter and Sozialamt directives on
  angemessene Unterkunftskosten supplies the KdU documents cited by the CSV.
- **[Mietenstufen der Gemeinden](https://www.gesetze-im-internet.de/wogv/anlage.html)**
  — The annex to § 1 Absatz 3 Wohngeldverordnung, „Mietstufen der Gemeinden nach Ländern
  ab 1. Januar 2023“ (BGBl. I 2022, 2166–2210), is the statutory source for the
  Mietstufen columns.
- **[Inseln ohne Festlandanschluss](https://www.gesetze-im-internet.de/wogg/__12.html)**
  — § 12 Absatz 4a WoGG defines the Mietstufe rule for the listed island Gemeinden.
- **[Wohngeld-Höchstbeträge](https://www.gesetze-im-internet.de/wogg/anlage_1.html)** —
  Anlage 1 zu § 12 Absatz 1 WoGG defines the monthly rent ceilings by household size and
  Mietstufe.
- **[Gemeindegrenzen](https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/georef-germany-gemeinde/exports/geojson?limit=-1)**
  — The OpenDataSoft `georef-germany-gemeinde` export supplies the boundaries, AGS, and
  Gemeinde, Kreis, and Bundesland names.
