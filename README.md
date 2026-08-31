# kdu

This repo provides a plotly choropleth of Germany at Gemeinde level. It depics the
maximum Kosten der Unterkunft at the Gemeindelevel and compares it with the maximum
Wohngeld rent.

Much of this is based on Harald Thomé's
[KdU-Richtlinien und Mietobergrenzen](https://harald-thome.de/informationen/bundesweite-dienstanweisungen-kdu.html)
collection of Jobcenter and Sozialamt directives on angemessene Unterkunftskosten.

Under SGB II and SGB XII, roughly 400 Kreise and kreisfreie Städte each publish their
own Angemessenheitsgrenze for Unterkunftskosten. This repository collects the local
rules, measures the errors researchers make when using rule of thumb fallbacks, and
reports how those errors change the gross income at which a household leaves the
transfer system.

The benchmark throughout is the **Wohngeld-Höchstbetrag times 1.10** — the standard the
Bundessozialgericht prescribes where a Kreis has published no schlüssiges Konzept, and
therefore the legally correct comparator rather than an arbitrary one.

## Installation and use

```bash
pixi install
pixi run pytask
pixi run pytest
pixi run ty
pixi run prek run --all-files
```

## The map

`bld/map/germany_map.html` is an interactive Gemeinde-level choropleth with seven
measures and a household-size control: the Mietenstufe, the local cap in euro and per
square metre, the statutory fallback, the ratio between them, the admissible Wohnfläche,
and the share of the local rented stock priced above the cap.

## Data

- `data/kdu_gemeinden.csv` — the collected caps, keyed by eight-digit AGS. Empty cells
  mean the cited document does not state the value. `data/kdu_codebook.md` defines every
  column.
- `data/gemeinden.geo.json` — boundaries simplified to roughly a 1 km grid.
- `data/wogg_parameters.csv` — Anlage 1 Höchstbeträge and Mietenstufen.
- `data/ba_wohnkosten/`, `data/zensus/` — the two external sources.

## Sources

- **[KdU-Richtlinien und Mietobergrenzen](https://harald-thome.de/informationen/bundesweite-dienstanweisungen-kdu.html)**
  — Harald Thomé's nationwide collection of Jobcenter and Sozialamt directives on
  angemessene Unterkunftskosten supplies the KdU documents.
- **[Mietenstufen der Gemeinden](https://www.gesetze-im-internet.de/wogv/anlage.html)**
  — the annex to § 1 Absatz 3 Wohngeldverordnung is the statutory source for the
  Mietenstufen.
- **[Inseln ohne Festlandanschluss](https://www.gesetze-im-internet.de/wogg/__12.html)**
  — § 12 Absatz 4a WoGG defines the Mietenstufe rule for the listed island Gemeinden.
- **[Wohngeld-Höchstbeträge](https://www.gesetze-im-internet.de/wogg/anlage_1.html)** —
  Anlage 1 zu § 12 Absatz 1 WoGG defines the monthly rent ceilings by household size and
  Mietenstufe.
- **[Wohnkosten in der Grundsicherung](https://statistik.arbeitsagentur.de)** — the
  Wohnkostenstatistik of the Bundesagentur für Arbeit reports actual and recognised
  housing costs per Jobcenter.
- **[Zensus 2022](https://ergebnisse.zensus2022.de)** — Nettokaltmieten and the rent
  distribution of the rented stock at Gemeinde level.
- **[Gemeindegrenzen](https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/georef-germany-gemeinde/exports/geojson?limit=-1)**
  — the OpenDataSoft `georef-germany-gemeinde` export supplies boundaries and names.

## Caveats

The caps are the maximum regularly recognisable Unterkunftsbedarf, **not** payments.
Actual costs are recognised where they are angemessen, so entitlement depends further on
actual rent, income, household composition, and Karenz- and Härtefallregelungen.

## The presentation

`documents/presentation.md` is the [Slidev](https://sli.dev) deck for the GETTSIM
workshop, split into one file per section under `documents/pages/`.

```bash
pixi install
npm install
pixi run pytask        # the deck embeds figures from bld/, so build them first
pixi run view-pres
```

The deck references figures in `bld/` by relative path, and `bld/` is not in version
control. `pixi run view-pres` therefore fails until `pixi run pytask` has run.

`pixi run export-pres` writes `documents/presentation.pdf`. It drives a headless
Chromium, which npm does not install by default; run
`npm install-scripts approve playwright-chromium` once beforehand.

The map segment is presented live from `bld/map/germany_map.html` in a separate browser
window. Slides 22 to 24, in `documents/pages/07_map_appendix.md`, are static renderings
of the same three views, for a machine where the live map does not come up.
