# Decision 1 — How GETTSIM Represents the Ceiling

Proposal: a **user-overridable monthly Bruttokaltmiete ceiling**, with Heizkosten
treated separately — instead of `min(€/m²) × min(m²)` on warm rent.

- The Bundessozialgericht's **Produkttheorie**: only the *product* of angemessene
  Wohnfläche and angemessener Quadratmeterpreis binds. Capping the two separately is a
  stricter rule than the one the Träger apply.

- **43,930 of 54,900** collected cap records publish exactly a single euro figure per
  month. A monthly figure is the form the Richtlinien are written in.

<br/>

This decision is about the **shape** of the parameter, and is independent of what value
the parameter takes.

<!--
This is the interface question. Whatever the default turns out to be, a single monthly
Bruttokaltmiete figure is what a user reading a Richtlinie can enter without converting
anything, and it is what the case law describes.
-->

---

# Decision 2 — Where the Default Comes From

| | option | cost to maintainers | limitation |
|---|---|---|---|
| A | user supplies the cap; GETTSIM ships no default | zero | no documented default — each user picks a value privately |
| B | ship AGS → cap inside GETTSIM | high, recurring, ~400 Träger | goes out of date as Träger republish |
| C | one empirical national €/month value, overridable | one number | no regional variation at all (see below) |
| **D** | **Wohngeld-Höchstbetrag plus Klimakomponente, × 1.10** | **one constant, existing tables, plus `mietstufe_hh` for Bürgergeld-only users** | **median −20.22 €; −47.30 € under the population-allocated Bedarfsgemeinschaft weighting** |
| E | companion package supplying AGS → cap, opt-in | zero for core | opt-in, so the core default is still needed |

C in numbers: a published Bruttokaltmiete cap of **430.50 €** against an implied
Bruttokaltmiete of **380.68 €** — GETTSIM's warm ceiling of 448.37 € minus the assumed
national Heizkosten of 67.69 € — for the same single-person household.

<!--
This decision is about the value, not the shape. The recommendation is D for the core
default with E alongside it for anyone who wants the actual local caps. A, B and C are
listed because each is a real position someone may prefer.
-->

---

# The Wohngeld-based Default Reuses Existing Policy Tables

- `germany/wohngeld/miete.py` — **already carries the Höchstbetrag table**:
  `max_miete_m_lookup.look_up(anzahl_personen_hh, mietstufe_hh)`.

What it costs:

- It avoids maintaining a national Gemeinde-level KdU table in core GETTSIM.
- It **introduces `mietstufe_hh` as an input** for Bürgergeld-only simulations, which
  today never touch it — `mietstufe` appears only under `germany/wohngeld/`.
- It stays an approximation to local practice.
- Beyond the 1.10 constant it needs a monthly Bruttokaltmiete interface, a
  Mietenstufe-keyed lookup on the Bürgergeld side, a decision on the Klimakomponente,
  new DAG dependencies, tests and documentation.

The **1.10 Sicherheitszuschlag** where no schlüssiges Konzept exists is
Bundessozialgericht case law (BSG, 12.12.2013 - B 4 AS 87/12 R). Whether the
**Klimakomponente** enters the base that factor multiplies is **not settled** at the
Bundessozialgericht; the construction here follows consistent instance case law.

A spelling gap to note: GETTSIM says `mietstufe`, this project says `mietenstufe`.

<!--
The Höchstbetrag table is the real strength here: it exists, it is maintained, and it is
keyed the way the default needs. The input requirement is the honest cost — a
Bürgergeld-only run has no reason to know its Mietenstufe today.
-->

---

# Limits of the Wohngeld-based default

- It is a legally grounded *construction* and a systematically generous *parameter*: it
  sits **20 €** above the median Gemeinde's cap and **47 €** above the cap under the
  population-allocated Bedarfsgemeinschaft weighting. The Wohngeld-based benchmark is
  not where Träger have settled.

- The Mietenstufe accounts for a variance share of **0.410** in log caps — less than
  knowing only the Bundesland (**0.457**). The default inherits exactly that regional
  resolution and no more.

<br/>

A defensible documented default. Not a substitute for the local cap.

<!--
Both limits are worth stating directly, and neither argues for the status quo: today's
national constant does worse on both counts.
-->

---

# Decision points

1. **Core interface** — a monthly, user-overridable Bruttokaltmiete ceiling.

1. **Core default** — a documented Wohngeld-based default: Höchstbetrag plus
   Klimakomponente, × 1.10.

1. **Optional companion package** — the current Gemeinde-level (AGS) local ceilings.

<!--
Leave this on screen for the discussion. Nothing has to be decided in the room; the
useful outcome is knowing which of these three the maintainers consider worth pursuing.
-->
