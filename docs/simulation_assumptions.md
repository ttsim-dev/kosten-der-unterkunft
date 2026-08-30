# Simulation assumptions — P0.6 and P0.7

The central assumptions file §12.5 requires. Every simplification the §11
administrative need measure and the §12 Standardfall microsimulation rest on is
recorded here. Where an assumption is contestable, the alternative is named so a
reader can see what was not done.

Modules: `src/kdu/simulation/kdu_cap.py`, `needs_level.py`, `microsim.py`,
`task_needs_level.py`, `task_microsim.py`.
Model: GETTSIM 1.3.0 on the ttsim backend, Rechtsstand `2026-08-31` (D2).

______________________________________________________________________

## 1. The legal parameters, and the one that had to be checked by hand

`docs/gettsim_audit.md` §4 confirms that 2026 is genuinely parameterised in
GETTSIM: Kindergeld, Kinderzuschlag, Einkommensteuertarif, Lohnsteuer,
Solidaritätszuschlag and the Sozialversicherungs-Bemessungsgrenzen all carry
explicit `2026-01-01` entries, Bürgergeld and Wohngeld carry forward correctly.

**Regelbedarfsstufe 1 = 563 € was the open item (A7), and it is confirmed.**
GETTSIM carries it forward from its 2024 entry rather than from a dated 2026 one.
Verified against the Verordnung zur Fortschreibung der Regelbedarfsstufen for
2026: the arithmetic Fortschreibung for RBS 1 produced 557 €, below the 563 € in
force, and the Besitzstandsschutz of § 28a Abs. 5 SGB XII forbids a reduction, so
2026 is a Nullrunde and RBS 1 stays at **563 €** — the same figure as 2024 and
2025. The value GETTSIM uses is therefore correct for the Rechtsstand, and
`tests/test_needs_level.py` asserts it.

The remaining Regelbedarfsstufen the model households draw, all read back out of
GETTSIM and asserted in the tests:

| Member | Regelbedarfsstufe | € per month |
|---|---|---|
| Single adult | RBS 1 | 563.00 |
| Adult in a couple | RBS 2 | 506.00 |
| Child aged 8 | RBS 5 + Kindersofortzuschlag | 415.00 |
| Child aged 14 | RBS 4 + Kindersofortzuschlag | 496.00 |

The child figures **include the Kindersofortzuschlag of 25 € per month**, because
GETTSIM adds it to the Regelsatz. It is a Zuschlag rather than a Regelbedarf in
the strict sense; the P0.6 measure carries it, and this is the only place where
`R` is wider than the Regelbedarfe alone.

`M` is the § 21 Abs. 3 SGB II Alleinerziehenden-Mehrbedarf, 12 % of RBS 1 =
**67.56 €** for the single parent with one child, and zero for the other three
households.

