# Codebook — `kdu_gemeinden.csv`

One row per German Gemeinde (10,980 rows, one per AGS). Values are the *maximum amounts a
Jobcenter / Sozialamt will recognise* as angemessen for Unterkunft under § 22 SGB II / § 35 SGB XII,
as published by the responsible Kreis or kreisfreie Stadt.

`kdu_extract_per_kreis/` holds the same rows split into one file per Kreis (400 files, named by
`ags_kreis`). Concatenating them reproduces this table exactly.

## The one distinction that matters most

German KdU documents work with two different rent concepts. Mixing them up invalidates any
comparison, so they are kept in separate columns:

| Concept | Column family | Contents |
|---|---|---|
| **Nettokaltmiete** (Grundmiete) | `max_nettokaltmiete_*` | bare rent only |
| **Bruttokaltmiete** | `max_bruttokaltmiete_*` | bare rent **+ kalte Betriebskosten** |

**Neither includes heating.** "Brutto" here means *including cold operating costs*, not
including everything — Heizkosten are always granted separately and are not in this table.
Where a document stated only a Bruttowarmmiete (incl. heating), the cells were left empty and
`notes` says so; such figures were never written into a rent column.

Most Kreise regulate only one of the two, so the other family is empty for that Gemeinde. About
73% of Gemeinden have a Bruttokaltmiete cap, about 21% a Nettokaltmiete cap.

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
| `wogg_mietstufe` | numeric (1–7) | Mietstufe under § 12 Wohngeldgesetz. Complete for every Gemeinde: where a KdU document names one it is used, otherwise the statutory value from the Anlage zur Wohngeldverordnung (ab 1.1.2023). Empty only for the 172 gemeindefreie Gebiete no document covers — see below |
| `notes` | text | Caveats: the Vergleichsraum / Mietstufe the Gemeinde was assigned to, corrections, `"nicht im Dokument"`, `"kein KdU-Dokument vorhanden"` |
| `wogv_mietstufe` | numeric (1–7) | The statutory Mietstufe alone, straight from the Anlage zur Wohngeldverordnung. Unlike `wogg_mietstufe` it never defers to a KdU document, so the two differ for 45 Gemeinden. Empty for gemeindefreie Gebiete |
| `wogg_hoechstbetrag_eur_1p`, `_2p`, `_4p` | numeric | Höchstbetrag für Miete nach § 12 Abs. 1 WoGG in €/Monat for 1, 2 and 4 persons, looked up from `wogv_mietstufe` in Anlage 1 WoGG (in force 1.1.2025) |
| `kdu_vs_wogg_pct_1p`, `_2p`, `_4p` | numeric | The KdU Bruttokaltmiete cap relative to that Höchstbetrag, in percent. Positive means the Jobcenter recognises more than the Wohngeld ceiling. Empty where either input is empty |

Decimal separator is `.`; there are no thousands separators, currency symbols or unit suffixes.

## Empty cells are meaningful

This section applies to every column except `wogg_mietstufe`, which is completed from the
Wohngeldverordnung (see below). Elsewhere, an empty cell means **the document does not state
that value** — not zero, and not unknown-by-
oversight. Values were never derived: a total was never computed as €/m² × m², and an
""per further person"" figure was never computed as the gap between two printed household sizes.
Blank was preferred over a plausible-looking inferred number throughout.

- 1,480 Gemeinden have no row values at all: 35 of Germany's 400 Kreise have no document in the
  corpus (`notes` = "kein KdU-Dokument vorhanden").
- Some documents publish a table per Vergleichsraum but never say which Gemeinde belongs to which.
  Those Gemeinden were left empty rather than guessed — this affects e.g. Rendsburg-Eckernförde,
  Erzgebirgskreis, Cottbus.

## The Mietstufe column is completed from the statute

`wogg_mietstufe` is the one column not read solely off the KdU documents. It is filled as:

1. Where a KdU document states a Mietstufe, that value is kept, normalised to an integer
   1–7 (the documents use both Roman `I`–`V` and Arabic forms). 1,421 Gemeinden.
