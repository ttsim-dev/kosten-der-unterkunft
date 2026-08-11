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

Most Kreise regulate only one of the two, so the other family is empty for that Gemeinde. 82 %
of Gemeinden have a Bruttokaltmiete cap and 21 % a Nettokaltmiete cap; 1,180 have both, because
their document prints the Nettokaltmiete, the kalte Betriebskosten and the Bruttokaltmiete side by
side. Where both are present the Bruttokaltmiete exceeds the Nettokaltmiete in every row, and no
row carries the same figure in both families.

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
| `max_bruttokaltmiete_abgeleitet_eur_1p` … `_addl` | numeric | Nettokaltmiete **plus** the printed cold-cost cap. Derived, not printed — see below |
| `kdu_vs_wogg_basis` | text | Whether `kdu_vs_wogg_pct_*` rests on a `gedruckt`en or an `abgeleitet`en Bruttokaltmiete |
| `wogg_mietstufe` | numeric (1–7) | Mietstufe under § 12 Wohngeldgesetz. Complete for every Gemeinde: where a KdU document names one it is used, otherwise the statutory value from the Anlage zur Wohngeldverordnung (ab 1.1.2023). Empty only for the 172 gemeindefreie Gebiete no document covers — see below |
| `notes` | text | Caveats: the Vergleichsraum / Mietstufe the Gemeinde was assigned to, corrections, `"nicht im Dokument"`, `"kein KdU-Dokument vorhanden"` |
| `wogv_mietstufe` | numeric (1–7) | The statutory Mietstufe alone, straight from the Anlage zur Wohngeldverordnung. Unlike `wogg_mietstufe` it never defers to a KdU document, so the two differ for 54 Gemeinden. Empty for gemeindefreie Gebiete |
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

- 933 Gemeinden have no rent cap. 11 of Germany's 400 Kreise have no document at all, and 20 have
  no rent value for any Gemeinde. The `notes` on those rows say why: no public document could be
  found, the responsible authority publishes only a Bruttowarmmiete, or the document prescribes an
  individual assessment without printing amounts.
- Gemeindefreie Gebiete — unpopulated forest and lake tracts — are generally outside the documents'
  scope and stay empty even where the surrounding Kreis is fully covered.
- Documents that publish a table per Vergleichsraum without naming member Gemeinden used to force
  whole Kreise to stay empty. The August 2026 audit resolved these from the authorities' own
  Vergleichsraum annexes, including Rendsburg-Eckernförde, Erzgebirgskreis and Cottbus.

## The Mietstufe column is completed from the statute

`wogg_mietstufe` is the one column not read solely off the KdU documents. It is filled as:

1. Where a KdU document states a Mietstufe, that value is kept, normalised to an integer
   1–7 (the documents use both Roman `I`–`V` and Arabic forms).
