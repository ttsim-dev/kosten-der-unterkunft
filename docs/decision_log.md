# Decision log

Binding decisions for the KdU proxy-error project. Every decision here overrides the
prose of `Priorisierter Analyse- und Implementierungsplan_ Kommunale KdU-Obergrenzen.md`
where the two conflict. Agents must read this file before touching anything.

Deviations from the written plan are marked **[DEVIATION]** and carry their reason.

## D1 — Policy region is the Kreis

`policy_region_id = ags_kreis`. 400 Kreise.

The Kreis is the legally responsible Träger and the entity that publishes the
Richtlinie, so it is the unit at which an independent policy decision is taken.

**[DEVIATION from §6.5 check 5]** 210 of 400 Kreise carry more than one distinct
`max_bruttokaltmiete_eur_1p`, because they define Vergleichsräume internally. Check 5
("identical values within a policy region") therefore becomes a *descriptive* report of
within-Kreis dispersion, never a violation flag. Clustering and weighting scheme 3 run
on the 400 Kreise.

## D2 — Analysestichtag is 2026-08-31

The close of data collection; the latest source document takes effect 2026-08-01.
Every region contributes the rule in force on that date.

- WoGG Rechtsstand: the Anlage 1 and Mietenstufen values already in the CSV (see D6).
- SGB Rechtsstand: 2026.
- BA reference month: the latest available month ≤ 2026-08.

The sample mixes document vintages (1 Kreis 2019, 5 in 2022, 14 in 2023, 63 in 2024,
178 in 2025, 103 in 2026, 36 undated). This is stated openly and is the object of study
in P2.1, not a defect to be hidden.

## D3 — Main sample: Bruttokaltmiete only, h=1–4 balanced

`analysis_sample_main` = Gemeinden with a `max_bruttokaltmiete_eur_*` value for **all**
of h = 1, 2, 3, 4. That is **9,442 Gemeinden across 357 Kreise**.

- h=5 is reported separately on the 8,543 Gemeinden balanced over h = 1…5, always
  labelled with its own N.
- Households ≥ 6 go to the annex via `max_bruttokaltmiete_eur_addl` (6,653 Gemeinden).
- Every cross-h object — the h=1 vs h=4 maps on one colour scale, the Familien-Tilt,
  the Spearman rank stability, the decile transition matrix — is computed on the fixed
  h=1–4 sample.

### The 576 Netto-only Gemeinden

They have a Nettokaltmiete cap, no Bruttokaltmiete, and **no** `max_kalte_bk_eur_*`
total (139 have only a €/m² figure). They enter `analysis_sample_extended` **only**,
converted under an explicit low / mid / high kalte-Betriebskosten scenario band — the
same three-scenario device §15.1 prescribes — and are always reported separately, never
pooled into a headline. §6.3's ban on nationwide averages stands: no single imputed
value is ever presented as *the* number.

### The 933 Gemeinden with neither concept

51 Kreise. Straight to `exclusion_log.csv` with a reason code drawn from `notes`:
`gemeindefreies_gebiet`, `kein_dokument`, `nur_bruttowarm`, `nur_eur_pro_qm_ohne_flaeche`,
`ableitungsverbot`, `nicht_oeffentlich`.

## D4 — The source corpus is stored in Sciebo

`/Users/marvin/sciebo/RA-SOPHIA/KdU/` holds:

- `kdu_pdfs/thome/` — 444 documents from the harald-thome.de collection
- `kdu_pdfs/own_research/` — 219 documents fetched from the responsible authority
- `kdu_pdfs/converted_text/` — 444 extracted `.txt` files
- `kdu_pdfs/ocr_searchable/` — 80 OCR'd PDFs
- `kdu_manifest.csv` (446 rows: region, doc_type, valid_from, filename, url)
- `kdu_validity_index.md`, `kdu_region_to_kreis.csv` (395 rows with a confidence column)
- `kdu_extract_per_kreis/` — the 400 per-Kreis extracts the codebook advertises

The path is configured once in `src/kdu/config.py` (overridable by the `KDU_CORPUS`
environment variable). PDFs are **never** copied into the repo. §6.6 validation is
executed against `converted_text/` where possible and against the PDF otherwise.

## D5 — Repo layout follows AGENTS.md, filenames follow §5.2

**[DEVIATION from §5.1]** No `src/config/`, `src/analysis/`, `src/figures/`,
`src/tables/`, `output/`. Instead:

- `src/kdu/data_management/` — harmonisation, benchmark, crosswalks
- `src/kdu/analysis/` — P0.3 … P1.3
- `src/kdu/simulation/` — P0.6, P0.7
- `src/kdu/final/` — figures, tables, the existing map
- all generated artefacts to `bld/` (gitignored) under exactly the §5.2 names
- committed inputs stay `.csv` / `.arrow`; intermediates `.pkl`; `bld/*.parquet` is fine
  because `bld/` is ignored wholesale
- every task is a pytask task registered through the `DataCatalog` in `src/kdu/config.py`

All legal and temporal parameters are defined in one `src/kdu/config.py` block. No year or
legal parameter is allowed to appear in an analysis module.

## D6 — Wohngeld benchmark

**Superseded in part by D15**, which moves the primary benchmark to
`wogg_base_cap × 1.10`. What survives from D6: all variants are always computed, the
robustness rows are mandatory rather than optional, and `wogg_heating_relief` enters
none of them. The facts recorded below about the underlying columns are unaffected.

**[DEVIATION from §4.4]** D6's original choice of primary was the base Höchstbetrag
alone:

```
W = wogg_base_cap                    (primary until D15; now a robustness row)
W_klima = wogg_base_cap + wogg_climate_component   (robustness)
```

Reason given at the time: the paper's claim is about the error tax-transfer models
actually make, and the bare Anlage 1 table is what such models substitute. D15 rejects
this as a description of current practice rather than of the correct fallback.

`wogg_heating_relief` is stored as its own column and is **never** added to either.

Facts already settled about the existing columns:

- `wogg_hoechstbetrag_eur_1p/2p/4p` are **base only**, no Klimakomponente, and are
  **2026 values**. The codebook's "in force 1.1.2025" / "Anlage ab 1.1.2023" wording is
  stale and must be corrected in place — the values themselves are not to be re-derived.
- **3p and 5p are missing and must be added** from the same 2026 Anlage 1 table.
- The lookup key is `wogv_mietstufe`, the purely statutory Mietstufe, because a
  Wohngeldstelle applies the statute regardless of what a KdU document claims. The 259
  Gemeinden where `wogg_mietstufe != wogv_mietstufe` do not change this.
- All `kdu_vs_wogg_pct_*` columns must be recomputed once 3p/5p exist.

## D7 — The WoGG-linked Kreise are flagged, kept, and reported both ways

**1,203 Gemeinden (12.9 % of the h=1 sample) have `K/W` exactly 1.100**, because BSG
case law (B 4 AS 16/11 R; B 4 AS 87/12 R) lets a Kreis without a schlüssiges Konzept use
the § 12 WoGG table plus a 10 % Sicherheitszuschlag. For them the proxy error is a
definitional identity, not an empirical fact.

