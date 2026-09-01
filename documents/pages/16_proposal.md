# What we propose

1. **Interface** — a user-overridable **monthly Bruttokaltmiete ceiling**, with Heizkosten
   assessed separately, instead of capping €/m² and m² separately on warm rent.
   *Why:* 43,930 of 54,900 collected cap records publish a single euro figure, and that is
   what the Produktregel describes.

1. **Default** — **(WoGG-Höchstbetrag + Klimakomponente) × 1.10**.
   *Why:* GETTSIM already carries the Höchstbetrag table in `germany/wohngeld/miete.py`.
   *Cost:* it introduces `mietstufe_hh` as an input for Bürgergeld-only simulations, and it
   is systematically generous — about **20 €** above the median Gemeinde's cap, about
   **47 €** above under the population-allocated Bedarfsgemeinschaft weighting.

1. **Optional companion package** supplying the Gemeinde-level caps by **AGS**, for anyone
   who wants the actual local number.

<!--
Decision 1 is about the shape of the parameter and is independent of its value; decision 2
is about the value. Nothing has to be decided in the room — the useful outcome is knowing
which of the three the maintainers consider worth pursuing. A spelling difference to note:
GETTSIM says mietstufe, this project says mietenstufe.
-->
