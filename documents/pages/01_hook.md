# Housing costs require a local parameter

Under **§ 19 Absatz 1 SGB II** the components are separate:

```
Gesamtbedarf = Regelbedarf + anerkannte KdU + Mehrbedarfe
```

- **Regelbedarf** is **statutory** and known to the cent

- **anerkannte KdU** is **not a national parameter**: § 22 SGB II delegates the
  number to roughly 400 Träger

- And it is the component that **varies**: one national number against 272.64 € to
  911.00 €

**Technical note.** In the current GETTSIM implementation the relevant function combines
two of these components under the name of one of them:

```
# gettsim/germany/bürgergeld/regelbedarf.py
regelbedarf_m = regelsatz_m + kosten_der_unterkunft_m
```

<!--
The Regelbedarf is legislated to the cent — 563 € at Regelbedarfsstufe 1. The KdU
component is delegated: § 22 SGB II states the rule and leaves the number to each
Träger, and it is the component that moves. The identifier in the source is a software
name, not the institutional concept: § 19 Absatz 1 SGB II lists Regelbedarf, Mehrbedarfe
and Bedarf für Unterkunft und Heizung as separate components, and the function sums two
of them under the name of the one that excludes the other.
-->

---

# A fixed one-person case under different local ceilings

Recognised cap at household size one, € per month, across Gemeinden with a collected
cap:

- minimum **272.64 €** · median **430.50 €** · maximum **911.00 €**

- percentiles **p10 342.5 · p25 390.0 · p50 430.5 · p75 499.0 · p90 560.0**

<br/>

Working on the **2026 Rentenkommission** update I had to decide whether a given
pensioner ends up in Grundsicherung im Alter — and I could not state her Bedarf.

<!--
Same single pensioner, same statutory Regelsatz, moved from one Gemeinde to another:
the recognised housing cap runs from 273 € to 911 €. The spread is an order of magnitude
larger than a rounding difference. The sample this distribution is taken over is on the
data slide that follows.
-->

---

# Institutional setting

- **§ 22 SGB II** — Unterkunftskosten are recognised *"in tatsächlicher Höhe, soweit
  angemessen"*. The law never defines *angemessen*.

- **~400 Träger** — every Kreis and kreisfreie Stadt publishes its own Richtlinie.
  Roughly 400 documents, collected by hand from Harald Thomé's archive.

- **Schlüssiges Konzept** — where a Träger has published none, the Bundessozialgericht
  sets the Angemessenheitsgrenze at the **Wohngeld-Höchstbetrag** (Anlage 1 zu § 12
  Absatz 1 WoGG) plus a **Sicherheitszuschlag of 10 %** — BSG, 12.12.2013 - B 4 AS 87/12 R.

- **Klimakomponente** — whether § 12 Absatz 7 WoGG enters the base that the 1.10
  multiplies is **not settled by the Bundessozialgericht**. The 2013 judgment predates
  the Klimakomponente, in force since 1.1.2023. Adding it before the markup follows
  **consistent instance case law** and is **unresolved at the Bundessozialgericht**.

<br/>

This deck measures against one documented analytical benchmark,
**(Höchstbetrag + Klimakomponente) × 1.10** — the *Wohngeld-based benchmark*. It is
**not** the legally applicable ceiling where a valid schlüssiges Konzept exists.

Every cap here is a **Bruttokaltmiete**, and every cap is a **maximum, not a payment**.

<!--
The room knows Bürgergeld but not this delegation. The law leaves the number open, about
four hundred Träger each answer it separately, and the case law supplies a construction
where a Träger has answered it with no schlüssiges Konzept. Keep the two halves apart:
the 10 % Sicherheitszuschlag on the Wohngeld table is Bundessozialgericht case law; the
place of the Klimakomponente in the base is instance case law only. The instance
decisions are SG Aurich 23.09.2025 - S 55 AS 99/25 ER, SG Oldenburg 20.06.2024 - S 37
AS 506/23, LSG Berlin-Brandenburg 17.01.2024 - L 32 AS 1179/23 B ER; their reasoning is
that the Sicherheitszuschlag absorbs the backward-looking Wohngeld table while the
Klimakomponente addresses future price development.
-->