Add `wogg_linked_flag`, detected **two independent ways that must cross-validate**:

1. `notes` matching the Sicherheitszuschlag / WoGG-Tabelle pattern (37 Kreise), and
2. `K/W` within tolerance of 1.10 across household sizes (72 Kreise).

Disagreements between the two detectors are listed for manual review.

They stay in `analysis_sample_main` — a model substituting W does mismeasure by
+10 % there. But **every headline in Table 2 and every map carries a with/without pair**,
and no text may present the pooled median as an empirical regularity. It is not one:

| | median K/W, all | median K/W, excl. flagged | share flagged |
|---|---|---|---|
| h=1 | +10.3 % | +13.9 % | 12.9 % |
| h=2 | +10.1 % | +10.8 % | 11.4 % |
| h=4 | +10.1 % | +12.6 % | 14.4 % |

That ~14 % of Gemeinden have no independent schlüssiges Konzept is itself a P2.1 finding.

## D8 — Population from the Destatis Gemeindeverzeichnis

`gemeinde_lookup.arrow` has no population and no area. Fetch the Destatis GV-ISys
Jahresausgabe (8-digit AGS, Bevölkerung, Fläche in km²), commit as
`data/gemeinde_population.arrow` with the Gebietsstand recorded.

The chosen vintage **must reproduce exactly the 10,980 AGS** in `gemeinden.geo.json`;
any AGS that fails to join is an error to be resolved, never dropped silently.

This unblocks: §8.2 population weighting, §8.3 Gemeindegrößenklassen, §9.1's
`<10.000 / ≥10.000 Einwohner` split (the institutional core of Beitrag 3), Table 1's
Bevölkerungsabdeckung, P1.1 density, P1.2 population-weighted Kreis means.

## D9 — Microsimulation model: GETTSIM 1.3

Add `gettsim` to `pyproject.toml`, run `pixi lock`, commit both together.

**Mandatory prerequisite:** audit how GETTSIM itself treats Wohnkosten before anything
is built on it. If GETTSIM applies its own cap — Wohngeld-derived or otherwise — that
cap must be neutralised, or the K/W contrast is contaminated at the root. This audit is
wave-1 work precisely because a negative result changes the P0.7 design.

Keep a thin, separately tested KdU module in this repo that owns the `min(m, cap)` logic
and hands GETTSIM a recognised amount, so a GETTSIM release cannot invalidate the finding.

## D10 — Simulation grid: unique caps, bisection for y*

The 9,442 main-sample Gemeinden contain only **1,099 distinct (K-vector, Mietstufe)
cells**, and only ~780–910 distinct (K, W) pairs per household size.

- Simulate on those cells, never per Gemeinde; left-join back to all 9,442 afterwards.
- Keep the ≤25 € income grid for the budget curves of §12.6 / Figure 3.
- Locate `y*^K` and `y*^W` by **bisection to €1**. The Anspruch is monotone in income,
  so bisection is exact in ~10 evaluations, and `Δy*` and `ΔH` then carry no grid
  artefact. The bisection must **assert** monotonicity rather than assume it.

## D11 — Karenzzeit

All Modellhaushalte are declared **beyond month 12**, so the cap is in force and the
K/W contrast is well defined.

**[GAP CLOSED — the plan never handles this]** Under § 22 Abs. 1 S. 2–3 SGB II the
Karenzzeit suspends the cap for the first 12 months: actual Unterkunftskosten are
recognised in full, so the proxy error is **identically zero** for a Bedarfsgemeinschaft
inside it. One explicit limitation sentence is mandatory in the results text: all
reported Δ are conditional on the cap being in force.

## D12 — The existing map survives as a QC tool

`task_map.py` keeps producing `bld/germany_map.html`, rebuilt on the long table. It is
the internal data-inspection surface — genuinely useful for spotting the border jumps
P1.1 hunts for. No agent refactors `maps.py` / `measures.py` / `hatching.py` beyond the
wide-CSV → long-table swap.

The §19 figure program is defined in new `src/kdu/final/task_figures_*.py` modules with their
own deliberately austere styling. `measures.py` gains the proxy-error measures only once
the long table exists.

## D13 — Language

Code, identifiers, docstrings, comments: **English** (AGENTS.md mandates it).

Figure labels, table headers, column names, `decision_log.md`, `quality_report.html`,
and the §21 result interpretations: **English**.

German is kept only for terms with no faithful translation: Bruttokaltmiete,
Nettokaltmiete, kalte Betriebskosten, Mietenstufe, Bedarfsgemeinschaft, Kosten der
Unterkunft, Kreis, Gemeinde, kreisfrei, schlüssiges Konzept, Vergleichsraum,
Regelbedarf, Mehrbedarf, Karenzzeit, Härtefall.

§20's forbidden terms apply in translation too: never "generosity", "restrictiveness",
"causal effect", "actual KdU payment" for a cap, "housing availability" from a mean
rent, "full Existenzminimum" without heating.

## D14 — Data shape

The canonical table is **long**, keyed `ags × household_size`, per the pandas module's
normal-form rules. The wide 43-column `data/kdu_gemeinden.csv` remains the committed
raw input and is never overwritten in place.
---

# Addenda — corrections established during implementation

## A1 — Corrections to D6 (established by the P0.2 module, verified against three sources)

- The Höchstbeträge are the Fassung **in force since 2025-01-01** (BGBl. 2024 I Nr. 314,
  2. VO zur Fortschreibung des Wohngeldes nach § 43 WoGG). D6's phrase "2026 values" is
  right in substance — these are the values in force at the 2026-08-31 Stichtag — but the
  correct citation date is 2025-01-01, and that is what must appear in every table note.
  The Klimakomponente (§ 12 Abs. 7) and Heizkostenentlastung (§ 12 Abs. 6) still carry
  their 2023-01-01 Wohngeld-Plus Fassung. Two Fassung dates, one consistent Rechtsstand.
- `wogv_mietstufe` is missing for **205** Gemeinden, not 160.
- `wogg_mietstufe != wogv_mietstufe` for **54** Gemeinden, not 259. The codebook is right.
- The reconstruction of 1p/2p/4p from `data/wogg_parameters.csv` reproduces the committed
  `wogg_hoechstbetrag_eur_*` **exactly for all 10,775** Gemeinden with a non-null
  `wogv_mietstufe`. The benchmark is confirmed sound.

## A2 — §7's completeness criterion is not satisfiable, and this shrinks the comparison sample

**119 of the 9,442 main-sample Gemeinden, across 27 Kreise, have a Bruttokaltmiete cap
but no statutory Mietenstufe.** They are gemeindefreie Gebiete (Forstgutsbezirke,
`Harz (Landkreis Goslar)`, …) that the Anlage zur WoGV does not list, so under the
statute **no Wohngeld benchmark exists for them at all**.

Consequences, binding on every downstream module:

