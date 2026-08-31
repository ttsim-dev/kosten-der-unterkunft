# What GETTSIM Does Today

`germany/bürgergeld/kosten_der_unterkunft.yaml`, unchanged since 2023:

```text
mietobergrenze_pro_qm_m      = 10 €/m²   (warm: (bruttokaltmiete + heizkosten) / wohnfläche)
berechtigte_wohnfläche_miete = 45 m² + 15 m² per further person

kosten_der_unterkunft_m = min(actual €/m², 10) × min(area, 45 + 15·(n−1))
```

The YAML says it itself: *"Die regionalen Parameter sind unbekannt."*

<!--
Two national constants, a price per square metre and an admissible area, multiplied
together. The file is honest about what it does not know.
-->

---

# The Level Is Wrong

Single adult:

| | |
|---|---|
| GETTSIM implied cap, warm | 45 × 10 = **450 €** |
| Bedarfsgemeinschaft-weighted mean actual Heizkosten (BA Wohnkostenstatistik) | **69.49 €** |
| GETTSIM implied cap, Bruttokaltmiete | **380.51 €** |
| median local cap | **430.50 €** |
| gap at the median Gemeinde | **≈ 50 €/month too tight** |
| Gemeinden whose cap exceeds it | **78.6 %** (of 9,471) |

**The limit:** this compares **caps, not payouts**. `min(actual €/m², 10)` means a
household under 10 €/m² keeps its rent.

<!--
Strip the Heizkosten out to make the two comparable, and the national constant sits
about fifty euros below the median Gemeinde. Say the limit before anyone else does.
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