1. Otherwise the statutory value from the Anlage zu § 1 Absatz 3 Wohngeldverordnung,
   "Mietenstufen der Gemeinden nach Ländern ab 1. Januar 2023"
   (<https://www.gesetze-im-internet.de/wogv/anlage.html>). The annex lists Gemeinden of
   10,000+ inhabitants individually and assigns everyone else their Kreis's Mietstufe.
1. Within step 2, the 28 Gemeinden named in § 12 Absatz 4a WoGG as lying on islands without
   a mainland connection take the annex's common island Mietstufe of V instead of their
   Kreis's. 27 of the 28 carry it here; only Helgoland keeps the differing value its own KdU
   document states, under step 1.
1. Gemeindefreie Gebiete — unpopulated forest and lake tracts — receive no statutory value,
   because the annex's fallback sentence covers Gemeinden only. 160 cells stay empty; the
   45 gemeindefreie Gebiete whose KdU document does state a Mietstufe keep it.

Two caveats. The annex in force dates from 1 January 2023 while the KdU documents here are
mostly 2025 and 2026, so the two describe different periods — the 1 January 2025 Fortschreibung raised the
Höchstbeträge, not the Mietstufen. And for 54 Gemeinden the KdU document contradicts the
statute; the document's value is the one kept in this table. They are worth checking against the
source PDFs — Helgoland states 4 against the statutory 5. Select them with
`df.query("wogg_mietstufe.notna() and wogv_mietstufe.notna() and wogg_mietstufe != wogv_mietstufe")`.

## Known limitations

1. **`*_addl` columns are the least reliable.** Independent re-extractions repeatedly derived these
   from differences between printed household sizes despite the rule against it. Treat
   `max_wohnflaeche_sqm_addl`, `max_nettokaltmiete_eur_addl` and `max_bruttokaltmiete_eur_addl`
   as lower-confidence than the rest.
2. **68 rows have caps that fall as household size rises.** Verified against the rendered source
   pages: the documents really print it that way. For the Wetteraukreis and Südliche Weinstraße
   schedules the dip appears independently in the separately printed Nettokaltmiete *and*
   Betriebskosten components, which rules out a shifted column. See `notes` on those rows.
3. **Sub-Gemeinde differentiation is lost.** A few documents set different caps per Ortsteil
   (e.g. Radolfzell am Bodensee has three schedules). One row per Gemeinde cannot express that;
   the main/Kernort values are recorded.
4. **One open interpretive question.** Freudenstadt and Main-Taunus-Kreis print only "Kaltmiete"
   without stating whether Betriebskosten are included. Both are recorded as Nettokaltmiete with
   Bruttokaltmiete left empty. The same ambiguity for Rems-Murr-Kreis and the Ostalbkreis was
   settled against the authorities' own definitions — both publish "Kaltmiete inkl. Nebenkosten"
   and are now recorded as Bruttokaltmiete.

## Sources

Derived from the KdU-Richtlinien and schlüssige Konzepte in `kdu_pdfs/` (catalogued in
`kdu_manifest.csv`), revised by a full re-audit of all 400 Kreise in August 2026 that checked every
Kreis against the responsible authority's current publication. 389 distinct documents supply
values. `kdu_pdfs/` separates the two provenances: `thome/` holds the 444 documents from the
harald-thome.de collection catalogued in the manifest, and `own_research/` the 219 retrieved
directly from the authorities during the audit, used wherever they were newer. A
`source_document` naming a file in neither folder is a document that was read at the authority's
website but could not be saved; the field still names it. Document-to-Kreis assignment is in
`kdu_region_to_kreis.csv`. Converted text and searchable OCR versions are in
`kdu_pdfs/converted_text/` and `kdu_pdfs/ocr_searchable/`.

## The one derived quantity in the table

Every other column holds what a document prints. `max_bruttokaltmiete_abgeleitet_*` is the
exception: it adds `max_nettokaltmiete_*` and `max_kalte_bk_*`, because Bruttokaltmiete is by
definition bare rent plus kalte Betriebskosten. It is filled only where a Kreis caps the two
separately and prints both, and never where a Bruttokaltmiete is printed outright — so
`max_bruttokaltmiete_*` keeps meaning "printed" and the two never blur.

478 Gemeinden across the Kreise that regulate the Nettokaltmiete gain a figure this way; the
cold-cost caps run from 11 % to 35 % of the corresponding Nettokaltmiete. A further 139
Gemeinden cap cold costs per m² only, and are left empty rather than multiplied by the
Wohnfläche.

Read the derived figure with one caveat. Two separate caps is not the same rule as one
combined ceiling: where rent and cold costs are capped individually, a tenant may not exceed
the rent cap even with unusually cheap operating costs. Some Kreise say explicitly that the
angemessene Bruttokaltmiete is the sum — Recklinghausen is one — and there the derivation is
the operative limit. Elsewhere it is the right basis for comparison but not automatically the
rule the Jobcenter applies. The per-Kreis `notes` record which case applies.

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

Across the 9,323 Gemeinden that have both figures, the KdU cap for a four-person household
sits a median of 10.1 % above the Wohngeld ceiling, and below it for 1,455 Gemeinden (13 %).
`kdu_vs_wogg_basis` says whether a row's comparison rests on a printed Bruttokaltmiete
(8,964 Gemeinden) or a derived one (478); filter on it to restrict the comparison to printed
figures alone.
