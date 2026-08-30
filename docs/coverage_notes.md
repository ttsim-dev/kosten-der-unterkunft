# P0.1 coverage and provenance notes

What the harmonised KdU data covers, what it does not, and where the evidence stops.
Every figure here is produced by `src/kdu/data_management/task_harmonise.py` and
`task_quality.py` and is reproducible with `pixi run pytask src/kdu/data_management`.

## Headline coverage

| Measure | Value |
| --- | --- |
| Gemeinden in the long table | 10,980 |
| Rows (`ags` by `household_size`, h = 1…5) | 54,900 |
| Policy regions (Kreise, D1) | 400 |
| Gemeinden with a Bruttokaltmiete cap for h = 1…4 (`analysis_sample_main`) | 9,442 |
| Kreise in the main sample | 357 |
| Population in the main sample | 75.5 m of 84.7 m (89.2 %) |
| Gemeinden balanced over h = 1…5 | 8,543 |
| Gemeinden in `analysis_sample_extended` | 10,047 |
| Gemeinden in `exclusion_log.csv` | 1,538 |

The main sample reproduces D3's 9,442 / 357 exactly; `task_harmonise.py` asserts both
numbers and fails the build if either moves.

## The K−W comparison runs on 9,323, not 9,442

119 of the 9,442 main-sample Gemeinden have no statutory Mietenstufe, so no Wohngeld
benchmark exists for them under the statute (decision log A2). They stay in the sample
with `wogg_rent_level_missing = True` and null `wogg_*`. Both numbers must appear
wherever coverage is stated.

## Coverage by Bundesland

`bld/coverage_by_state.csv` carries the full table. The spread is wide and is a finding
in its own right: Schleswig-Holstein, Hamburg, Bremen, Saarland, Berlin, and
Sachsen-Anhalt are at 100 % of Gemeinden in the main sample, while
Mecklenburg-Vorpommern is at 66.9 % and Hessen at 76.7 %. The shortfall is concentrated
in Kreise that publish a Nettokaltmiete cap only, or that publish nothing.

## Why 1,538 Gemeinden are outside the main sample

| Scope | Reason code | Gemeinden |
| --- | --- | --- |
| all samples | `kein_dokument` | 618 |
| all samples | `ableitungsverbot` | 135 |
| all samples | `gemeindefreies_gebiet` | 83 |
| all samples | `nur_eur_pro_qm_ohne_flaeche` | 50 |
| all samples | `nur_bruttowarm` | 46 |
| all samples | `nicht_oeffentlich` | 1 |
| main sample only | `nur_nettokaltmiete` | 576 |
| main sample only | `haushaltsgroessen_unvollstaendig` | 29 |

The first six sum to D3's 933 Gemeinden with neither cost concept. The last two hold a
rule the main sample cannot use and enter `analysis_sample_extended` instead — the 576
under the cold-opex scenario band, the 29 at whatever household sizes they cover.

`gemeindefreies_gebiet` is read off the Gemeinde type in `gemeinde_lookup.arrow`, never
off the notes text: only three of the affected Gemeinden mention it in `notes` (A2).

## Provenance

389 distinct `source_document` citations resolve to 451 source components:

| | Count |
| --- | --- |
| Citation components matched to a corpus file | 419 |
| Components that are a URL or a described web page | 25 |
| Components naming a document the corpus does not hold | 7 |
| Citations fully matched to files | 357 of 389 |
| **Citations resolving to no file at all** | **19 of 389** |
| Corpus files with a sha256 in the register | 419 |
| Corpus files with an extracted text layer | 247 |

The 19 unmatched citations are the headline provenance gap. 16 of them are URLs or
described web pages — a Jobcenter page rather than a PDF, so no document was ever
archived. The remaining components name a file the corpus does not contain, for example
`Bearbeitungshinweise Unterkunft - SGB II (Stand 01.01.2026).pdf`, where a
similarly-named file exists (`260130_Bearbeitungshinweise_2026.pdf`) but is not the same
name. Nothing is matched by similarity; near misses are reported as unmatched.

