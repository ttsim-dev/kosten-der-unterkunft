# External validation data — what was obtained, what is blocked

Status of the two external sources P1.2 (§14) and P1.3 (§15) validate against.
Retrieval date for everything below: **2026-08-27**.

## Obtained

### BA "Wohn- und Kostensituation" (§14)

| | |
|---|---|
| Publisher | Statistik der Bundesagentur für Arbeit |
| Product | Wohn- und Kostensituation — Deutschland, West/Ost, Länder, Kreise und Jobcenter (Monatszahlen), topic `kdu-kdu` |
| Listing | `https://statistik.arbeitsagentur.de/SiteGlobals/Forms/Suche/Einzelheftsuche_Formular.html?topic_f=kdu-kdu` |
| File URL pattern | `https://statistik.arbeitsagentur.de/Statistikdaten/Detail/{YYYYMM}/iiia7/kdu-kdu/kdu-{code}-0-{YYYYMM}-xlsx.xlsx?__blob=publicationFile&v=1` |
| Reference month | **2026-04**, the latest published at or before the D2 Stichtag 2026-08-31 |
| Annual-average window | 2025-05 … 2026-04 |
| Regions | 401 Kreise and 404 Jobcenter per month |

Sheets read, both restricted to Mietunterkünfte as §14.1 point 3 requires:
`Tabelle 1b HH Miete` (by size of the Haushaltsgemeinschaft) and
`Tabelle 2b BG Miete` (by Bedarfsgemeinschaft type).

2026-05 and every later month return 404: the series runs about four months
behind. April 2026 is therefore the newest month the Stichtag admits, not a
choice.

**Volume deviation.** The full download is 5,202 workbooks and roughly 1.5 GB, so
the workbooks are not committed. What is committed is the parsed extract plus a
manifest carrying the source URL, retrieval date, byte size and SHA-256 of every
workbook that went into it, so any file can be fetched again and checked against
what was parsed. The national workbook `kdu-d-0-202604-xlsx.xlsx` is committed
verbatim because its `Hinweis_SGB-II_Wohnkosten` sheet carries the BA's own
methodological notes.

**Annual average deviation.** §14.1 asks for a twelve-month average as robustness.
The twelve monthly Kreis panels are averaged during the fetch and only the average
is committed, again for volume. `n_months` records how many months contributed to
each cell.

Not in this source, and therefore not delivered: **Bezugsdauer**. D11 hoped for it
in the same release. The Wohn- und Kostensituation reports stocks, floor area and
costs only; duration of receipt is a separate BA product
(`Zeitreihen zur Verweildauer`) and would have to be fetched on its own.

The portal answers 403 when a run fetches too quickly. The fetcher uses three
concurrent connections and backs off 30–480 seconds on 403, 429 and 503.

### Zensus 2022 Gemeinde rents (§15)

| | |
|---|---|
| Publisher | Statistisches Bundesamt |
| Product | Zensus 2022, Regionaltabelle "Gebäude und Wohnungen", sheet `CSV-Wohnungen` |
| URL | `https://www.destatis.de/static/DE/zensus/gitterdaten/Regionaltabelle_Gebaeude_Wohnungen.xlsx` |
| Stichtag | 2022-05-15 |
| Rows | 12,439 — 10,786 Gemeinden, 1,207 Gemeindeverbände, 400 Kreise, 29 Regierungsbezirke, 16 Länder, Bund |

Kept per region: the mean Nettokaltmiete per square metre (`QMMIETE`), the dwelling
counts across ten Nettokaltmiete classes, the dwelling counts across ten
floor-area classes, the mean floor area per dwelling, the dwelling total and the
dwellings rented for residential use.

10,776 of the 10,786 Gemeinden join `data/gemeinde_lookup.arrow` on the
twelve-digit Regionalschlüssel. The ten that do not, and the 204 lookup Gemeinden
with no Zensus row, are Gebietsstand differences between the 2022 Zensus and the
lookup's vintage and are listed by `task_zensus.py`'s output rather than dropped
silently.

These are **Bestandsmieten**. Every column name and docstring says so, and
`fail_if_measure_names_claim_availability` refuses any measure name that would
turn a mean over existing tenancies into a statement about what a searching
household can find.

## The Jobcenter ↔ Kreis crosswalk (§14.3)

