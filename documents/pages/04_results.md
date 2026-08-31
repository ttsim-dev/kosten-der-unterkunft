# R1 — The Fallback Is Not a Safe Default

**35.7 %** of Gemeinden set caps *below* Wohngeld-Höchstbetrag × 1.10.

Cap difference, single adult, € per month — deciles:

`−73.5 · −40.1 · −15.4 · 0.0 · +0.9 · +21.1 · +31.4 · +54.4 · +97.9`

<img src="../../bld/kdu_vs_wohngeld/cap_comparison_distribution.png" style="max-height: 290px; margin: 1rem auto 0;" />

**A default that is right on average is wrong by −74 € at the first decile and +98 € at the ninth.**

<!-- The benchmark is not a floor: more than a third of Gemeinden are stricter than the Bundessozialgericht fallback. Read the two ends of the decile row out loud — that spread is what the fallback cannot represent. -->

---

# R2 — "Unbiased" and "Too Generous" at Once

Cap difference, single adult:

| statistic | value | statement about |
|---|---|---|
| median | **+0.90 €** | the median Gemeinde |
| mean over Gemeinden | **+10.02 €** | the average Gemeinde |
| mean weighted by Bedarfsgemeinschaften | <span style="color:#ff6b6b">**−24.61 €**</span> | the average **claimant** |

<div style="font-size:1.6rem; text-align:center; margin: 0.5rem 0;">
<span style="color:#7dd3a0">+0.90 €</span> · <span style="color:#7dd3a0">+10.02 €</span> · <span style="color:#ff6b6b">−24.61 €</span>
</div>

Two causes: skew, and *where the claimants are* — generous caps sit in thinly populated Kreise, cities set caps below the fallback.

Across 2.41 m Bedarfsgemeinschaften: ≈ **−0.7 bn € per year** of overstated housing need.

**Pick your weighting scheme before you quote a bias; they do not share a sign.**

<!-- The sign flips between the second and the third row, and nothing about the data changed — only the question. One Gemeinde one weight answers a question about places; Bedarfsgemeinschaft weighting answers one about people. -->

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

**The error is correlated with local housing costs — the thing a regional analysis conditions on. Confounding, not noise.**

<!-- Concede the first column: between Mietenstufen the Mietenstufe tracks the rent gradient. The second column holds the residual variation, and it is systematic. -->

---

# R5 — What the Cap Prices Out

The median Gemeinde prices **14.3 %** of its rented stock above the local cap — p10 **2.2 %**, p90 **37.5 %**.

Substituting the fallback misstates that share by **5.9 pp** at the median.

<img src="../../bld/market_rent_comparison/share_of_stock_above_cap.png" style="max-height: 300px; margin: 1rem auto 0;" />

**Zensus reports Bestandsmieten, so this understates what a mover faces.**

<!-- This is the question a claimant actually faces: not what the cap is, but how much of the local market it closes off. The Bestandsmieten caveat is mine to state, not the room's. -->

---

# R6 — No Per-Gemeinde Correction Factor Works

Within one Gemeinde the deviation from the fallback varies **across household sizes** by a median of **7.6 ratio points** — exceeding 5 points in **two thirds** of Gemeinden.

<img src="../../bld/kdu_vs_wohngeld/cap_ratio_spread_distribution.png" style="max-height: 300px; margin: 1rem auto 0;" />

**A single mother is size 2 in a Gemeinde whose error you calibrated at size 1. The error moves along the very dimension your subgroup is defined on.**

<!-- If the deviation were a fixed per-Gemeinde offset, a lookup table of correction factors would close it. It is not: it moves with household size inside the same directive. -->

---

# R7 — The Margin Amplifies

Euro of gross income at the transfer exit per euro of cap error:

| Modellhaushalt | amplification |
|---|---|
| Single adult, 35 | **1.86** |
| Couple, children 8 and 14 | 1.62 |
| Single parent, child 8 | 1.58 |
| Single pensioner, 70 | **1.15** |

The pensioner is the outlier: a pension counts almost in full, while earnings keep part of each euro under the Erwerbstätigenfreibetrag of § 11b SGB II. The amplification is largely that disregard.

**Each euro of cap error moves the eligibility boundary by 1.86 €.**

<!-- Amplification is a property of earners, not of households in general — the ranking here is the Erwerbstätigenfreibetrag showing through. The exit threshold assumes the actual Bruttokaltmiete sits at the higher of the two caps, so the cap binds in both scenarios. -->
