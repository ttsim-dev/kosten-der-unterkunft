# GETTSIM 1.3 audit for P0.7

The wave-1 audit D9 makes a prerequisite for everything under §12. Every claim below
was read out of the installed source at
`.pixi/envs/default/lib/python3.14/site-packages/gettsim/` or measured by
`scripts/gettsim_spike.py`, which reproduces all of it in one run.

Installed: `gettsim 1.3.0` (conda-forge, published 2026-08-20) on the `ttsim` backend.
Added to `pyproject.toml` as `gettsim = ">=1.3,<2"`; `pixi.lock` regenerated in the
same change.

**Recommendation: GO** for D9 and D10, with the two changes recorded under
"Required changes" below. Both are already implemented.

______________________________________________________________________

## 1. How GETTSIM represents Unterkunftskosten

Housing enters through four household-level input columns in the `wohnen` namespace
(`germany/wohnen/inputs.py`):

| Column | Unit | Level |
|---|---|---|
| `wohnen__bruttokaltmiete_m_hh` | euro per month | household |
| `wohnen__heizkosten_m_hh` | euro per month | household |
| `wohnen__wohnfläche_hh` | square metres | household |
| `wohnen__bewohnt_eigentum_hh` | bool | household |

For the Rechtsstand 2026 the consuming module is `bürgergeld` (`arbeitslosengeld_2` is
end-dated 2022-12-31). It turns those into person-level columns by the Kopfteilprinzip
(BSG B 14/7b AS 58/06 R) and then applies its own appropriateness test:

```
bruttokaltmiete_m            = wohnen__bruttokaltmiete_m_hh / anzahl_personen_hh
heizkosten_m                 = wohnen__heizkosten_m_hh      / anzahl_personen_hh
wohnfläche                   = wohnen__wohnfläche_hh        / anzahl_personen_hh
anerkannte_warmmiete_je_qm_m = min((bruttokaltmiete_m + heizkosten_m) / wohnfläche,
                                   mietobergrenze_pro_qm_m)
berechtigte_wohnfläche       = min(wohnfläche, eligible_size / anzahl_personen_hh)
kosten_der_unterkunft_m      = berechtigte_wohnfläche * anerkannte_warmmiete_je_qm_m
regelbedarf_m                = regelsatz_m + kosten_der_unterkunft_m
```

The Bedarfsgemeinschaft structure is expressed through `hh_id`, `bg_id`, `fg_id`,
`eg_id`, `wthh_id` (all derived unless supplied) plus
`bürgergeld__p_id_einstandspartner` and the `familie__p_id_*` foreign keys. All amounts
are euro per month.

`grundsicherung__im_alter__bedarf_m` is built on `bürgergeld__regelbedarf_m`, so the
§11.1 Rentnerhaushalt runs through exactly the same housing chain — one intervention
point covers all four model households.

## 2. Does GETTSIM apply its own cap on Wohnkosten? — Yes. This is the finding.

**Yes, and it is not Wohngeld-derived.** GETTSIM applies a national rule-of-thumb
Angemessenheitsgrenze:

- `bürgergeld__mietobergrenze_pro_qm_m = 10 EUR/m²/month`, unchanged since 2023-01-01,
- `berechtigte_wohnfläche_miete = 45 m² + 15 m² per further person`,

