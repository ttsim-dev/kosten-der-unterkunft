# What GETTSIM does today

`germany/bürgergeld/kosten_der_unterkunft.yaml`, unchanged since 2023:

```text
mietobergrenze_pro_qm_m      = 10 €/m²   warm
berechtigte_wohnfläche_miete = 45 m² + 15 m² per further person
```

- The ceiling binds on **warm** rent, so **Heizkosten sit inside it**.

- The Bundessozialgericht's **Produktregel** binds only the *product* of angemessene
  Wohnfläche and angemessener Quadratmeterpreis. GETTSIM caps the two factors
  **separately**, which is a stricter rule.

- The parameter file says it itself: *"Die regionalen Parameter sind unbekannt."*

<br/>

For a single, that warm ceiling implies **380.68 €** of Bruttokaltmiete, against a median
local cap of **430.50 €**.

<!--
Two national constants multiplied together, and the product is a warm ceiling, so heating
is not granted on top of it. Because the minimum is taken on each factor separately, slack
on the area cap cannot offset the factor that binds — exactly what the Produktregel does
not do. The euro comparison runs through GETTSIM 1.3 at 50 m² with national Heizkosten of
67.69 €, so it moves with a GETTSIM release and is stored with the version.
-->
