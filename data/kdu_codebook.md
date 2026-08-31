# Codebook — `kdu_gemeinden.csv`

We collected data on the maximum Kosten der Unterkunft (SGB II / SGB XII) by Gemeinde.
The data is largely based on Harald Thomé's
[collection](https://harald-thome.de/informationen/bundesweite-dienstanweisungen-kdu.html).
We updated it to complete the coverage of (almost) all German Gemeinden.

One row per German Gemeinde (10,980 rows, one per AGS). Values are the *maximum amounts
a Jobcenter / Sozialamt will recognise* as angemessen for Unterkunft under § 22 SGB II /
§ 35 SGB XII, as published by the responsible Kreis or kreisfreie Stadt.

## The one distinction that matters most

German KdU documents work with two different rent concepts. Mixing them up invalidates
any comparison, so they are kept in separate columns:

| Concept | Column family | Contents |
|---|---|---|
| **Nettokaltmiete** (Grundmiete) | `max_nettokaltmiete_*` | bare rent only |
| **Bruttokaltmiete** | `max_bruttokaltmiete_*` | bare rent **+ kalte Betriebskosten** |

**Neither includes heating.** "Brutto" here means *including cold operating costs*,
Heizkosten are always granted separately and are not in this table.

## Columns

| Column | Type | Meaning |
|---|---|---|
| `gemeinde_name` | text | Official Gemeinde name, spelled as in the geodata |
| `ags_gemeinde` | text (8) | Amtlicher Gemeindeschlüssel. **Keep as text** — leading zeros are significant |
| `ags_kreis` | text (5) | First 5 digits of the AGS = Land + Regierungsbezirk + Kreis |
| `kdu_region` | text | Region label of the source document, as catalogued |
| `source_document` | text | Filename of the PDF the values came from. `" + "` separates two documents where a newer one was supplemented from an older |
| `valid_from` | date | ISO date the document takes effect. Empty where it states no exact date |
| `max_wohnflaeche_sqm_1p` … `_5p` | numeric | Maximum angemessene Wohnfläche in m², households of 1–5 persons |
| `max_wohnflaeche_sqm_addl` | numeric | Additional m² granted per further person beyond 5 |
| `max_nettokaltmiete_eur_1p` … `_5p` | numeric | Maximum monthly Nettokaltmiete in €, households of 1–5 persons |
| `max_nettokaltmiete_eur_addl` | numeric | Increase of the Nettokaltmiete cap per further person beyond 5 |
| `max_nettokaltmiete_eur_sqm` | numeric | Maximum Nettokaltmiete per m² in € |
| `max_bruttokaltmiete_eur_1p` … `_5p` | numeric | Maximum monthly Bruttokaltmiete in €, households of 1–5 persons |
| `max_bruttokaltmiete_eur_addl` | numeric | Increase of the Bruttokaltmiete cap per further person beyond 5 |
| `max_bruttokaltmiete_eur_sqm` | numeric | Maximum Bruttokaltmiete per m² in € |
| `max_kalte_bk_eur_1p` … `_5p` | numeric | Cap the document sets on the **kalten Betriebskosten** alone, €/month, households of 1–5 |
| `max_kalte_bk_eur_addl` | numeric | Increase of that cold-cost cap per further person |
| `max_kalte_bk_eur_sqm` | numeric | Cold-cost cap expressed per m², where the document caps it that way instead |
| `wogg_mietstufe` | numeric (1–7) | Mietstufe under § 12 Wohngeldgesetz |
| `notes` | text | Caveats and comments |
| `wogg_hoechstbetrag_eur_1p`, `_2p`, `_4p` | numeric | Höchstbetrag für Miete nach § 12 Abs. 1 WoGG in €/Monat for 1, 2 and 4 persons, looked up from `wogg_mietstufe` in Anlage 1 WoGG. **Base amount only** — the Klimakomponente of § 12 Abs. 7 and the Heizkostenentlastung of § 12 Abs. 6 are not included. 3p and 5p are absent here. This is not the project's benchmark: `wohngeld_fallback_cap` in `bld/data/wohngeld_fallback.parquet` adds the Klimakomponente and then applies the 10 % Sicherheitszuschlag |
| `kdu_vs_wogg_pct_1p`, `_2p`, `_4p` | numeric | The KdU Bruttokaltmiete cap relative to that Höchstbetrag, in percent. |
| `haertefall_regelung` | 1 or empty | `1` where the source document itself prints a quantified Härtefall uplift as an alternative to the Richtwert. |