- They are kept in `analysis_sample_main` with null `wogg_*` and
  `wogg_rent_level_missing = True`. They are never silently dropped.
- Every K−W comparison — the proxy error, both maps, Table 2, the simulation — therefore
  runs on **9,323 Gemeinden**, not 9,442. State both numbers wherever coverage is
  reported; the gap is a finding, not a rounding detail.
- §7's acceptance criterion "vollständige Mietenstufenzuordnung für alle Gemeinden der
  Hauptstichprobe" is struck as unsatisfiable, with this reason recorded.
- **Only 3 of the 119 say "gemeindefrei" in `notes`**, so the `gemeindefreies_gebiet`
  exclusion reason code of D3 CANNOT be derived from the notes text alone. It must be
  derived from the absence of a statutory Mietenstufe combined with the Gemeinde type in
  `gemeinde_lookup.arrow`.

## A3 — The committed AGS is not corrupt (correction)

`data/kdu_gemeinden.csv` stores every AGS correctly as text: all 10,980
`ags_gemeinde` are eight characters and all `ags_kreis` are five. There is no
leading-zero loss in the committed file.

Leading zeros disappear only when the file is read **without** `dtype=str`, because
pandas then infers `int64`. Always read it as:

```python
pd.read_csv(path, dtype=str, keep_default_na=False, engine="pyarrow")
```

`crosswalk.pad_ags` guards that path defensively and is a no-op on correctly read
input. It is not evidence of a data defect.

## A4 — Geometry Gebietsstand is a reconstruction, not a published vintage

No single published Gebietsstand reproduces `data/gemeinden.geo.json`; the
OpenDataSoft export mixes vintages (31.12.2022 → 1 missing / 14 extra;
31.12.2023 → 3 missing / 4 extra; 31.12.2024 → 27 missing / 6 extra).

`data/gemeinde_population.arrow` uses **31.12.2023 as the base** plus two explicit,
code-visible reversals, and reproduces all 10,980 AGS exactly:

- `01059101` Tastrup and `01059141` Maasbüll, merged into `01059126` Hürup on
  2023-01-01, restored from 31.12.2022 and netted out of Hürup. Population and area
  both reconcile exactly, so nothing is double counted.
- `09374451` Heinersreuther Forst, a gemeindefreies Gebiet with 0 inhabitants,
  restored from 2022. Its 5.88 km² **is** double counted in the national area total
  (0.0016 %). Population is unaffected.

Report the Gebietsstand as "31.12.2023, reconstructed to the boundary set of the
committed geometry", never as an official vintage.

`data/gemeinde_lookup.arrow` has 10,981 rows, one more than the geometry:
`034579501501` Insel Lütje Hörn loses its polygon under the 1 km grid snap. It is
dropped by name as `LOOKUP_ONLY_AGS`, so any *other* lookup-only AGS raises instead
of being silently inner-joined away.

## A5 — Module-level attribute docstrings are rejected by this repo

The `check-docstring-first` pre-commit hook rejects docstrings placed after
module-level constants. Document module constants with `#` comments above them.
Docstrings on dataclass and enum members are fine.

## A6 — GETTSIM applies its own housing cap, and it had to be replaced (D9 resolved: GO)

**GETTSIM 1.3 caps Wohnkosten itself**, in `germany/bürgergeld/regelbedarf.py`:

```
kosten_der_unterkunft_m = berechtigte_wohnfläche
                          * min((bkm + heizkosten) / wohnfläche, 10 €/m²)
```

