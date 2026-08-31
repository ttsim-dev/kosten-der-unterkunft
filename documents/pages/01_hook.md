# Every Simulated Bedarf Contains This Term

`gettsim/germany/bürgergeld/regelbedarf.py`

```
regelbedarf_m = regelsatz_m + kosten_der_unterkunft_m
```

- `regelsatz_m` is **statutory** and known to the cent

- `kosten_der_unterkunft_m` is **not a national parameter**: § 22 SGB II delegates the
  number to roughly 400 Träger

- And it is the half that **varies**: one national number against 272.64 € to 911.00 €

<!--
The left half is legislated to the cent — 563 € at Regelbedarfsstufe 1. The right half
is delegated: § 22 SGB II states the rule and leaves the number to each Träger, and it
is the half that moves. Note also what the identifier does: § 19 Abs. 1 SGB II lists
Regelbedarf, Mehrbedarfe and Bedarf für Unterkunft und Heizung as separate components,
and this function sums two of them under the name of the one that excludes the other.
-->

---

# One Pensioner, Moved Across Germany

Recognised cap at household size one, € per month (n = 9,471 Gemeinden):

- minimum **272.64 €** · median **430.50 €** · maximum **911.00 €**

- percentiles **p10 342.5 · p25 390.0 · p50 430.5 · p75 499.0 · p90 560.0**

<br/>

Working on the **2026 Rentenkommission** update I had to decide whether a given
pensioner ends up in Grundsicherung im Alter — and I could not state her Bedarf.

<!--
Same single pensioner, same statutory Regelsatz, moved from one Gemeinde to another:
the recognised housing cap runs from 273 € to 911 €. This is not a rounding question.
-->

---

# Three Terms, Forty-Five Seconds

- **§ 22 SGB II** — Unterkunftskosten are recognised *"in tatsächlicher Höhe, soweit
  angemessen"*. The law never defines *angemessen*.

- **~400 Träger** — every Kreis and kreisfreie Stadt publishes its own Richtlinie.
  Roughly 400 documents, collected by hand from Harald Thomé's archive.

- **Schlüssiges Konzept** — where a Träger has published none, the
  Bundessozialgericht prescribes **Wohngeld-Höchstbetrag plus Klimakomponente, × 1.10**.
  That is the
  benchmark throughout: it follows the case law rather than being chosen.

<br/>

Every cap here is a **Bruttokaltmiete**, and every cap is a **maximum, not a payment**.

<!--
The room knows Bürgergeld but not this delegation. The law leaves the number open,
about four hundred Träger each answer it separately, and the courts supply the
fallback.
-->
