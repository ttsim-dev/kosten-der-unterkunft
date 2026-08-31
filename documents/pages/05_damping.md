# The Parameter Is Wrong; the Outcome Frequently Is Not

BA Wohnkostenstatistik, single Bedarfsgemeinschaften:

| | |
|---|---|
| actual Bruttokaltmiete | **427.84 €** |
| recognised | **411.14 €** |
| shortfall | **16.70 €** |
| unrecognised share of euros | **3.9 %** |
| Bedarfsgemeinschaft-weighted | **3.5 %** |

Existing claimants already sit under their cap, so `min(rent, cap)` does not bind.

- It is a share of **euros, not of households** — equally consistent with 90 % losing
  nothing and 10 % losing a great deal.
- It holds for the **level of the incumbent caseload** and nowhere else.

<!--
This is the objection everyone in the room is about to raise, so raise it first and
then bound it. Both qualifications matter: it never spoke to the spread across
Germany, and it says nothing about anything determined at the margin.
-->

---

# Where the Error Dies, and Where It Grows

| where | form | effect |
|---|---|---|
| recognised housing cost | `min(actual rent, cap)` | **damps** |
| `ungedeckter_bedarf_m`, and again at Bedarfsgemeinschaft level | `max(0, regelbedarf − einkommen)` | **amplifies**, asymmetrically |
| `wohngeld_kinderzuschlag_vorrangig_…_ab_2023` | returns a **bool** | **misclassifies the instrument** |

The third has **no euro interpretation at all**. The cap sits on the right-hand side of
that Vorrangprüfung, so a wrong cap assigns the household to Wohngeld and
Kinderzuschlag instead of Bürgergeld, or the reverse.

It corrupts take-up and the instrument split even when total euros look fine.

<!--
Three non-linear points in the DAG, and only the first reduces the error. Spend the
time on the third row: a bool cannot be off by sixteen euros — it is either right or
wrong.
-->
