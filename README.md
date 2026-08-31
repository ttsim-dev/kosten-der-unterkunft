# kdu

How far does the maximum rent a local Jobcenter will recognise depart from the figure a
tax-transfer model substitutes when it has no local number — and what does that change?

Under SGB II and SGB XII, roughly 400 Kreise and kreisfreie Städte each publish their
own Angemessenheitsgrenze for Unterkunftskosten. Tax-transfer models rarely have those
figures and substitute the Wohngeld-Höchstbetrag instead. This repository collects the
local rules, measures the substitution error, and traces it through to eligibility.

The benchmark throughout is the **Wohngeld-Höchstbetrag times 1.10** — the standard the
Bundessozialgericht prescribes where a Kreis has published no schlüssiges Konzept, and
therefore the legally correct comparator rather than an arbitrary one.

## What it finds

- The fallback is **right on average and wrong locally**: at household size one the
  median Gemeinde's cap sits 0.2% above it, while the tenth and ninetieth percentiles
  sit 16.7% below and 23.4% above.
- The statutory **Mietenstufe cannot repair this**. It accounts for about 41% of the
  variation in local caps — less than knowing the Bundesland alone accounts for.
- The variation it misses is **not administrative noise**. Within a Mietenstufe, where
  the fallback is constant by construction, local caps still track actual Zensus market
  rents.
- A cap error is **amplified** in what it changes: roughly 1.9 euro of gross income at
  the point a household leaves the transfer system per euro of error in the cap.

## Installation and use

```bash
pixi install
pixi run pytask                    # build everything into bld/
pixi run pytest
pixi run ty
pixi run prek run --all-files
```

The build never touches the network. Source data are committed under `data/`;
`scripts/fetch_*.py` refresh them by hand when a new vintage appears.

## The map

`bld/map/germany_map.html` is an interactive Gemeinde-level choropleth with seven
measures and a household-size control: the Mietenstufe, the local cap in euro and per
square metre, the statutory fallback, the ratio between them, the admissible Wohnfläche,
and the share of the local rented stock priced above the cap. Each measure is also
exported as its own file. Areas whose directive admits a Härtefallregelung are hatched.
The map is labelled in German.

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

Where a cap equals the Wohngeld-Höchstbetrag times 1.10 exactly, we suspect the Kreis
applies the fallback unchanged, which would make the measured departure an arithmetic
identity rather than a finding. Those documents have not been located, so this remains a
suspicion and every result is reported both including and excluding those Kreise.
