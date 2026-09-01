# What GETTSIM Does Today

`germany/bürgergeld/kosten_der_unterkunft.yaml`, unchanged since 2023:

```text
mietobergrenze_pro_qm_m      = 10 €/m²   warm
berechtigte_wohnfläche_miete = 45 m² + 15 m² per further person

kosten_der_unterkunft = min(wohnfläche, 45 + 15·(n−1))
                      × min((bruttokaltmiete + heizkosten) / wohnfläche, 10)
```

The ceiling binds on **warm** rent — Heizkosten sit inside it. There is no
Bruttokaltmiete cap in GETTSIM to hold a Richtlinie against.

The YAML says it itself: *"Die regionalen Parameter sind unbekannt."*

<!--
Two national constants, a price per square metre and an admissible area, multiplied
together — and the product is a warm ceiling, so heating is not granted on top of it.
That is why the comparison has to be run through GETTSIM rather than converted by hand.
The parameter file records that the regional values are unknown.
-->

---

# In a stylised median-cap case, the gap is largest for one person

One household through three rules. Warm, € per month, computed by GETTSIM 1.3:

| household | GETTSIM | median Gemeinde | Wohngeld-based benchmark | Gemeinden above GETTSIM |
|---|---|---|---|---|
| 1 person, 50 m², 430.50 + 67.69 € | **448.37** | **498.19** | 485.91 | **78.6 %** |
| 2 persons, 60 m², 507.98 + 99.88 € | **600.00** | **607.86** | 607.86 | **53.0 %** |
| 4 persons, 90 m², 710.00 + 133.99 € | **843.99** | **843.99** | 840.63 | **0.0 %** |

<!--
Same actual rent, same area, same Heizkosten in all three columns; only the rule
changes. Actual rent is the median local cap, area the modal admissible area in the
collected Richtlinien, Heizkosten the Bedarfsgemeinschaft-weighted mean of the BA
Wohnkostenstatistik. Both are assumptions — no Gemeinde-level distribution of rents
actually paid exists — and the last column is one Gemeinde one weight.

The difference is not a level shift. For a single the national ceiling is about fifty
euros below the median Gemeinde; by four persons at 90 m² it does not bind at all,
because that household is already under 10 €/m² warm. This is one stylised dwelling per
row, not a population average. Numbers are GETTSIM 1.3's own column and move with a
GETTSIM release, so they are stored with the version.
-->

---

# The current functional form differs from the Produkttheorie

The Bundessozialgericht's **Produkttheorie**: only the *product* of angemessene
Wohnfläche and angemessener Quadratmeterpreis binds. GETTSIM caps the two
**separately**.

- Of **54,900** collected cap records, **43,930** publish a single Bruttokaltmiete euro
  figure, **2,430** are summed from published components, and **8,540** carry no
  published Bruttokaltmiete cap at all.

- Admissible area for a single: **50 m² in 7,302** records against **45 m² in 1,628**.
  GETTSIM's 45 is the minority convention, **4.5 : 1**.

- One person, 30 m², Bruttokaltmiete **390.00 €** plus Heizkosten **60.00 €** =
  **450.00 €** warm = **15.00 €/m²** warm (GETTSIM 1.3):
  - GETTSIM: the area cap does **not** bind (30 m² against 45 m²); the price ceiling
    **does** (15.00 against 10.00 €/m² warm) → **300.00 €** recognised warm, heating
    inside that figure.
  - Against a monthly Bruttokaltmiete ceiling of **430.50 €**: **390.00 €** cold
    recognised in full, **plus 60.00 €** Heizkosten assessed separately.

<!--
This one is independent of the parameter value. Because GETTSIM takes a minimum on each
factor separately, slack on the area cap cannot offset the factor that binds — that is
exactly what the Produkttheorie does not do, where only the product has to clear the
threshold. Read the two sides as two functional forms that are not equal, not as one
paying more than the other: the local side keeps Heizkosten as a separate assessment,
and that separation is the whole point. It comes back as proposal F.
-->