`publication_date` is empty throughout the register: the collection never recorded one.
The manifest's date is the Wirksamkeitsdatum and is carried as `valid_from`.
`retrieval_date` is the corpus file's modification date, which is when it was fetched.

## Whether each cap was printed or computed

`derived_value_flag` has three states and is never guessed at.

| Flag | Evidence | Rows |
| --- | --- | --- |
| `printed` | `found_in_text` | 21,497 |
| `computed` | `components_sum` | 2,430 |
| `unknown` | `no_text_available` | 18,849 |
| `unknown` | `no_amounts_in_text` | 2,918 |
| `unknown` | `not_found_in_text` | 666 |
| `unknown` | `no_cap` | 8,540 |

`computed` is the case D3 anticipates: 498 Gemeinden across 21 Kreise whose
Bruttokaltmiete is exactly a printed Nettokaltmiete plus a printed cold-cost cap.

`no_text_available` is the largest state and is a corpus limitation, not a data problem:
only the 444 harald-thome documents have a `pdftotext` extraction, so roughly half the
Gemeinden cite a document there is no text to search.

`no_amounts_in_text` marks documents whose extraction contains *none* of the caps
recorded against them. Those are image-only tables and failed scans; a missing amount
there is evidence about the extraction, not about the value.

`not_found_in_text` is the state that matters. 666 rows, **202 Gemeinden across 16 Kreise
and 16 documents**, where the extracted text does contain some of the document's caps but
not this one. Spot-checking Hildburghausen (`KdU Hildburghausen LK - 30.10.2024.pdf`)
shows why: the document prints a Nettokaltmiete of 280 € and a 48 m² area cap, and the
recorded Bruttokaltmiete of 353 € implies a cold-cost rate of 1.52 €/m² that the document
does not print as a total. The value is very likely derived rather than transcribed, but
nothing in the corpus proves the rate, so the flag stays `unknown` and every such row is
on the validation worklist.

## Quality tiers

| Tier | Reason | Rows | Gemeinden (h = 1) |
| --- | --- | --- | --- |
| A | `printed_gross_cold_verified` | 20,302 | 4,138 |
| B | `components_reproducible` / `gross_cold_unverified` | 21,670 | 4,413 |
| C | everything else | 12,928 | 2,429 |

In `analysis_sample_main`: 4,138 A, 4,413 B, 891 C.

Two deviations from §6.4 are recorded here rather than buried:

1. §6.4 puts only tiers A and B in the main analysis. D3 defines the main sample by data
   completeness instead, and D3 overrides. 891 tier-C Gemeinden are therefore inside
   `analysis_sample_main`, carrying `quality_tier` and `quality_tier_reason` so any
   analysis can condition on them. The C reasons there are `no_effective_date` (1,868
   rows), `no_primary_document` (1,096) and `region_assignment_ambiguous` (600).
2. §6.4's tier B means "reproducible from documented components". A third case exists in
   this corpus and §6.4 does not name it: a primary document is held, the cap is a
   Bruttokaltmiete total, but the document has no text layer, so print status cannot be
   verified. Those rows are tier B under the reason `gross_cold_unverified`, which keeps
   them countable and separable from the rows §6.4 means.

§6.4's "Haushaltsgrößen vollständig" is read against h = 1…4, the sizes the main analysis
is defined on (D3). A document that stops at four people is complete for that analysis;
the h = 5 gap is carried separately by `all_household_sizes_complete`.

## The cold-opex scenario band

D3 sends the 576 Netto-only Gemeinden to the extended sample under a low / mid / high
band, but fixes no numbers. §6.3 forbids importing a nationwide average, so the band is
the 10th, 50th, and 90th percentile of the €/m² cold-cost figures the KdU documents
themselves publish, pooled with the €/m² rates implied by Gemeinden that publish both a
Nettokaltmiete and a Bruttokaltmiete. Where a Gemeinde publishes its own €/m² figure,
that local value replaces the band's mid point. 546 of the 576 receive scenario values;
the other 30 publish no admissible Wohnfläche to multiply by. No headline uses any of
these three numbers.

