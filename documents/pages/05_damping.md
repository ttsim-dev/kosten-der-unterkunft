# Aggregate non-recognition is small in the incumbent caseload

BA Wohnkostenstatistik, single Bedarfsgemeinschaften:

| | |
|---|---|
| actual Bruttokaltmiete | **427.84 €** |
| recognised | **411.14 €** |
| shortfall | **16.70 €** |
| unrecognised share of euros | **3.9 %** |
| Bedarfsgemeinschaft-weighted | **3.5 %** |

Across the incumbent caseload, **3.5 %** of reported Bruttokaltmiete euros go unrecognised, over 398 Jobcenter.

- It is a share of **euros, not of households** — equally consistent with 90 % losing
  nothing and 10 % losing a great deal.
- It holds for the **level of the incumbent caseload** and nowhere else.
- It does not identify the household-level **incidence** of a binding ceiling.
- It is reported Bruttokaltmiete for households **already in the caseload**, so it is
  conditioned on being in it and says nothing about anyone a cap kept out.

<!--
Put this first, before the pass-through and the threshold experiment: the number
everyone in the room is about to raise, raised here and then bounded. All four
qualifications matter, and the last is the honest reason 3.5 % cannot bound the effect
at the margin — the statistic is conditioned on the caseload it is measured over.
-->

---

# Nonlinearities govern pass-through to simulated outcomes

| stage | mapping | implication |
|---|---|---|
| recognised Bruttokaltmiete | `min(actual Bruttokaltmiete, cap)` | truncates the difference |
| benefit amount — `ungedeckter_bedarf_m`, and again at Bedarfsgemeinschaft level | `max(0, regelbedarf − einkommen)` | at most one-for-one while entitled; zero after exit |
| gross-income exit threshold | inverse of the net-income and withdrawal schedule | can move by more than one euro per euro of cap difference |
| programme assignment — `wohngeld_kinderzuschlag_vorrangig_oder_günstiger_ab_2023` | returns a **bool** | discrete; can switch the simulated programme |

The last has **no euro interpretation at all**. The cap sits on the right-hand side of
that Vorrangprüfung, and the bool gates Bürgergeld, Wohngeld, Kinderzuschlag and
Grundsicherung im Alter alike, so a different cap can move the household to a different
simulated programme.

**The same cap difference can be irrelevant for benefit levels, material at an
eligibility threshold, or discrete for programme assignment.**

<!--
Four points in the DAG, and the euro difference never grows at the second one:
while the household is entitled, the derivative of the benefit with respect to the cap
is exactly one, and the truncation at zero sends it to zero after exit. The stage that
moves by more than one-for-one is the inverse map — from a need difference to the gross
income that exhausts entitlement — and that is the next slide. Spend the time on the
last row: a bool cannot be off by sixteen euros. This is simulated programme assignment,
not behaviour; nothing in this project models whether a household claims.
-->

---

# Gross-income exit thresholds can move more than one-for-one

Median over Gemeinden of the per-Gemeinde ratio — € of gross monthly income at the transfer exit per € of cap difference:

| Modellhaushalt | € per € | n Gemeinden |
|---|---|---|
| Single adult, 35 | **1.84** | 9,397 |
| Couple, children 8 and 14 | 1.61 | 9,368 |
| Single parent, child 8 | 1.58 | 9,388 |
| Single pensioner, 70 | **1.15** | 9,397 |

Identifying construction: the assumed actual Bruttokaltmiete is set to
`max(local cap, Wohngeld-based benchmark)`, so **both ceilings bind by construction**.
These are the **median of per-Gemeinde ratios**, not a ratio of medians.

The single-adult and single-pensioner rows share household size, Gemeinde set
(n = 9,397) and cap differences (p10 −94.44, median −20.22, p90 +71.78) exactly. Only
the income type differs — earnings against a pension.

**Scenario-specific threshold effects, not population-average effects.**

<!--
Because the two single rows hold everything but income type fixed, the contrast does
identify income type as the source of the difference between 1.84 and 1.15. It does not
go further: the Erwerbstätigenfreibetrag of § 11b SGB II, the
Sozialversicherungsbeiträge and the income tax all switch on together with earnings, so
this sweep cannot separate them. Say that much and no more. And say what the
construction assumes: both ceilings bind, which is the case in which the threshold moves
at all.
-->