both from `germany/bürgergeld/kosten_der_unterkunft.yaml`. Its own description concedes
the point: *"Diese Grenze ist nicht konkret im Gesetz festgehalten … Dies ist nur eine
Approximation. Die regionalen Parameter sind unbekannt, siehe Issue
[gettsim#782](https://github.com/ttsim-dev/gettsim/issues/782)."* That open issue is
precisely the gap this project fills.

Two properties make it fatal if left in place:

1. **It binds low.** For a single person the recognised amount saturates at
   45 m² × 10 €/m² = **450 €**. Measured, at 90 € Heizkosten:

   | actual Bruttokaltmiete | GETTSIM `kosten_der_unterkunft_m` |
   |---|---|
   | 200 | 290 |
   | 300 | 390 |
   | 360 | 450 |
   | 400 | 450 |
   | 500 | 450 |
   | 700 | 450 |

   The h=1 sample's K values run well above 450 € warm in most Kreise, and 5 of the 7
   Wohngeld Mietenstufen already put W alone above 450 € before heating. Both scenarios
   would be truncated to the same 450 €, so **ΔT would be measured as zero across most
   of the sample** — a false null, and exactly the contamination D9 warns about.

2. **It is a warm cap.** It caps `bruttokaltmiete + heizkosten` jointly. §12.3 requires
   heating held constant so that every K−W difference is a pure Bruttokaltmiete effect.
   Under GETTSIM's rule heating competes with rent for the same ceiling, so the heating
   sensitivity of §12.3 (±25 %) would move the *rent* result. That alone disqualifies
   unmodified GETTSIM.

### How it is neutralised

Supply `bürgergeld__kosten_der_unterkunft_m` as an input column. `ttsim` treats a
supplied column as an override of the policy function of the same name and prunes the
now-unreachable nodes — `anerkannte_warmmiete_je_qm_m`, `berechtigte_wohnfläche`,
`mietobergrenze_pro_qm_m` all drop out of the DAG. Verified:

| actual Bruttokaltmiete | handed over | GETTSIM `kosten_der_unterkunft_m` | `anspruchshöhe_m` |
|---|---|---|---|
| 200 | 290 | 290 | 853 |
| 400 | 490 | 490 | 1053 |
| 700 | 790 | 790 | 1353 |
| 1500 | 1590 | 1590 | 2153 |

Exact pass-through, linear, no saturation. The K/W contrast then comes out right by
construction: with K = 520, W = 456, m = max(K, W) = 520,
T^K(0) − T^W(0) = 1173 − 1109 = **64 = K − W**.

`src/kdu/simulation/kdu_cap.py` owns that `min(m, cap)` and exports the override column
name as `GETTSIM_UNTERKUNFTSKOSTEN_COLUMN`, so the coupling to GETTSIM is one
string.

### The override column is per-person

`bürgergeld__kosten_der_unterkunft_m` is person-level. Passing the household total to
each member inflates the Bedarf by a factor of household size — invisible for §11.1
household 1, wrong for the other three. `kdu_cap.kopfteil_m()` does the split and is
tested. Keep supplying `wohnen__bruttokaltmiete_m_hh` and `wohnen__heizkosten_m_hh`
anyway: the Wohngeld branch needs them, and §12.6's `Y^posthousing` needs the actual
Bruttowarmmiete.

## 3. The § 22 Abs. 1 Karenzzeit — modelled, and D11 is expressible

`bürgergeld__bezug_im_vorjahr` (bool, person level) is the switch. Contrary to what its
docstring suggests, the branch is:

- `False` (no receipt in the last 12 months, i.e. **inside** the Karenzzeit) ⟹
  `bruttokaltmiete_m + heizkosten_m` recognised in full,
- `True` (**past** the Karenzzeit) ⟹ the appropriateness cap applies.

Measured at m = 700, Heizkosten = 90: `False` → 790, `True` → 450.

**D11 is therefore set with `bürgergeld__bezug_im_vorjahr = True` on every model
household.** Note that GETTSIM does not implement the § 22 Abs. 1 S. 3 carve-out that
heating is appropriateness-tested even inside the Karenzzeit — it exempts the warm total
— but that is irrelevant to us, because under D11 no household is inside the
Karenzzeit and the override bypasses the branch entirely.

## 4. Rechtsstand 2026 coverage

2026 is genuinely parameterised. **D2 does not need to change.** Per-domain, taking the
latest dated entry in each YAML:

| §12.5 / §12.7 requirement | Status for 2026 |
|---|---|
| Regelbedarfe | Carried forward from the 2024-01-01 entry, RBS 1 = 563 €. Correct: the Fortschreibung was a Nullrunde for both 2025 and 2026. **Verify against the RBSFV 2026 before publication** — GETTSIM has no explicit 2026 entry, so this is the one number GETTSIM does not itself date-stamp. |
| Mehrbedarfe | § 21 SGB II Alleinerziehenden-Mehrbedarf, Mehrbedarf Schwerbehinderung G. Present. |
| Unterkunft und Heizung | Present, but see §2 — we replace it. |
| Erwerbstätigenfreibeträge | `bürgergeld/freibeträge.yaml`, Bürgergeld-Fassung of 2023-07-01, still in force. |
| Kindergeld | `kindergeld.yaml` has a **2026-01-01** entry. |
| Sozialversicherung | Beitragsbemessungsgrenzen KV and RV, KV-Beitragssatz, Entgeltpunkte all carry **2026-01-01** entries; Rentenformel **2026-07-01**. |
| Lohnsteuer / Einkommensteuer | `einkommensteuertarif.yaml`, `lohnsteuer/einkommensgrenzwerte.yaml`, `lohnsteuer/vorsorge.yaml`, `kinderfreibetrag.yaml`, `solidaritätszuschlag.yaml` all **2026-01-01**. |
| Wohngeld | `wohngeld/miete.yaml` and `wohngeld/wohngeld.yaml` last dated 2025-01-01. Correct for 2026: Anlage 1 is fortgeschrieben biennially, next 2027-01-01. |
| Kinderzuschlag | `kinderzuschlag.yaml` **2026-01-01**. |
| Vorrangprüfung §12.7 | `vorrangprüfungen__wohngeld_kinderzuschlag_vorrangig_oder_günstiger`, active from 2023-01-01. `bürgergeld__betrag_m` is zero when it fires; `bürgergeld__anspruchshöhe_m` is the pre-Vorrang claim. Both are targets, so §12.7's regime switch is directly observable. |

**Independent cross-validation of D6.** GETTSIM's `raw_max_miete_m_hh` for 2025-01-01,
one person, Mietenstufen I–VII, is 361 / 408 / 456 / 511 / 562 / 615 / 677. That is
exactly the median of `wogg_hoechstbetrag_eur_1p` by `wogv_mietstufe` in
`data/kdu_gemeinden.csv`. D6's claim that the CSV holds base-only 2026 values is
confirmed from a second source, and the "in force 1.1.2025" wording the codebook is
told to correct is in fact the correct *Fassung* date — the values are simultaneously
the 2025 and the 2026 values.

Caveat on the Vorrangprüfung: its own docstring says it assumes WTHH = BG and "will not
work in more complex situations", and carries an open TODO for SGB XII households
([gettsim#1165](https://github.com/ttsim-dev/gettsim/issues/1165)). §12.7 must state
this; §11.1 household 4 (the 70-year-old) is the one where it matters.

## 5. Mindestlohn for §12.6

`sozialversicherung/mindestlohn.yaml`:

- **2026-01-01: 13.90 €/hour** (Fünfte Mindestlohnanpassungsverordnung, BGBl. 2025 I
  Nr. 268),
- 2027-01-01: 14.60 €/hour.

The Analysestichtag 2026-08-31 falls in the 13.90 € band, so §12.6's
ΔH = Δy* / (4.33 × 13.90) = Δy* / 60.19 hours per week.

## 6. Vectorisation and measured timings

**Fully vectorised.** One `main()` call takes a `DataFrame` of arbitrarily many
households — one row per person, distinct `p_id` and `hh_id` — and evaluates the whole
DAG on numpy arrays. It is not one household at a time.

Measured on this machine (macOS arm64, numpy backend), targets
`bürgergeld__anspruchshöhe_m`, `bürgergeld__betrag_m`, `wohngeld__betrag_m_wthh`,
`kinderzuschlag__betrag_m_bg`:

| households per call | wall time | per household |
|---|---|---|
| 1 | 2.08 s | 2081 ms |
| 100 | 1.87 s | 18.7 ms |
| 1,099 | 2.00 s | 1.8 ms |
| 2,198 | 1.87 s | 0.85 ms |
| 10,990 | 2.04 s | 0.18 ms |

The cost is a fixed ~2 s per call, flat in batch size to at least 22,000
rows. `include_fail_nodes=False, include_warn_nodes=False` brings it to ~1.2 s; reusing
a prebuilt `tt_function` does **not** reduce it; the overhead is in DAG assembly and input
validation, not in evaluation.

Consequence for D10: put all 1,099 cells × both scenarios in **one** call. A bisection
to €1 over the ~2,100 € span needs ~12 evaluations, so one model household costs
~12 × 2 s ≈ 25 s and all four ≈ 100 s. The ≤25 € budget grid of §12.6 is one more call.
Simulating per Gemeinde would also be affordable, but D10's cell design stands — it is
cheaper and it is the honest unit.

Monotonicity, which D10's bisection requires, was checked on a 104-point ladder from 0
to 2,575 € gross for household 1: `bürgergeld__anspruchshöhe_m` is weakly decreasing
throughout, y* = 2,100 € at a 25 € grid. `kdu_cap.fail_if_not_weakly_decreasing()`
makes that check mandatory rather than assumed, as D10 demands.

## 7. Required changes

Neither changes a decision; both are already implemented.

1. **GETTSIM's housing rule is replaced, not configured.** Every P0.7 run supplies
   `bürgergeld__kosten_der_unterkunft_m`. Raising `mietobergrenze_pro_qm_m` instead
   would also work but leaves the warm-cap coupling of §12.3 in place and depends on
   `wohnfläche` staying under the eligible size, so it is the worse option and is not
   used.
1. **Household amounts are split by Kopfteil before they reach GETTSIM**
   (`kdu_cap.kopfteil_m`).

## 8. Open risks

- **Regelbedarf 2026 is carried forward, not dated.** The single number to verify by
  hand against the RBSFV 2026 (§10). Everything else in §12.5 carries an explicit
  2026-01-01 entry.
- **The Vorrangprüfung assumes WTHH = BG.** Fine for the §11.1 households as specified;
  must be stated as a limitation in §12.7, and revisited if household 4 is taken
  seriously.
- **A benign NaN inside GETTSIM.** `anteil_steuerfälliger_einnahmen` divides by total
  Einnahmen and produces `0/0` for a household with no income at all, raising
  `RuntimeWarning: invalid value encountered in divide`. It does not propagate: every
  `anspruchshöhe_m`, `betrag_m` and `kosten_der_unterkunft_m` observed was finite. Worth
  a `np.isfinite` assertion on results rather than a filtered warning.
- **`gettsim` pins `ttsim-backend >= 1.2`.** The `min(m, cap)` logic living in this repo
  (D9) is what makes a future GETTSIM release a maintenance question rather than a
  threat to the finding.

## 9. If it had been NO-GO

Recording the counterfactual, because the spike existed to price it. The fallback of
§12.5 is a bespoke Standardfallrechner. What GETTSIM supplies without further
implementation, and would
otherwise have to be written and validated against BMAS reference cases:

- Regelbedarfsstufen 1–6 with the age brackets, Kindersofortzuschlag, the § 21 Abs. 3
  Alleinerziehenden-Mehrbedarf with its three-way maximum and its 60 % cap;
- § 11b Erwerbstätigenfreibeträge with the Bürgergeld bracket structure;
- Kindergeld, Kinderzuschlag with its own income test, Unterhaltsvorschuss;
- the full Wohngeld formula — Anlage 1 Höchstbeträge by Mietenstufe, Klimakomponente,
  Heizkostenkomponente, Mindestmiete, Mindesteinkommen, the Anlage 2 coefficients;
- Sozialversicherungsbeiträge with Bemessungsgrenzen, Minijob and Midijob;
- Lohn- and Einkommensteuer including Soli;
- the Bedarfsanteilsmethode and the vertikal-horizontale income allocation across a
  Bedarfsgemeinschaft, plus the Vorrangprüfung.

That is a multi-week build with a large validation surface, and its own error bar would
be of the same order as the effect being measured. Avoiding it is the substantive value
of this GO.
