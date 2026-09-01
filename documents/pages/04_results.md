# R1 — Local caps are below the benchmark in 60 % of Gemeinden

**59.9 %** of Gemeinden set caps *below* the Wohngeld-based benchmark.

Cap difference, single adult, € per month — deciles:

`−94.4 · −61.9 · −36.5 · −21.1 · −20.2 · 0.0 · +10.3 · +32.6 · +71.8`

<img src="../../bld/kdu_vs_wohngeld/cap_difference_distribution.png" style="max-height: 290px; margin: 1rem auto 0;" />

**The local cap sits 20 € below the benchmark at the median Gemeinde, 94 € below at the first decile and 72 € above at the ninth.**

<!-- The benchmark is not a floor: 59.9 % of Gemeinden set a cap below it. Read the two ends of the decile row out loud — that spread is what a single national figure cannot represent. -->

---

# R2 — Caseload weighting increases the estimated mean gap

Cap difference, single adult, € per month:

| statistic | value | statement about |
|---|---|---|
| median | **−20.22 €** | the median Gemeinde |
| mean over Gemeinden | **−11.39 €** | the average Gemeinde |
| mean over Bedarfsgemeinschaften, allocated by population | <span style="color:#9aa0a6">**−47.30 €**</span> | the average claimant **under a within-Kreis constant claimant rate** |

Where within a Kreis its claimants live is **not observed**. Allocating each Kreis's published stock entirely to its **lowest-departure** Gemeinde gives **−65.84 €**; entirely to its **highest-departure** Gemeinde gives **−26.23 €**. Every within-Kreis placement of the published stocks lies between the two:

<div style="font-size:1.5rem; text-align:center; margin: 0.4rem 0;">
<span style="color:#9aa0a6">−65.84 € ≤ mean over Bedarfsgemeinschaften ≤ −26.23 €</span>
</div>

**The direction of the result does not depend on the allocation assumption at all; only the magnitude does.**

<!-- Every cut points the same way: Träger recognise less than the benchmark. What the weighting changes is how much. One Gemeinde one weight answers a question about places; the allocated Bedarfsgemeinschaft weight answers one about people. Because where within a Kreis its claimants live is not observed, the population allocation is bracketed by putting the whole Kreis stock on the Gemeinde with the lowest departure and on the one with the highest departure — the extremes are taken on the cap difference, not on the cap itself, and the Gemeinde with a Kreis's lowest cap is the one with its lowest departure in only 57 % of Kreise, because the Mietenstufe varies within a Kreis. One direction of bias is signed: claimant rates are higher in the urban core of a Kreis and cities set lower caps, so a constant-rate allocation understates the claimant-weighted gap. The assumption leans toward the null of this very result. -->

---
layout: two-cols
---

# R3 — Mietenstufe fixed effects absorb 41 % of log-cap variation

::left::

Share of variance in log caps between groups, household size 1, n = 9,397:

| classification | groups | share | adjusted |
|---|---|---|---|
| Mietenstufe | 7 | **0.410** | **0.410** |
| Bundesland | 16 | **0.457** | **0.456** |
| Mietenstufe × Bundesland | 69 | 0.739 | 0.737 |
| Kreis | 358 | 0.919 | 0.916 |

Knowing only the Bundesland accounts for more of the variation than the Mietenstufe.

The degrees-of-freedom correction moves every row by less than **0.004**, against a Mietenstufe-to-Bundesland gap of **0.047**.

Within Mietenstufe 1 the interdecile range is still **167.5 €**.

::right::

<img src="../../bld/kdu_vs_wohngeld/mietenstufe_dispersion.png" style="max-height: 400px; margin: 0 auto;" />

**Conditioning on the Mietenstufe leaves 59 % of the variation unaccounted for.**

<!-- This is the lead result. The instrument that looks like the regional control accounts for less of the variation than a classification with sixteen values and no housing content at all. In-sample fit rises mechanically with the number of groups, so the adjusted column is on the slide: with n = 9,397 the correction is an order of magnitude smaller than the gap it would have to close. -->

---

# R4 — Local caps retain systematic within-Mietenstufe variation

Correlation with the mean incumbent Nettokaltmiete per square metre (Zensus 2022), single adult, n = 9,281:

| | overall | within Mietenstufe |
|---|---|---|
| local KdU cap | 0.681 | **0.422** |
| Wohngeld-based benchmark | 0.705 | **n/a — constant within class** |

Between Mietenstufen the benchmark tracks the rent gradient slightly *better*.

Within one, the benchmark takes a single value at a fixed household size, so no correlation is defined — while local caps still covary with the local rent measure at **ρ = 0.42**.

<!-- Grant the first column: between Mietenstufen the Mietenstufe tracks the rent gradient. The second column holds the residual variation, and it is systematic rather than idiosyncratic. The benchmark cell is not a zero: at a fixed household size the benchmark has exactly one distinct value per Mietenstufe and a standard deviation of exactly zero, so the correlation is 0/0 and undefined. These are unweighted correlations across Gemeinden, and caps are set by roughly 358 Träger, so the observations are not independent and the n overstates how much information stands behind them. The Zensus measure is sitting-tenant rent in 2022, not asking rent. -->

---

# R5 — A single Gemeinde factor does not reproduce the household-size schedule

Within one Gemeinde the departure from the benchmark varies **across household sizes** by a median of **6.4 ratio points** — exceeding 5 points in **56 %** of Gemeinden.

<img src="../../bld/kdu_vs_wohngeld/cap_ratio_spread_distribution.png" style="max-height: 300px; margin: 1rem auto 0;" />

**A single parent is size 2 in a Gemeinde whose difference you would have calibrated at size 1. The difference moves along the very dimension the subgroup is defined on.**

<!-- If the departure were a fixed per-Gemeinde offset, a lookup table of correction factors would close it. It is not: it moves with household size inside the same directive. -->

---

# R6 (appendix) — A stock-based rent-threshold index

Share of the local rented stock whose rent sits above the cap. Substituting the Wohngeld-based benchmark for the local cap moves that share by **5.4 pp** at the median Gemeinde.

For context only: the local cap itself sits above **14.3 %** of the median Gemeinde's rented stock.

<img src="../../bld/market_rent_comparison/share_of_stock_above_cap.png" style="max-height: 300px; margin: 1rem auto 0;" />

**The difference survives the measurement; the level does not.**

<!-- Appendix material, and lead on the difference: it is computed on the same stock with the same conversion, so the limitations largely difference out. Those limitations bind the level, which is why 14.3 % is context and not a result. The Zensus reports Bestandsmieten from 2022 rather than asking rents; the kalte Betriebskosten used to convert a Bruttokaltmiete cap into a Nettokaltmiete per square metre are published only at Kreis level and stand in for every Gemeinde inside it; the count covers the whole rented stock rather than dwellings within the admissible Wohnfläche; and shares inside a two-euro band are interpolated as if rents were uniform within it. On the rent-vintage channel alone the direction is signed: sitting-tenant rents are below asking rents, so a mover faces a tighter distribution than these shares describe. -->