Mindestlohn 2026 = **13.90 €/h** (Fünfte Mindestlohnanpassungsverordnung, BGBl.
2025 I Nr. 268), so §12.6's hours equivalent is `ΔH = Δy* / (4.33 × 13.90) =
Δy* / 60.19`.

## 2. GETTSIM's own housing cap is replaced, not reconfigured

GETTSIM 1.3 applies a national rule-of-thumb Angemessenheitsgrenze of its own:

```
kosten_der_unterkunft_m = berechtigte_wohnfläche × min((bkm + heizkosten) / wohnfläche, 10 €/m²)
```

with `berechtigte_wohnfläche = 45 m² + 15 m² per further person`. Left in place it
would have destroyed the study twice over: it binds at 450 € for a single person,
which is below most of the sample's `K` *and* below the Wohngeld Höchstbetrag of
five of the seven Mietenstufen, so both scenarios would truncate to the same value
and `ΔT` would have measured as zero across most of Germany — a false null that
looks like a finding. It is also a **warm** cap, which violates §12.3's requirement
that heating be held constant.

It is neutralised by supplying `bürgergeld__kosten_der_unterkunft_m` as an input
column. `ttsim` then treats it as an override and prunes
`anerkannte_warmmiete_je_qm_m`, `berechtigte_wohnfläche` and
`mietobergrenze_pro_qm_m` out of the DAG. The recognised amount is computed in
this repository by `kdu_cap.unterkunftskosten_m`, so a future GETTSIM release is a
maintenance question rather than a threat to the finding (D9).

**The override column is per person, not per household.** Passing the household
total would inflate the Bedarf by a factor of household size — invisible for the
single adult, wrong for the other three. `kdu_cap.kopfteil_m` does the split
(Kopfteilprinzip, BSG B 14/7b AS 58/06 R) and is separately tested.

The exact contrast the audit pins down is asserted end to end in
`tests/test_microsim.py`: with `K = 520`, `W = 456`, `m = 520` and 90 € heating,
`T^K(0) = 1173 €`, `T^W(0) = 1109 €`, so `ΔT(0) = 64 € = K − W`.

## 3. Two inputs GETTSIM does not derive, and silently defaults to zero

`alter` and `alter_monate` are ordinary input columns. They are **not** derived
from `geburtsjahr` and `geburtsmonat`, and they are **not** listed in the
`input_data_dtypes` template for the target set this project uses. Leaving them at
their zero default makes every adult a newborn: Regelbedarfsstufen come out wrong,
`familie__volljährig` is `False` for a 35-year-old, and the 70-year-old is paid
Bürgergeld instead of Grundsicherung im Alter. `microsim._demographics` sets both
explicitly, and the household composition tests would fail if it stopped.

## 4. The four §11.1 Modellhaushalte as implemented

Ages, composition and the Alleinerziehenden flag come from
`config.MODEL_HOUSEHOLDS`. Everything below is an assumption made here.

| Assumption | Value | Note |
|---|---|---|
| Adult age in households 2 and 3 | 35 | §11.1 fixes only household 1; matching it makes differences come from composition alone |
| Karenzzeit | elapsed for all (D11) | `bürgergeld__bezug_im_vorjahr = True` |
| Vermögen | 0 € | so the Vermögensprüfung never binds |
| Earnings within a couple | one earner | § 11b Erwerbstätigenfreibetrag is claimed once |
| Lohnsteuerklasse | I single, II Alleinerziehend, IV/IV couple | irrelevant to the results: disposable income uses the Veranlagung, not the withholding |
| Wohnfläche | 45 m² + 15 m² per further person | only reaches rules the override prunes away |
| Maintenance for the single parent's child | none paid; Unterhaltsvorschuss received | GETTSIM grants it automatically (299 € at age 8 in 2026) and counts it as income |
| Pensioner's pension | gesetzliche Altersrente, retirement at the Regelaltersgrenze, 45 Pflichtbeitragsjahre | Zugangsfaktor exactly 1.0, no Grundrentenzuschlag |
| Disability, Erwerbsminderung, Elterngeld, ALG I | none | no §11.1 household is defined on them |

The pensioner's §12.4 income grid is a grid over the **gross monthly pension**.
GETTSIM takes Entgeltpunkte, and the pension is linear in them at a fixed
Zugangsfaktor, so `microsim._gross_pension_per_entgeltpunkt_m` inverts the
relation with one GETTSIM call and the reported grid value is exact.

## 5. The rent assumption (§12.2)

- **Variante 1, the headline.** `m = max(K, W)`. This is a **construction
  scenario** that isolates the maximum mechanical difference between the two
  parameters. It is **not** a typical market rent and must never be described as
  one. At that rent both caps bind, so the recognised amounts are exactly `K` and
  `W`.
- **Variante 2.** A grid of `m` from 50 % to 130 % of `max(K, W)` in 10 % steps.
  Below roughly 80 % neither cap binds and the two parameters give identical
  results; the difference emerges only once the rent reaches the lower cap.
- **Variante 3, Bestandsmieten.** Not implemented. It waits on the Zensus module.
  `task_microsim.bestandsmiete_hook` documents where it plugs in: replace the rent
  vector and nothing else changes, because the whole contrast is carried by
  `kdu_cap.recognised_bruttokaltmiete_m`. Its label is "Bestandsmietenszenario".

## 6. Heating (§12.3)

Heating is **identical between the two scenarios**, so it cancels from every K−W
difference and the contrast stays a pure Bruttokaltmiete effect.

The central figure is the nationwide average **recognised** Heizkosten per
Bedarfsgemeinschaft from the BA Wohnkosten data, by household size. The BA
publishes no national row, so the mean is taken over the 400 Kreise and weighted
by the stock of Bedarfsgemeinschaften with recognised KdU — never an unweighted
mean over Kreise, which would over-weight small ones.

| Household size | Recognised Heizkosten, € per month |
|---|---|
| 1 | 67.78 |
| 2 | 99.93 |
| 3 | 119.05 |
| 4 | 134.07 |
| 5 | 148.54 |

Reference month **2026-04**, the latest the BA had published at the
Analysestichtag; D2 admits the latest month ≤ 2026-08.

Sensitivity at **75 % and 125 %** of these values, as §12.3 prescribes. Because
heating is held constant across scenarios it cannot move `ΔT(0)` at all; it moves
`Δy*` only through the shape of the income-offsetting schedule, and the measured
movement is small.

Two approximations to state: the BA figures are SGB II Bedarfsgemeinschaften, so
applying them to the SGB XII pensioner household is an approximation; and they are
*recognised* rather than *actual* Heizkosten, which is the right concept for a
Bedarf but is itself already the product of an administrative appropriateness
test.

## 7. The income grid and the exit threshold (§12.4, §12.6, D10)

- Grid from 0 € in 25 € steps, extended twelve grid points beyond the last exit
  threshold so §12.4's stopping rule is satisfied exactly, with §12.4's technical
  ceiling of 8,000 € per month.
- `y*` is located by **bisection to one euro** (D10), not read off the grid, so
  `Δy*` and `ΔH` carry no grid artefact.
- Monotonicity of the Anspruch in income is **asserted, not assumed**:
  `budget_curve` runs `kdu_cap.fail_if_not_weakly_decreasing` over every cell and
  scenario of a 65-point ladder before bisection begins, and the bisection refuses
  to run on a cell that still holds a claim at the ceiling.
- Every simulated result is asserted `np.isfinite` (A7). GETTSIM raises a benign
  `RuntimeWarning: invalid value encountered in divide` for a household with no
  income at all, from a `0/0` inside `anteil_steuerfälliger_einnahmen`. It does
  not propagate. The assertion is the guard; the warning is not filtered.
- Rounding is applied **centrally**: `kdu_cap.round_currency_m` is the only place
  a euro amount is rounded, and `round_ratio` the only place a share or an hours
  figure is. §12.8 test 8 asserts that the simulation output equals its own
  centrally rounded value.

## 8. The simulation grid (D10)

GETTSIM never sees a Gemeinde. The 9,442 main-sample Gemeinden collapse to
**1,099 distinct (K-vector, Mietenstufe) cells**, and per household size to 782
(h = 1), 841 (h = 2) and 908 (h = 4) distinct (cap, Mietenstufe) pairs, exactly as
D10 states. Results are left-joined back onto every Gemeinde afterwards.

`simulation_cells` drops Gemeinden with no statutory Mietenstufe, because A2
records that no Wohngeld benchmark exists for them under the statute. **The
simulation therefore runs on 9,323 of the 9,442 Gemeinden**, and both numbers are
reported wherever coverage is.

## 9. Full transfer integration (§12.7) and its one structural limitation

GETTSIM applies the Vorrangprüfung of § 12a SGB II through
`vorrangprüfungen__wohngeld_kinderzuschlag_vorrangig_oder_günstiger`, so SGB II
and Wohngeld are never paid at the same time. `bürgergeld__anspruchshöhe_m` is the
claim before the Vorrang and is what `ΔT` and `y*` are defined on;
`bürgergeld__betrag_m` is the claim after it and is what the regime boundaries
reported in `microsim_cells.parquet` are defined on.

**The Vorrangprüfung assumes the wohngeldrechtlicher Teilhaushalt coincides with
the Bedarfsgemeinschaft** (its own docstring). All four §11.1 households satisfy
that as specified, but the assumption is a real restriction on how far the §12.7
results generalise, and it matters most for the couple with two children, where
Kinderzuschlag and Wohngeld interact.

## 10. The Karenzzeit limitation (D11), stated once and plainly

All four Modellhaushalte are declared beyond month 12 of Bürgergeld receipt, so
the Angemessenheitsgrenze is in force and the K/W contrast is well defined.

**Every Δ reported by this module is conditional on the cap being in force. Under
§ 22 Abs. 1 S. 2–3 SGB II the Karenzzeit suspends it for the first twelve months,
during which actual Unterkunftskosten are recognised in full, so the proxy error
is identically zero for a Bedarfsgemeinschaft inside it.**

## 11. The WoGG-linked group (D7)

Every table in this module is reported three ways — all Gemeinden, excluding the
flagged group, and the flagged group alone. The flag is `wogg_linked_flag`, which
A12 names `linked_union`: the union of the notes-regex and `K/W` detectors of D7,
1,752 of the 9,323 comparable Gemeinden (18.8 %). Every table states which group
it uses in its own note.

`linked_union` is not `exact_ratio`, the 1,203 Gemeinden whose `K/W` is 1.100
within 5e-4 and for whom `K/W = 1.10` holds by construction. The two overlap
without either containing the other. It is `exact_ratio` whose `Δ` distribution
is compressed to what a definitional identity looks like; `linked_union` is the
right group when asking which Kreise lean on the WoGG table at all. No pooled
median may be presented as an empirical regularity under either.

## 12. Language (D13, §20)

Figure labels, table headers and result text are English. German is kept only for
terms with no faithful translation. §20's forbidden terms apply in translation
too: nothing here is called "generosity", "restrictiveness", a "causal effect", an
"actual KdU payment", or a "full Existenzminimum". The P0.6 measure carries
exactly one name — *administrative Bruttokaltbedarf before income offsetting* —
because heating is not in it.
