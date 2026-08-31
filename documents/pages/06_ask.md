# Six Options

| | option | cost to maintainers | what the data says |
|---|---|---|---|
| A | user supplies the cap; GETTSIM does not guess | zero | correct but empty — every user then invents 10 €/m² privately |
| B | ship AGS → cap inside GETTSIM | high, recurring, ~400 Träger | the dataset exists; it goes out of date as Träger republish |
| C | one empirical national €/month value, overridable | one number | 430.50 € against today's implied 380.51 €; but no regional variation at all |
| **D** | **Wohngeld-Höchstbetrag × 1.10 as the default cap** | **one parameter, no new data** | median +0.90 €, claimant-weighted −24.61 €, explains 41 % |
| E | companion package supplying AGS → cap, opt-in | zero for core | the realistic version of B |
| **F** | **single €/month cap instead of `min(€/m²) × min(m²)`** | small | Produkttheorie; 43,930 of 54,900 records publish exactly this |

<!--
The proposal is F together with D, with E as the opt-in for anyone who wants the real
caps. A, B and C are on the table honestly, not as straw men.
-->

---

# D Costs One Parameter and No New Data

GETTSIM already has both halves of it:

- `germany/wohngeld/inputs.py` — **already requires `mietstufe_hh`** from every user.

- `germany/wohngeld/miete.py` — **already carries the Höchstbetrag table**:
  `max_miete_m_lookup.look_up(anzahl_personen_hh, mietstufe_hh)`.

<br/>

So D costs **one scalar parameter (1.10) and zero new data** — and it is the
Bundessozialgericht standard where no schlüssiges Konzept exists, rather than a chosen
number.

A spelling gap to note: GETTSIM says `mietstufe`, this project says `mietenstufe`.

<!--
No new input burden and no new dataset to keep current. The only thing D adds is a
multiplication that already has a legal basis.
-->

---

# What Is Wrong With D

Stated by me, before anyone else does:

- The claimant-weighted mean cap difference is **−24.61 €** per month. D is unbiased at
  the median Gemeinde and too generous at the average claimant. Those signs differ.

- The Mietenstufe accounts for a variance share of **0.410** in log caps — less than
  knowing only the Bundesland (**0.457**). D inherits exactly that regional resolution
  and no more.

<br/>

D is a defensible default. It is not a substitute for the local cap.

<!--
Conceding both weaknesses up front is better than being handed them, and neither one
argues for the status quo — today's national constant does worse on both counts.
-->

---

# Open Floor

| | option | cost to maintainers | what the data says |
|---|---|---|---|
| A | user supplies the cap; GETTSIM does not guess | zero | correct but empty — every user then invents 10 €/m² privately |
| B | ship AGS → cap inside GETTSIM | high, recurring, ~400 Träger | the dataset exists; it goes out of date as Träger republish |
| C | one empirical national €/month value, overridable | one number | 430.50 € against today's implied 380.51 €; but no regional variation at all |
| **D** | **Wohngeld-Höchstbetrag × 1.10 as the default cap** | **one parameter, no new data** | median +0.90 €, claimant-weighted −24.61 €, explains 41 % |
| E | companion package supplying AGS → cap, opt-in | zero for core | the realistic version of B |
| **F** | **single €/month cap instead of `min(€/m²) × min(m²)`** | small | Produkttheorie; 43,930 of 54,900 records publish exactly this |

<!--
Leave this on screen for the discussion. Nothing has to be decided in the room; the
useful outcome is knowing which rows the maintainers consider worth pursuing.
-->