Built in `build_jobcenter_kreis_crosswalk` from the BA's own region labels and
checked against the BA's own stock of Bedarfsgemeinschaften. For all 393
territories the Jobcenter stock equals the sum over the Kreise served, to the
person.

- 404 Jobcenter, 401 Kreise, every one of them mapped.
- **398 Jobcenter serve exactly one Kreis.** Under D1 the Kreis is the policy
  region, so these are one policy region each.
- **6 Jobcenter span several Kreise**: Vorderpfalz-Ludwigshafen (4: Frankenthal,
  Ludwigshafen, Speyer, Rhein-Pfalz-Kreis), Landau-Südliche Weinstraße (2),
  Deutsche Weinstraße (2: Bad Dürkheim, Neustadt a. d. Weinstraße),
  Amberg-Sulzbach with Amberg Stadt (2), Neustadt-Weiden (2), Straubing-Bogen with
  Straubing Stadt (2).
- **Berlin runs the other way**: twelve Bezirks-Jobcenter share the single Kreis
  Berlin. Each still serves one policy region, so all twelve are main sample.

Label matching alone leaves 21 Jobcenter unresolved, because the two files spell
the same territory differently and because six Jobcenter are named after no Kreis
at all. `JOBCENTER_KREIS_OVERRIDES` resolves those explicitly; every entry was
verified by the stock identity rather than assumed.

**06415 Hanau** is the 401st Kreis, against the 400 of D1. It appears in the BA
release only from 2026-01 onwards; the eight earlier months return 404 and are
skipped, and `n_months` reaches 3 for it in the annual average. Two further Kreise
reach 11 rather than 12 — 05374 Oberbergischer Kreis and 08327 Tuttlingen —
because a month is withheld. Everything else has all twelve.
`data/kdu_gemeinden.csv` has no row under that AGS, because Hanau still sits inside
the Main-Kinzig-Kreis there. Whoever joins the BA table to the KdU table has to
decide what rule applies to Hanau; nothing here decides it.

## Blocked

### Zensusdatenbank API — mean Nettokaltmiete within a floor-area class

§15.2's `s(h)` wants the Zensus mean rent for the apartment size class that matches
the local Wohnflächenobergrenze. The free Regionaltabelle publishes the two
marginal distributions — dwellings by rent class and dwellings by floor-area class
— but not the mean rent *within* a floor-area class. That cross-tabulation exists
only in the Zensusdatenbank at `https://ergebnisse.zensus2022.de`.

Its API is closed to unauthenticated requests:

- `POST https://ergebnisse.zensus2022.de/api/rest/2020/catalogue/tables` with empty
  credentials returns
  `{"Code":15,"Content":"Sie sind nicht berechtigt diesen Service aufzurufen …"}`.
- The web front end's own proxy at `https://ergebnisse.zensus2022.de/proxy/api/rest`
  serves `settings/instance`, `help/faq` and `information/*` without credentials,
  but answers **403** to `statistics`, `variables`, `tables/structure`,
  `tables/{code}/information` and `search`, with or without browser headers, a
  session cookie or a `uuid` header.
- `POST /proxy/api/rest/sessions` needs a registered account; the instance settings
  report `"allowRegistration": true` and `"contactMail":
  "zensusdatenbank-reg@destatis.de"`.

**What the user needs to do:** register a free account at
`https://ergebnisse.zensus2022.de`, then either export the Gemeinde-level table of
Nettokaltmiete by Wohnfläche from the web front end, or put the credentials into
the GENESIS-style API at `https://ergebnisse.zensus2022.de/api/rest/2020/`. No
substitute source was used in the meantime.

**Fallback that exists but was not built.** Destatis publishes
`https://www.destatis.de/static/DE/zensus/gitterdaten/Durchschnittliche_Nettokaltmiete_nach_Gebaeudealter_und_Wohnungsgroesse.zip`
— mean Nettokaltmiete by building age and dwelling size in 100 m grid cells, free
and unauthenticated. Aggregating it to Gemeinde level needs a spatial join against
`Shapefile_Zensus2022.zip` and dwelling-count weights. That is a different piece of
work from parsing a published Gemeinde table, so it is recorded here rather than
attempted.

### BA Bezugsdauer

D11 asks for Bezugsdauer alongside the Bedarfsgemeinschaften stocks. It is not in
the Wohn- und Kostensituation. Nothing is blocked technically — the data are published in a
different BA product — but it is out of the scope that was fetched here.