1. Otherwise the statutory value from the Anlage zu § 1 Absatz 3 Wohngeldverordnung,
   "Mietenstufen der Gemeinden nach Ländern ab 1. Januar 2023"
   (<https://www.gesetze-im-internet.de/wogv/anlage.html>). The annex lists Gemeinden of
   10,000+ inhabitants individually and assigns everyone else their Kreis's Mietstufe.
   9,387 Gemeinden.
1. Within step 2, the 28 Gemeinden named in § 12 Absatz 4a WoGG as lying on islands without
   a mainland connection take the annex's common island Mietstufe of V instead of their
   Kreis's. 26 of the 28 carry it here; Helgoland and Wangerooge keep the differing value
   their own KdU document states, under step 1.
1. Gemeindefreie Gebiete — unpopulated forest and lake tracts — receive no statutory value,
   because the annex's fallback sentence covers Gemeinden only. 172 cells stay empty; the
   33 gemeindefreie Gebiete whose KdU document does state a Mietstufe keep it.

Two caveats. The annex in force dates from 1 January 2023 while most KdU documents here are
2025, so the two describe different periods — the 1 January 2025 Fortschreibung raised the
Höchstbeträge, not the Mietstufen. And for 45 Gemeinden the KdU document contradicts the
statute; the document's value is the one kept in this table. Those 48 are listed in the
project's `bld/mietstufe_disagreements.csv` and are worth checking against the source PDFs —
Wangerooge states 1 against the statutory 5, Helgoland 4 against 5.

## Known limitations

1. **`*_addl` columns are the least reliable.** Independent re-extractions repeatedly derived these
   from differences between printed household sizes despite the rule against it. Treat
   `max_wohnflaeche_sqm_addl`, `max_nettokaltmiete_eur_addl` and `max_bruttokaltmiete_eur_addl`
   as lower-confidence than the rest.
2. **39 rows have caps that fall as household size rises.** Verified against the rendered source
   pages: the documents really print it that way. See `notes` on those rows.
3. **Sub-Gemeinde differentiation is lost.** A few documents set different caps per Ortsteil
   (e.g. Radolfzell am Bodensee has three schedules). One row per Gemeinde cannot express that;
   the main/Kernort values are recorded.
4. **Two open interpretive questions**, flagged rather than silently decided:
   * Dresden — city Merkblatt vs. the newer schlüssiges Konzept; the Merkblatt values are used.
   * Rems-Murr-Kreis, Ostalbkreis, Freudenstadt — the document says only "Kaltmiete" without
     stating whether Betriebskosten are included. Recorded as Nettokaltmiete, Bruttokaltmiete left
     empty.

## Sources

Derived from 444 KdU-Richtlinien and schlüssige Konzepte (`kdu_pdfs/`, catalogued in
`kdu_manifest.csv`). 362 distinct documents supplied values. Document-to-Kreis assignment is in
`kdu_region_to_kreis.csv`. Converted text and searchable OCR versions are in
`kdu_pdfs/converted_text/` and `kdu_pdfs/ocr_searchable/`.

## Comparing the KdU caps to Wohngeld

§ 12 Absatz 1 WoGG caps the rent a Wohngeld calculation may take into account, by
Mietstufe and household size (Anlage 1 WoGG, in force 1 January 2025, BGBl. 2024 I
Nr. 314). That cap is defined on the **Bruttokaltmiete** — § 9 WoGG counts Nettokaltmiete
plus kalte Betriebskosten and excludes heating and warm water — which is the same concept
as the `max_bruttokaltmiete_*` columns here. The two are therefore directly comparable in
euros, and `kdu_vs_wogg_pct_*` expresses the difference as a percentage of the Wohngeld
ceiling.

The `max_nettokaltmiete_*` columns are **not** comparable to these Höchstbeträge; they are
a different rent concept.

The Höchstbetrag is computed from `wogv_mietstufe`, the purely statutory value, because a
Wohngeldstelle applies the statutory Mietstufe regardless of what a KdU document states.

Across the 7,877 Gemeinden that have both figures, the KdU cap for a four-person household
sits a median of 10.0 % above the Wohngeld ceiling, and below it for 1,668 Gemeinden (15 %).
