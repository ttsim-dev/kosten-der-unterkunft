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

<br/>

For a single, that warm ceiling implies **378.88 €** of Bruttokaltmiete, against a
median local cap of **428.50 €**.
