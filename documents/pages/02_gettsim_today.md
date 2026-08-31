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

# The Level Is Wrong for Small Households

One household through three rules. Warm, € per month, computed by GETTSIM 1.3:

| household | GETTSIM | median Gemeinde | Wohngeld fallback | Gemeinden above GETTSIM |
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

The error is not a level shift. For a single the national ceiling is about fifty euros
short of the median Gemeinde; by four persons at 90 m² it does not bind at all, because
that household is already under 10 €/m² warm. Numbers are GETTSIM 1.3's own column and
move with a GETTSIM release, so they are stored with the version.
-->

---

# The Functional Form Is Wrong Too

The Bundessozialgericht's **Produkttheorie**: only the *product* of angemessene
Wohnfläche and angemessener Quadratmeterpreis binds. GETTSIM caps the two
**separately**.

- **43,930 of 54,900** collected cap records publish a single euro figure. Only
  **2,430** are built from components — Träger publish the product.

- Admissible area for a single: **50 m² in 7,302** records against **45 m² in 1,628**.
  GETTSIM's 45 is the minority convention, **4.5 : 1**.

- Single, 30 m², 15 €/m² warm: GETTSIM recognises 30 × 10 = **300 €**. A real
  Richtlinie recognises the whole **~450 €**, because the product is under the cap.

<!--
This one is independent of the parameter value: even with a perfect euro per square
metre, the separate caps misprice a small expensive flat. It comes back as proposal F.
-->
