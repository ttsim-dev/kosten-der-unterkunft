# R1 — The Fallback Is Not a Safe Default

**59.9 %** of Gemeinden set caps *below* the statutory fallback.

Cap difference, single adult, € per month — deciles:

`−94.4 · −61.9 · −36.5 · −21.1 · −20.2 · 0.0 · +10.3 · +32.6 · +71.8`

<img src="../../bld/kdu_vs_wohngeld/cap_comparison_distribution.png" style="max-height: 290px; margin: 1rem auto 0;" />

**A default that misses the median Gemeinde by −20 € is wrong by −94 € at the first decile and +72 € at the ninth.**

<!-- The benchmark is not a floor: more than a third of Gemeinden are stricter than the Bundessozialgericht fallback. Read the two ends of the decile row out loud — that spread is what the fallback cannot represent. -->

---

# R2 — Where the Claimants Are Makes It Four Times Worse

Cap difference, single adult:

| statistic | value | statement about |
|---|---|---|
| median | **−20.22 €** | the median Gemeinde |
| mean over Gemeinden | **−11.39 €** | the average Gemeinde |
| mean over Bedarfsgemeinschaften, allocated by population | <span style="color:#ff6b6b">**−47.30 €**</span> | the average **claimant** |

<div style="font-size:1.6rem; text-align:center; margin: 0.5rem 0;">
<span style="color:#9aa0a6">−20.22 €</span> · <span style="color:#9aa0a6">−11.39 €</span> · <span style="color:#ff6b6b">−47.30 €</span>
</div>

Two causes: skew, and *where the claimants are* — generous caps sit in thinly populated Kreise, cities set caps below the fallback.

**Pick your weighting before you quote a magnitude — the direction is the same either way.**

<!-- Every cut points the same way: Träger recognise less than the fallback. What the weighting changes is how much — four times as much where the claimants actually are. One Gemeinde one weight answers a question about places; the allocated Bedarfsgemeinschaft weight answers one about people. Where within a Kreis its claimants live is not observed, so the third row allocates the Kreis stock by resident population; allocating it instead to the lowest- or highest-cap Gemeinde of each Kreis brackets it. -->

---
layout: two-cols
---

# R3 — The Mietenstufe Does Not Repair It

::left::

Share of variance in log caps explained, household size 1, n = 9,397:

| classification | groups | variance share |
|---|---|---|
| Mietenstufe | 7 | **0.410** |
| Bundesland | 16 | **0.457** |
| Mietenstufe × Bundesland | 69 | 0.739 |
| Kreis | 358 | 0.919 |

Knowing only the Bundesland accounts for more of the variation than the statutory Mietenstufe.

Within Mietenstufe 1 the interdecile range is still **167.5 €**.

::right::

<img src="../../bld/kdu_vs_wohngeld/mietenstufe_dispersion.png" style="max-height: 400px; margin: 0 auto;" />

**Conditioning on the Mietenstufe leaves 59 % of the variation unaccounted for.**

<!-- This is the lead result. The statutory instrument that looks like the regional control accounts for less of the variation than a classification with sixteen values and no housing content at all. -->

---

# R4 — And the Residual Is Not Noise

Correlation with Zensus 2022 market rents, single adult, n = 9,281:

| | overall | within Mietenstufe |
|---|---|---|
| local KdU cap | 0.681 | **0.422** |
| statutory fallback | 0.705 | **0.000** (by construction) |

Between Mietenstufen the fallback tracks rents slightly *better*.

Within one, it cannot vary at all — while real caps still track market rents.

**Substituting the fallback is non-classical measurement error: it correlates 0.42 with the covariates within a Mietenstufe, so it biases in an unknown direction rather than attenuating.**

<!-- Concede the first column: between Mietenstufen the Mietenstufe tracks the rent gradient. The second column holds the residual variation, and it is systematic. These are unweighted correlations across Gemeinden, and caps are set by roughly 358 Träger, so the observations are not independent and the n overstates how much information stands behind them. -->

---

# R5 — How Much of the Rented Stock Sits Above the Cap

Substituting the fallback misstates that share by **5.4 pp** at the median Gemeinde.

For context: the local cap itself sits above **14.3 %** of the median Gemeinde's rented stock.

<img src="../../bld/market_rent_comparison/share_of_stock_above_cap.png" style="max-height: 300px; margin: 1rem auto 0;" />

**The difference survives the measurement; the level does not.**

<!-- This is the question a claimant actually faces: not what the cap is, but how much of the local market it closes off. Lead with the difference, because it is computed on the same stock with the same conversion, so the limitations largely difference out. Those limitations bind the level: the Zensus reports Bestandsmieten rather than asking rents; the kalte Betriebskosten used to convert a Bruttokaltmiete cap into a Nettokaltmiete per square metre are published only at Kreis level and stand in for every Gemeinde inside it; the count covers the whole rented stock rather than dwellings within the admissible Wohnfläche; and shares inside a two-euro band are interpolated as if rents were uniform within it. On the rent-vintage channel alone the direction is signed: sitting-tenant rents are below asking rents, so a mover faces a tighter market than these shares describe. -->

---

# R6 — No Per-Gemeinde Correction Factor Works

Within one Gemeinde the deviation from the fallback varies **across household sizes** by a median of **6.4 ratio points** — exceeding 5 points in **56 %** of Gemeinden.

<img src="../../bld/kdu_vs_wohngeld/cap_ratio_spread_distribution.png" style="max-height: 300px; margin: 1rem auto 0;" />

**A single mother is size 2 in a Gemeinde whose error you calibrated at size 1. The error moves along the very dimension your subgroup is defined on.**

<!-- If the deviation were a fixed per-Gemeinde offset, a lookup table of correction factors would close it. It is not: it moves with household size inside the same directive. -->

---

# R7 — The Margin Amplifies

Euro of gross income at the transfer exit per euro of cap error:

| Modellhaushalt | amplification |
|---|---|
| Single adult, 35 | **1.84** |
| Couple, children 8 and 14 | 1.61 |
| Single parent, child 8 | 1.58 |
| Single pensioner, 70 | **1.15** |

The pensioner is the outlier: a pension counts almost in full, while earnings keep part of each euro under the Erwerbstätigenfreibetrag of § 11b SGB II. The amplification is largely that disregard.

**Where the cap binds in both scenarios, one euro of cap difference moves the gross monthly income at which no SGB claim remains by 1.15–1.84 €, depending on the household's income type.**

<!-- Amplification is a property of earners, not of households in general — the ranking here is the Erwerbstätigenfreibetrag showing through. The exit threshold assumes the actual Bruttokaltmiete sits at the higher of the two caps, so the cap binds in both scenarios. -->