with `mietobergrenze_pro_qm_m = 10 €/m²` and
`berechtigte_wohnfläche = 45 m² + 15 m² per person`. It is **not** Wohngeld-derived —
it is an explicit rule-of-thumb whose own YAML description points at
[gettsim#782](https://github.com/ttsim-dev/gettsim/issues/782), the open issue about
missing regional parameters. **That issue is the gap this project fills**, which is worth
stating in the paper.

Left in place it would have destroyed the study, two ways:

1. **It binds at 450 € for a single person.** Recognised KdU measures as
   290/390/450/450/450/450 for rents of 200/300/360/400/500/700. Most of the h=1 sample's
   K *and* the W of 5 of 7 Mietenstufen lie above it, so both scenarios would truncate to
   the same value and **ΔT would have measured as zero across most of the sample** — a
   false null that looks like a finding.
2. **It is a warm cap**, applying to Bruttokaltmiete + Heizkosten jointly, which violates
   §12.3's requirement that heating be held constant so the whole difference comes from
   the cold cap.

**Neutralisation, verified exactly:** supply `bürgergeld__kosten_der_unterkunft_m` as an
input column. ttsim treats a supplied column as an override and prunes
`anerkannte_warmmiete_je_qm_m`, `berechtigte_wohnfläche` and `mietobergrenze_pro_qm_m`
out of the DAG. Pass-through is exact and linear to 1,590 € with no saturation, and the
contrast comes out right by construction: K=520, W=456, m=520 gives
T^K(0) − T^W(0) = 1173 − 1109 = 64 = K − W.

**The constraint that must never be forgotten: that column is per-person, not per-household.**
Passing the household total inflates the Bedarf by household size — invisible for
Modellhaushalt 1, wrong for the other three. Always split by Kopfteil first;
`kdu_cap.kopfteil_m()` owns this.

Replace GETTSIM's housing rule. Never merely reconfigure `mietobergrenze_pro_qm_m`.

## A7 — Rechtsstand 2026 confirmed, with one number to verify by hand

D2 stands: 2026 is genuinely parameterised in GETTSIM. Kindergeld, Kinderzuschlag,
Einkommensteuertarif, Lohnsteuer, Soli and the SV-Bemessungsgrenzen all carry explicit
`2026-01-01` entries; Bürgergeld and Wohngeld carry forward correctly (Nullrunde;
Anlage 1 is biennial).

**OPEN ITEM — must be checked against the Bekanntmachung before Gate 3:** Regelbedarf
RBS 1 = 563 € is carried from a 2024 entry rather than a dated 2026 entry. Every
Bedarfsniveau in P0.6 and every Anspruch in P0.7 rests on it.

Further confirmations and constraints:

- **D6 independently cross-validated.** GETTSIM's WoGG Anlage 1 for one person
  (361/408/456/511/562/615/677) matches `wogg_hoechstbetrag_eur_1p` by `wogv_mietstufe`
  exactly. Three independent sources now agree on the benchmark.
- **D11 is expressible verbatim:** `bürgergeld__bezug_im_vorjahr = True` puts the cap in
  force. (GETTSIM's docstring for it reads backwards from its code; the code is right.)
- **Mindestlohn 2026 = 13.90 €/h** (BGBl. 2025 I Nr. 268), so §12.6's
  ΔH = Δy* / 60.19.
- **§12.7 Vorrangprüfung exists and works but assumes WTHH = BG** (its own docstring).
  State as a limitation; it matters for Modellhaushalt 3.
- **Vectorisation:** one row per person, ~2 s *fixed* per `main()` call, flat to 22,000
  rows. D10's entire grid fits in one call; bisection for all four households ≈ 100 s.
  Reusing a prebuilt `tt_function` does not help — the cost is DAG assembly, not
  evaluation. Monotonicity confirmed on a 104-point ladder, so D10's bisection is sound.
- P0.7 must assert `np.isfinite` on results rather than filter GETTSIM's benign `0/0`
  `RuntimeWarning` for zero-income households.

## A8 — Corrections established by P0.1

1. **There are 16 non-monotone rows, not 15.** My count was taken on the h=1…5 balanced
   subsample. The 16th is **Kalletal (AGS 05766036, Kreis Lippe)**: 442.00 → 436.80 at
   h=2, missed because it has no h=5 value. The 8 flat steps are confirmed exactly.

2. **D7's detector counts do not reproduce, and D7 did not specify them.** D7 quoted
   37 Kreise from the notes regex and 72 from the ratio detector; the actual figures are
   31 and 54, and both move sharply with the pattern and tolerance chosen — neither of
   which D7 stated. What *does* reproduce exactly is the anchor that matters: **1,203
   Gemeinden with K/W = 1.100 at h=1** (atol 5e-4). The two detectors **disagree on 1,647
   Gemeinden across 58 Kreise**, all listed in `bld/wogg_link_disagreements.csv` and none
   silently resolved. `wogg_linked_flag` is the **union** of the two.

3. **§6.4 conflicts with D3, and D3 takes precedence.** §6.4 admits only tiers A and B to the main
   analysis; D3 defines the main sample by completeness of the Bruttokaltmiete. So **891
   tier-C Gemeinden sit inside `analysis_sample_main`**. `quality_tier_reason` lets any
   analysis condition on them, and the tier-A-only robustness row of §18 remains
   mandatory.

4. **D4 overstates the text coverage.** `kdu_pdfs/converted_text/` covers only the 444
   thome PDFs — **247 of the 419 held documents**, so roughly 46 % of Gemeinden cite a
   document with no searchable text. "Validate against converted_text where possible"
   leaves a far larger "not possible" than D4 implies.

5. **D3's cold-cost scenario band had no numbers.** It is now derived from the €/m² cold
   figures the KdU documents themselves publish (p10/p50/p90), never a national average,
   preserving §6.3. 546 of the 576 Netto-only Gemeinden get scenario values; 30 publish
   no admissible Wohnfläche.

6. **The codebook's "8,845 rest on a Bruttokaltmiete the document prints outright" is not
   verifiable** and is partly contradicted by 666 `not_found_in_text` rows.

### Tier definitions as actually implemented (two documented widenings)

- Tier B covers rows whose primary document is held but has **no text layer**, under the
  reason `gross_cold_unverified` (15,751 rows). Without this a corpus limitation, not a
  data defect, would push most of the table to tier C.
- §6.4's "Haushaltsgrößen vollständig" is read against **h = 1…4**, the sizes the main
  analysis is defined on. The h=5 gap is carried separately by
  `all_household_sizes_complete`. Without this, 783 fully evidenced main-sample Gemeinden
  would be tier C for a reason irrelevant to the main sample.

### Carried defects, to be fixed when their dependency lands

- `large_neighbour_jump` is a **surrogate**: true adjacency needs P1.1's geometry, so it
  currently ranks Kreise within a Bundesland and flags steps above the 95th percentile.
  **Recompute it when P1.1 lands** and re-derive the affected worklist stratum.
- `publication_date` is empty throughout `source_register.csv` — the collection never
  recorded one. `retrieval_date` is the corpus file's mtime, which is a proxy, not a
  record. Both must be described as such in the Methodenanhang.
- 19 of 389 source citations resolve to no corpus file. Nothing was matched by
  similarity, deliberately — but at least one is plainly the same document under two
  names (`Bearbeitungshinweise Unterkunft - SGB II (Stand 01.01.2026).pdf` vs
  `260130_Bearbeitungshinweise_2026.pdf`). These 19 are small enough to resolve by hand.

## A9 — §6.6's manual validation census is waived (data owner's decision)

The project owner, who collected the corpus, states confidence in the collected values.
§6.6's requirement to manually re-check every tier-C observation against the original
source is therefore **waived**, and Gate 1 closes without it.

What stands in its place, and what must be said in the Methodenanhang:

- All 12 automated checks of §6.5 ran and their violations are retained as warn flags in
  `bld/kdu_warn_flags.parquet`. Nothing was excluded by a check.
- The automated validation that *was* possible ran against `kdu_pdfs/converted_text/`:
  **1,467 observations checked, 1,281 pass, 186 fail — an 87.2 % pass rate**, with the
  failures concentrated in six documents.
- `bld/validation_worklist.csv` (13,281 observations) is retained as documentation of
  what a full audit would cover, not as work to be executed.
- The Methodenanhang states plainly: values rest on the collectors' extraction, verified
  automatically where a text layer existed and not otherwise. The 87.2 % figure is
  reported as the measured agreement rate on the checkable subset, and is **not**
  extrapolated to the full table.
- The 666 `not_found_in_text` rows and the 19 unmatched citations remain flagged in the
  data. They are described, not resolved.

## A10 — External data acquired (P1.2 / P1.3 inputs)

**BA "Wohn- und Kostensituation"** (Statistik der Bundesagentur für Arbeit, product
`kdu-kdu`), retrieved 2026-08-27.

- **Reference month 2026-04** — the latest published at or before the D2 Stichtag. The
  series runs roughly four months behind; 2026-05 onward returns 404. 401 Kreise and
  404 Jobcenter.
- Annual average 2025-05 … 2026-04 for the §14.1 robustness, with `n_months` per cell.
- Mietunterkünfte sheets only, so §14.1 point 3 holds.
- Unterkunftskosten / kalte Betriebskosten / Heizkosten kept separate; Bruttokaltmiete
  derived as the first two summed. This also neutralises the BA's own footnote 7, that
  some Träger fold Betriebskosten into Unterkunftskosten.
- **§14.1 point 6 is enforced in code**: `fail_if_measure_names_suggest_payment` rejects
  any measure name containing a payment/benefit/Leistung word. Columns are `actual_*` and
  `recognised_*` only — recognised costs are never mixed with disbursed benefits.
- BG stocks by household size and BG type are present, so §8.2's fourth weighting scheme
  and §14.5 are unblocked.
- Magnitude check: median `N^BA` on Bruttokaltmiete per BG across 400 Kreise is **3.5 %**
  (IQR 2.4–4.7 %).
- **The 5,209 workbooks (~1.5 GB) are NOT committed.** Committed instead: the parsed
  extracts (11 MB) plus `ba_download_manifest.csv` carrying URL, retrieval date, byte
  size and SHA-256 for every file, and the national workbook verbatim for its
  methodological notes. This is a deliberate, documented deviation from "commit the
  downloaded files".

**Zensus 2022** — Regionaltabelle "Gebäude und Wohnungen", retrieved 2026-08-27.
10,786 Gemeinden, of which 10,776 join the lookup. Mean Nettokaltmiete €/m², dwellings by
rent class, dwellings by floor-area class. Named and documented as **Bestandsmieten**
throughout, and `fail_if_measure_names_claim_availability` refuses any name implying
availability or Angebotsmieten (§15's limitations, §20's ban).

### Jobcenter ↔ Kreis, verified rather than assumed

404 Jobcenter, 401 Kreise, all mapped. The mapping is proven by a stock identity: for all
**393 territories the Jobcenter BG stock equals the sum over its Kreise exactly**, 0
mismatches (`bld/jobcenter_kreis_stock_check.parquet`).

- 398 Jobcenter serve exactly one Kreis.
- 6 span several: Vorderpfalz-Ludwigshafen (4); Landau-Südliche Weinstraße, Deutsche
  Weinstraße, Amberg-Sulzbach + Amberg Stadt, Neustadt-Weiden, Straubing-Bogen +
  Straubing Stadt (2 each).
- **Berlin runs the other way**: 12 Bezirks-Jobcenter share the single Kreis 11000. Each
  is still one policy region, so all 12 are main sample.
- **06415 Hanau is a 401st Kreis absent from `kdu_gemeinden.csv`**, published only from
  2026-01. Handle explicitly wherever BA and KdU are joined.

**§14.3 samples:** main = 398 Jobcenter covering 387 Kreise; extended = 6 Jobcenter
covering 14 Kreise. The sample is decided per Jobcenter, never per row, so no Jobcenter
straddles both.

### Open items from this module

- `bld/municipality_crosswalk_with_jobcenter.parquet` carries the filled `jobcenter_id`
  (10,979 of 10,980; Berlin is the exception, twelve Jobcenter). Two pytask tasks cannot
  write one product, so the owner of `task_crosswalk.py` must call `add_jobcenter_id`
  in place and retire the second file.
- **`openpyxl` must be declared in `pyproject.toml`** and `pixi.lock` regenerated in the
  same change.
- **Bezugsdauer is not in this BA product**, so D11's optional Karenz-share scaling has
  no source here. It is published in a separate BA release.

## A11 — BLOCKED: the Zensus floor-area × rent cross-tabulation needs a registered account

§15.2's market-stress indicator needs the mean Nettokaltmiete **within a floor-area
class**, to match `s(h)` to the admissible Wohnfläche. The free Regionaltabelle publishes
only the two marginals — mean rent, and dwellings by floor-area class — not the cross.

That cross-tabulation exists only at `ergebnisse.zensus2022.de`, which rejects anonymous
API access (`/api/rest/2020/…` → error 15; the front end's own proxy → 403 under every
header and cookie combination). A free registered account is required. **Nothing was
substituted.**

Until it is supplied, P1.3 can compare against the *overall* mean Gemeinde
Nettokaltmiete only, which ignores that small dwellings cost more per m² — biasing the
single-person market-stress indicator in a known direction that must be stated.

A grid-level fallback exists
(`Durchschnittliche_Nettokaltmiete_nach_Gebaeudealter_und_Wohnungsgroesse.zip`) but needs
a spatial join to Gemeinden. Recorded, not built.

## A12 — D7's table and D7's flag describe two different groups (correction)

D7 quotes a with/without table and a "share flagged" column. Those numbers were computed
on the **exact-ratio group** — rows where `K/W = 1.100` within `atol 5e-4` — and they
reproduce almost perfectly: 13.85 / 10.80 / 12.59 against the logged 13.9 / 10.8 / 12.6,
with the share reproducing to the digit (12.90 / 11.38 / 14.39).

But A8 item 2 defines `wogg_linked_flag` as the **union** of the two detectors, which is
a broader group: excluding it gives 14.13 / 10.80 / 12.73 and a share of **18.79 %**, not
12.9 %. So D7's table labels as "flagged" a group that D7's own flag does not define.

**Resolution — both are carried, neither is reconciled away.** Every with/without pair is
reported for two `LinkageGroup` values:

- `exact_ratio` — `K/W = 1.100` within 5e-4. 1,203 Gemeinden at h=1 (12.9 %). This is the
  group for which the proxy error is a *definitional identity*, and it is the one D7's
  quoted numbers refer to.
- `linked_union` — the union of the notes-regex and ratio detectors, 18.79 %. Broader,
  and the right group when asking which Kreise lean on the WoGG table at all.

Both are tested. Which one a given table uses must be stated in that table's note.

**Config corrected:** `WOGG_SAFETY_MARKUP_TOLERANCE` was 0.005, which admits a further
18.2 % of h=1 rows — Kreise that merely land near 1.10 rather than Kreise that adopted the WoGG
table. It is now **5e-4**, the value that isolates the 1,203.

## A13 — Ruff confusable characters

`−` (U+2212 minus), `×` and `–` are the correct characters in this project's docstrings,
figure labels and table headers (`K − W`, `MS × h`). `[tool.ruff.lint] allowed-confusables`
now permits them, clearing 27 RUF001 and 16 RUF002 findings across four modules. This was
a shared-file fix no single module agent could make.

## A14 — RBS 1 = 563 € is CORRECT for 2026 (A7's open item, resolved)

A7 flagged that GETTSIM carries Regelbedarfsstufe 1 forward from a 2024 entry. Verified:
**2026 is a Nullrunde.** The arithmetic Fortschreibung produced **557 €**, which is *below*
the 563 € in force, and the Besitzstandsschutz of **§ 28a Abs. 5 SGB XII** forbids a
reduction. RBS 1 therefore stays at **563 €** for 2026, identical to 2024 and 2025 —
exactly what GETTSIM carries forward. Asserted in `tests/test_needs_level.py`; the 557 €
counterfactual is recorded in `docs/simulation_assumptions.md` §1.

## A15 — Two GETTSIM input traps the audit missed

`alter` and `alter_monate` are **ordinary input columns**. They are *not* derived from
`geburtsjahr`, and they are **absent from the `input_data_dtypes` template** for this
target set. Left at their zero default GETTSIM runs cleanly and returns wrong numbers:

- adults get `familie__volljährig = False`
- children get the wrong Regelbedarfsstufe
- **the 70-year-old is paid Bürgergeld instead of Grundsicherung im Alter**

Same failure class as A6 — a silent, plausible, wrong answer — and not in
`docs/gettsim_audit.md`. The audit's own spike script avoided it only by supplying `alter`
incidentally. **Always set `alter` and `alter_monate` explicitly.**

## A16 — ΔT_max and ΔT(0) are one outcome, not two

§12.6 lists the Anspruch difference at zero income and the maximum Anspruch difference as
separate outcomes. **Measured, `delta_transfer_max_m` equals `|delta_transfer_zero_m|` in
every cell**, because the Bedarf difference is the constant `K − W` and both scenarios
apply an identical Anrechnung schedule. Both are reported, but the paper must **not**
present them as independent evidence.

Related, and worth stating plainly rather than dressing up: **§12.3's heating sensitivity
cannot move ΔT(0) by construction**, and the run confirms it to the cent (69.00 € at both
75 % and 125 % for the couple household). It shifts Δy* by at most 2 € for one household
and 0 € for the other three. It is a confirmation that the design isolates the cold cap,
not a robustness check carrying information.

## A17 — Deferred §12.2 coverage

Variante 2 (the 50–130 % rent grid) delivers ΔT(0) at every rent factor but **not** Δy*.
A full bisection at nine rent factors × four households adds ~15 minutes to every pytask
run, for a dimension whose shape is already clear: the two parameters are indistinguishable
below ~80 % of `max(K,W)` and saturated at or above 100 %. Documented in
`docs/simulation_assumptions.md`. Extend it if a reviewer asks for Δy* across the grid.

## A18 — The simplified geometry cannot support adjacency; use the raw export instead

**Measured, not asserted.** `data/gemeinden.geo.json` against the unsimplified source, over
the 10,980 shared AGS (`bld/tables/border_jump_geometry_fitness.csv`):

| | |
|---|---|
| true neighbour pairs **destroyed** | **916** (2.8 %) |
| false neighbour pairs **fabricated** | **765** (2.4 %) |
| edges shared by **more than two** polygons | **7,404** — impossible in a planar partition |
| recall / precision | 0.972 / 0.976 |

97 % accuracy is worthless here, because the neighbour graph *is* the analysis object rather
than an input to a smoothing step: 765 fabricated pairs are 765 fabricated border jumps, and
916 destroyed pairs are jumps that silently never get measured. The 7,404 over-shared edges
are the signature of the 1 km snap welding distinct polygons together.

**The fix, and BKG was not needed.** `bld/gemeinden_raw.geojson` — the unsimplified
OpenDataSoft `georef-germany-gemeinde` export that `pixi run prepare-gemeinden` downloads,
and which `data/gemeinden.geo.json` is *derived from* — is a valid planar
partition: **zero** edges shared by more than two polygons, 10,963 of 10,981 polygons with
at least one neighbour, minimum shared border 51 m and so no slivers. Adjacency is exact by
shared-edge matching; no geometry library and no new dependency. Projected area comes to
357,202 km² against the official 357,592 km² (0.11 % low, consistent with generalised line
work) — an independent check that the EPSG:3035 projection is right.

Two caveats, documented in the module: it is a BKG *derivative*, not VG250 itself, so
§13.1's named source is approximated; and its Gebietsstand is A4's reconstruction. Neither
affects the topology.

**Rule going forward: never compute adjacency, shared boundaries or areas from
`data/gemeinden.geo.json`. It is a display geometry.**

## A19 — Border jumps: the finding, and the handoff that closes A8's carried defect

32,230 neighbour pairs; 401 point contacts excluded; 461 (1.7 %) flagged as possible
artefacts at 250 m. Excluding `linked_union`:

| h | border type | n | share J=0 | median J^€ | share > 100 € |
|---|---|---|---|---|---|
| 1 | within policy region | 17,161 | **82 %** | 0 € | 1.2 % |
| 1 | between Kreise, one Bundesland | 3,121 | 0.4 % | 38 € | 12.9 % |
| 4 | within policy region | 17,161 | 82 % | 0 € | 4.6 % |
| 4 | between Kreise, one Bundesland | 3,121 | 1.0 % | **80 €** | **37.3 %** |
| 4 | between Bundesländer | 795 | 0.1 % | 97 € | **46.4 %** |

Inside a Kreis the cap is flat; across a Kreis boundary the median four-person household
faces an **80 € monthly step**, and more than a third of pairs exceed 100 €. The §13.4
point-6 tight comparison group (same Mietenstufe, Zensus rent within 10 %, similar density,
different policy region) retains 593 pairs and **does not close the gap**: median 75 €,
32 % above 100 € at h=4. Dropping suspected artefacts moves nothing beyond the second digit.

**This remains an administrative discontinuity, not a regression discontinuity.** No causal
claim. The guard is in the module and figure docstrings, the `comparison_group` and
`top_jumps` docstrings, part 4 of the interpretation, every figure subtitle, and the
`limitation` field of all four manifest rows.

### Handoff — replaces A8's `large_neighbour_jump` surrogate

`bld/neighbour_jump_flags.parquet` now holds the real flag. Per `docs/config_requests_p11.md`
the owner of `quality.py` must: add the dependency in `task_quality.py`; replace
`_neighbour_jumps`'s body with an inner join on the flagged `ags × household_size`, keeping
the stratum label; delete `NEIGHBOUR_JUMP_PERCENTILE` and `NEIGHBOUR_JUMP_THRESHOLD`; and
adjust the ladder fixture in `tests/test_quality.py`. No cycle exists.

Note in the Methodenanhang that the stratum changes **kind**: the surrogate picked one row
per flagged policy region, the real flag picks Gemeinden (6.9 % of `ags × household_size`),
so `n` grows. `has_cross_border_neighbour = False` distinguishes "no eligible neighbour"
from "no jump".

## A20 — BA validation: the association holds, but only conditionally

Main §14.3 sample, h=1…4, household-size and Bundesland fixed effects, SEs clustered on
Jobcenter (n = 1,412 rows, 353 Jobcenter):

| Group | n | β log(K/W) | β log(M/K) |
|---|---|---|---|
| all | 1,412 | **−0.0361** (0.0066) | **+0.0496** (0.0081) |
| excl. `exact_ratio` | 1,257 | −0.0324 (0.0065) | +0.0377 (0.0075) |
| excl. `linked_union` | 1,176 | −0.0307 (0.0065) | +0.0316 (0.0073) |
| `exact_ratio` only | 155 | **+0.3615 (0.6098)** | +0.1883 (0.0270) |

A higher local cap relative to Wohngeld goes with a **lower** non-recognised cost share, and
greater market pressure relative to the cap goes with a **higher** one. Both signs are as
expected. Phrase associationally only — §14.4 and §20 forbid causal language.

**THE CAVEAT THAT MUST TRAVEL WITH THIS RESULT.** The *unconditional* gradient nearly
vanishes: across deciles of `K/W` the mean ratio rises 0.835 → 1.365 (log distance 0.49)
while mean `R^BA` rises only **96.56 % → 96.79 %, i.e. 0.23 pp**, where β implies 1.78 pp.
The Bundesland fixed effects do most of the work, because Kreise with high caps are
disproportionately Kreise with expensive housing and the two pull `N^BA` in opposite
directions. **The binscatter must never be shown without the coefficient beside it**, and
the conditional nature belongs in the sentence, not a footnote.

**D7 degeneracy confirmed numerically:** `sd(log K/W)` is 0.1367 overall, **0.0070 in
`exact_ratio` (IQR exactly 0)**, 0.0420 in `linked_union`. Within `exact_ratio` β is +0.36
with a clustered SE of **0.61** — no identifying variation, no evidence either way, exactly
as D7 predicted.

**§14.5 reconciles with P0.3 exactly:** `D̄^BG` at h=1 is 21.4595 € against P0.3's
21.459512 — the same weighted average written two ways. h=4 is 66.14 €.

Table 5 weighted medians of `K − W` show the three weightings genuinely diverge:
h=1 → 38.65 unweighted / 37.78 population / **25.17 BG**; h=4 → 66.23 / 70.79 / 62.35.

Further limitations recorded in the artefacts themselves: `M^market` is a Nettokaltmiete
measured against a Bruttokaltmiete cap (and A11's floor-area cross-tab is missing), so
`M/K` understates market pressure; the extended 6-Jobcenter sample is labelled
`is_robustness_only` and its coefficients are indistinguishable from zero (n = 24,
6 clusters); Hanau (06415) is documented in `KREISE_ABSENT_FROM_KDU_TABLE`, and
`fail_if_unexpected_kreis_absent` raises on any *other* Kreis the BA reports but the KdU
table lacks, so a future boundary reform cannot drop one silently.

## A21 — OPEN: `analysis_sample_main.jobcenter_id` is entirely null

`bld/municipality_crosswalk.parquet` now carries `jobcenter_id` for 10,979 of 10,980
Gemeinden, but **`analysis_sample_main.parquet` has its own `jobcenter_id` column and it is
null throughout** — it is written by `task_harmonise`, which does not join the Jobcenter
mapping. P1.2 worked around it by sourcing the id from the crosswalk, so nothing currently
depends on it, but **it will silently mislead the next module that trusts it**. Either fill
it in `task_harmonise` or drop the column so the absence is loud rather than quiet.

## A22 — A12 corrected: `linked_union` is NOT a superset of `exact_ratio`

A12 calls `linked_union` "broader", which reads as a superset. **It is not.** At h=1:

- 1,137 Gemeinden are in **both**
- 615 are in **`linked_union` only**
- **66 are in `exact_ratio` only** — Gemeinden sitting exactly at `K/W = 1.100` at h=1 that
  the notes-based detector does not flag, because it applies its tolerance across household
  sizes

The correct wording, to be used everywhere: **"broader than, and not a superset of"**. The
two groups overlap heavily but neither contains the other, which is precisely why A12
requires every table to name which one it uses.

## A23 — The `.query("@CONSTANT")` bug class

`pandas.DataFrame.query` resolves an `@name` from the **caller's local scope only**. A
module-level constant is not found there, and the failure surfaces as
`UndefinedVariableError` — or, worse, as a plain missing import that no linter can see,
because the name lives inside a string.

Found and fixed at six sites: `simulation/needs_level.py` (which was *also* missing the
`SCENARIO_KDU` import from `simulation/microsim.py` altogether),
`simulation/microsim.py` (`BA_HEIZKOSTEN_MEASURE`, `BA_STOCK_MEASURE`), and
`final/task_figures_microsim.py` (`MAP_HOUSEHOLD_KEY`, three sites). **Always bind a
module-level constant to a local before using it in `query`.**

**Why this survived four green builds:** `pytask` skips a task whose outputs are
already up to date, so the graph stayed green while the code under it was broken. Only
`pixi run pytest` could see it. The four verification gates are not redundant — run all of
them, and do not read a green `pytask` as evidence that the code executes.

## A24 — The four closing items of P1, and three figures A12/A19/A20 do not reproduce

**A19's handoff is done.** `quality.py` now selects the `large_neighbour_jump` stratum
by an inner join on `bld/neighbour_jump_flags.parquet`; `NEIGHBOUR_JUMP_PERCENTILE` and
`NEIGHBOUR_JUMP_THRESHOLD` are gone. The stratum changed kind, as A19 predicted, and the
size of the change is recorded in `docs/coverage_notes.md`: **18 rows became 1,343 rows
across 614 Gemeinden**, and the worklist grew 13,281 → 14,462. The measured automatic
agreement rate moved with it, from 87.2 % (1,281 of 1,467) to **90.1 % (1,990 of
2,209)**, because the larger stratum draws in more rows whose document has a text layer.
A9's 87.2 % is superseded; the document now reads the rate off the worklist rather than
restating it.

Note that **6.9 % was a share of a subset**: 1,343 of 37,768 `ags × household_size` rows
are flagged, which is 3.6 % of all rows and 6.8 % of the rows that have an eligible
cross-border neighbour at all. `has_cross_border_neighbour` is `False` for 48 % of rows.

**A21 is closed by filling, not dropping.** `task_harmonise` now reads
`bld/jobcenter_kreis_crosswalk.parquet` and `build_geography` fills `jobcenter_id` from
the Kreis. No cycle exists: that crosswalk depends only on the BA extracts and the
committed `data/kdu_gemeinden.csv`. Berlin stays null — twelve Bezirks-Jobcenter, one
Gemeinde — and `docs/data_dictionary_source.json` says so.

### Three logged figures do not reproduce against the built artefacts

All three are consequences of A12's own tolerance correction and of rebuilding artefacts
that a green `pytask` had left stale (A23). The artefacts are right; the logged numbers
are the stale ones.

- **A12/A22's `linked_union` counts.** A12 quotes an 18.79 % share and A22 a 1,752 /
  1,137 / 615 / 66 split at h=1. Those were measured under the **old**
  `WOGG_SAFETY_MARKUP_TOLERANCE` of 0.005, which A12 itself corrected to 5e-4. At the
  corrected tolerance, on the 9,323 comparable Gemeinden at h=1: `linked_union` is
  **1,276** (13.7 %), `exact_ratio` is **1,203**, **1,015** are in both, **261** are in
  `linked_union` only, and **188** are in `exact_ratio` only. A22's *qualitative* claim
  is unaffected and is the one that matters: `linked_union` is **broader than, and not a
  superset of, `exact_ratio`**. That wording is now used in Table 2's note, in the
  §13/§14 figure texts, and in `within_mietenstufe.py`.
- **A19's border-jump table.** Excluding `linked_union` at h=4 the artefacts give
  **3,555** between-Kreis pairs with a median step of **81 €** and **38.1 %** above
  100 €, and **825** between-Bundesland pairs with **97 €** and **46.8 %**; the tight
  comparison group retains **685** pairs at a median of **71 €** with **29.9 %** above
  100 €. A19 logs 3,121 / 80 € / 37.3 %, 795 / 97 € / 46.4 % and 593 / 75 € / 32 %. The
  finding is unchanged in every respect, including that the tight comparison group does
  not close the gap.
- **A20's `excluding_linked_union` coefficient.** β on `log(K/W)` is **−0.0332**
  (0.0066), not the logged −0.0307 (0.0065), for the same reason. The pooled
  −0.0361 (0.0066), the `exact_ratio` +0.3615 (0.6098) and the whole conditional-versus-
  unconditional caveat reproduce exactly.

### Manifest coverage, and why the §23 audit computes its own verdict

`docs/results.md` now carries a **§23 Definition of Done audit**, and criterion 11's
verdict is computed rather than asserted: it compares `bld/results_manifest.csv` against
the files under `bld/tables` and `bld/figures` and reports *Partially met*, naming the
gap, whenever one is unregistered. It read *Partially met — 15 unregistered* until the
seven P1.1 tables, the six P1.2 tables, `ba_validation_interpretation.md` and
`table5_external_validation.md` were registered. **72 of 72 outputs now carry a manifest
row**, and all twelve criteria are met.

P1.2 had deliberately left its tables out, on the ground that they are analysis inputs
rather than presented output. That ground no longer holds: `docs/results.md` reads its
§14 numbers straight out of them.

`bld/household_profile_interpretation.md` moved to `bld/tables/` beside its three
siblings and is registered by `task_household_profile`.

### The manifest is now a declared dependency of the results document

`task_workshop_deck` takes `bld/results_manifest.csv` in its signature, so a task that
registers a new output makes the document stale instead of leaving a stale count behind
a green `pytask` (A23). No task declares the manifest a product — every task appends its
own rows — so pytask cannot order this one after them; on a build from an empty `bld/`
the §23 count converges on the second run, and the docstring says so.

## D15 — The primary Wohngeld benchmark carries the BSG Sicherheitszuschlag

**Supersedes D6's choice of primary.** The benchmark every headline number, map and
Table 2 row is read against is

```
W        = wogg_base_cap × 1.10          (primary, all headline numbers)
W_base   = wogg_base_cap                 (robustness: what a model substituting the
                                          bare Anlage 1 table would use)
W_klima  = wogg_base_cap + wogg_climate_component   (robustness, D6/§18)
```

`wogg_heating_relief` still enters none of the three.

**Reason.** D6 chose the bare Anlage 1 table on the ground that this is what a
tax-transfer model actually substitutes. That is a claim about current practice, not
about the correct fallback. A model with no local KdU parameter is, by construction, in
exactly the situation § 22 SGB II case law addresses: no schlüssiges Konzept is
available. The fallback the BSG prescribes there (B 4 AS 16/11 R; B 4 AS 87/12 R) is the
§ 12 WoGG table **plus a 10 % Sicherheitszuschlag**. Benchmarking against the bare table
therefore measures the gap against a value that is legally the wrong default, and
attributes to "proxy error" a 10 % markup that a correctly specified model would already
carry.

**What the change does to the numbers.** The level component of the proxy error is
almost entirely the Sicherheitszuschlag. On the main sample the unweighted median gap
falls from +45.5 € to **+0.9 €** at household size 1, and from +69.0 € to **+0.4 €** at
size 4. The gap turns negative for 35.7 % of Gemeinden at h=1 rather than 19.9 %.

**What it does not change.** The standard deviation of the log error is *identical*
(14.19 at h=1), because scaling `W` by a constant shifts every log gap alike and cannot
touch dispersion. The Familien-Tilt is unchanged *exactly*, since it differences log
gaps across household sizes and the constant cancels. The within-Mietenstufe spread of
the cap itself is a property of `K` alone and is untouched. The mean absolute error
stays large: 46 €/month at h=1, 73 €/month at h=4.

The paper's claim therefore moves from "the Wohngeld proxy is biased upward" to **"the
Wohngeld proxy is approximately unbiased at the median and wrong Gemeinde by
Gemeinde"** — a stronger claim, because a level bias is repairable with one constant and
dispersion is not.

**The circularity this creates, and how it is handled.** The 1,203 Gemeinden that
adopted the WoGG table plus the 10 % markup now sit at *exactly zero* error by
construction: the exact-zero mass rises from 1.6 % to 10.3 % of the sample. D7's
with/without reporting is therefore load-bearing rather than a robustness courtesy.
Excluding the `linked_union` group the median is +9.4 € at h=1 and +8.4 € at h=4 — a
small residual, not a headline.

**Implementation.** `wogg_primary_cap` is built in `wohngeld.build_wogg_benchmark` and
flows through the analysis sample, so every module reads one column.
`proxy_error.PRIMARY_BENCHMARK` names the variant that headline selections filter on;
promoting a different variant is a one-line change. All three variants are always
computed, so `benchmark_variant == "base"` still recovers every pre-D15 number.

**A bug this exposed.** `at_safety_markup` was computed from `cap_ratio`, the ratio
against whichever benchmark the row used. Under `base_plus_climate` that already meant
the flag was testing `K/(W+Klima)` against 1.10 rather than `K/W`, so the flag carried a
different meaning in each variant. It never reached a headline because every table
filtered to the base variant first. It is now computed from `kdu_bkc_cap / wogg_base_cap`
and is variant-independent by construction, with a parametrised test over every variant.

## D16 — Every headline is reported pooled and with the WoGG-linked group set aside

Neither linkage group is primary. Every headline number carries both readings side by
side, because under D15 the two answer different questions and the difference between
them is itself a finding.

**Why the choice cannot be made once for all numbers.** D7 kept the WoGG-linked
Gemeinden in the sample on the ground that "a model substituting `W` does
mismeasure by +10 % there". D15 inverts that: those Gemeinden now sit at *exactly zero*
error, mean absolute 0.0 € and standard deviation 0.1. So the group flipped from
carrying the largest systematic error in the sample to carrying none, and the inclusion
argument flipped with it.

- Pooled answers **how wrong a model is across Germany**. The linked Kreise are
  genuinely predicted correctly, and excluding them would overstate national simulation
  error. That ~13 % of Gemeinden track the WoGG formula is a real empirical fact.
- Excluding answers **how much genuine local deviation from the WoGG formula exists**.
  There the linked Kreise contribute nothing by construction and dilute every dispersion
  measure by roughly 13–14 %.

Both are legitimate; the paper needs both, so both are printed.

**The one inference that remains forbidden**, sharpened from D7: the pooled figure may
never be offered as evidence that the proxy performs well. The group is detected partly
*by* `K/W ≈ 1.10`, so their zero error is evidence about their adoption of the rule, not
about the proxy's accuracy anywhere else.

**What this changed in the task graph.**

- Beitrag 1 gained a paired paragraph carrying the median, the mean absolute gap and the
  share beyond 100 € for both exclusions, not only the median.
- The border-jump section previously reported *only* the excluding reading; it now
  prints the pooled counterpart beside it. Pooling barely moves the Kreis-boundary step
  (81 € either way) but pulls the §13.4 tight comparison group from 71 € to 63 €,
  because matching on Mietenstufe selects linked pairs disproportionately. The headline
  keeps the excluding reading there, and now says why.
- `needs_level` gained a `wogg_linked_flag` breakdown, which it did not have. The
  needs-level shift is +1 € and +0 € pooled against +9 € and +8 € excluding.
- Beiträge 2, 3 and 4 already carried an excluding figure and were left alone.

Headline pairs at household size 1, unweighted euro gap: median +0.9 € pooled against
+15.7 € excluding `exact_ratio` and +9.4 € excluding `linked_union`; mean absolute
46.4 € against 53.3 € and 53.0 €; share beyond 100 € 13.0 % against 14.9 % and 15.0 %.