## The §6.6 validation worklist

`bld/validation_worklist.csv` holds 14,462 Gemeinde-by-household-size observations,
one row per observation, with the corpus path of every cited document and the exact
figure to check. The strata:

| Stratum | Observations |
| --- | --- |
| `quality_tier_c` — every tier C observation | 12,928 |
| `derivation_unverified` — one per Kreis whose print status is unknown | 225 |
| `stratified_random` — seeded, 16 Bundesländer, at least 5 each | 108 |
| `non_monotone` — every Gemeinde whose cap falls with household size | 80 |
| `extreme_kdu_wogg_deviation` — 20 largest positive and 20 largest negative | 40 |
| `large_neighbour_jump` — Gemeinden whose cap steps far across a real border | 1,343 |

The random sample uses `np.random.default_rng(20260831)`, so the worklist is byte-stable
across runs; a test asserts it.

Every row whose cited document has a usable text extraction was checked automatically
against that text:

| Outcome | Rows |
| --- | --- |
| `pass` — the amount is in the source text | 1,990 |
| `fail` — the amount is absent from a readable source text | 219 |
| `manual` — no text layer, no readable amounts, or no amount to check | 12,253 |

The pass rate on what could be checked is **90.1 %** (1,990 of 2,209). The failures
concentrate in a handful of documents and are the first thing a human should open.

### `large_neighbour_jump` changed kind when P1.1 landed

The stratum used to rest on a surrogate, because true Gemeinde adjacency did not exist:
it ranked Kreise within a Bundesland by their median h = 1 cap and flagged steps above
the 95th percentile of that distribution, contributing **one row per flagged policy
region — 18 rows in all**.

It now selects on `bld/neighbour_jump_flags.parquet`, which compares each Gemeinde's cap
against those of its **directly adjacent Gemeinden in another policy region**, across a
shared border of at least 250 m, and flags a step above the 95th percentile of all such
cross-border steps at that household size. The unit is therefore the Gemeinde, not the
policy region, and the stratum contributes **1,343 rows across 614 Gemeinden** — 3.6 % of
all `ags × household_size` rows, and 6.8 % of the rows that have an eligible cross-border
neighbour at all.

The worklist grew from 13,281 to 14,462 rows for that reason alone, and the automatic
agreement rate moved from 87.2 % (1,281 of 1,467) to 90.1 % (1,990 of 2,209) because the
larger stratum draws in more rows whose document carries a text layer. Both are measured
agreement rates on the checkable subset and neither is extrapolated to the full table.

`has_cross_border_neighbour = False` marks a Gemeinde with no eligible cross-border
neighbour — an island, or one whose whole Kreis boundary is a suspected geometry
artefact. Those rows are never flagged, and the distinction matters: no evidence of a
jump is not evidence of no jump. It covers 48 % of rows.

A large step across a Kreis boundary is what §13 documents as normal, so the stratum is a
worklist of rows worth looking at, never a list of rows that are wrong.

## The two WoGG-link detectors do not agree, and that is the point

D7 requires two independent detectors that cross-validate. They do not.

| | Gemeinden | Kreise |
| --- | --- | --- |
| Detector 1, `notes` wording | 909 | 31 |
| Detector 2, `K/W` at the markup for every household size | 1,492 | 54 |
| Either | 2,024 | — |
| **Disagree** | **1,647** | 58 |

`bld/wogg_link_disagreements.csv` lists all 1,647 for manual review. No detector
overrides the other and `wogg_linked_flag` is the union, so nothing is silently resolved.

D7's own counts are 37 and 72 Kreise. Neither is reproduced. The gap is a definitional
one, not a data one: D7 does not state the notes pattern or the ratio tolerance it used,
and both counts move sharply with either choice. See the reported deviations.
