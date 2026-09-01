# For anyone simulating Kosten der Unterkunft

- **Have the Gemeinde (AGS)? Use its own cap** — not the Kreis's. 210 of 358 Kreise
  publish more than one.

- **No Gemeinde? Cross Mietstufe with Bundesland.** The Mietstufe alone leaves ± 83 €;
  the two together ± 50 €.

- **Never calibrate one correction factor per Gemeinde.** The gap moves with household
  size, and in 1 of 8 Gemeinden it changes direction.

- **A cap error hurts about twice as much at the eligibility margin.** 100 € too little
  cap makes the benefit at most 100 € too low — but pushes the household out of the
  system about 180 € of gross income too early.

<!--
The euro figures are p10-to-p90 half-widths of the cap around its group mean at household
size one, one Gemeinde one weight — a spread, not a standard error. Crossing the two
classifications is the one recommendation here that does not depend on the transform:
0.739 of the variation in log caps and 0.725 in euro, against 0.410 and 0.454 for the
Mietstufe alone. The amplification at the margin is roughly 1.8 because counted income
rises more slowly than gross income — Sozialversicherungsbeiträge, Einkommensteuer and
the Erwerbstätigenfreibetrag take their share first.
-->
