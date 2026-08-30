# Config requests — P0.2 (Wohngeld benchmark)

`src/kdu/data_management/wohngeld.py` currently derives its two input paths from
`kdu.config.DATA` and its output path from `kdu.config.BLD`, because P0.2 does not own
`src/kdu/config.py`. The owner of that file should move the following into it, after
which the constants at the top of `wohngeld.py` and the defaults in
`task_wohngeld.py` can be replaced by catalog lookups.

## DataCatalog entries

```python
DATA_CATALOG.add("wogg_parameters", DATA / "wogg_parameters.csv")
DATA_CATALOG.add("wogg_benchmark", BLD / "wogg_benchmark.parquet")
```

`kdu_gemeinden` already exists and is the other input.

## Legal and temporal constants

D5 forbids year numbers and legal parameters in analysis modules. The values themselves
are stored in `data/wogg_parameters.csv` with their citations, so config only needs the
Rechtsstand declarations and the household-size grid:

```python
ANALYSIS_REFERENCE_DATE = dt.date(2026, 8, 31)  # D2 Analysestichtag
WOGG_HOECHSTBETRAG_IN_FORCE_FROM = dt.date(2025, 1, 1)  # Anlage 1 WoGG
WOGG_COMPONENTS_IN_FORCE_FROM = dt.date(2023, 1, 1)  # § 12 Abs. 6 and 7 WoGG
HOUSEHOLD_SIZES: tuple[int, ...] = (1, 2, 3, 4, 5)
RENT_LEVELS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7)  # Mietenstufen I–VII
```

`HOUSEHOLD_SIZES` and `RENT_LEVELS` are defined in `wohngeld.py` today and should be
imported from config once it carries them; both are also used by P0.1 and P0.3.

## Note on the two Rechtsstand dates

The Höchstbeträge of Anlage 1 were last fortgeschrieben with effect from 2025-01-01
(BGBl. 2024 I Nr. 314); the Klimakomponente and the Heizkostenentlastung still carry
their Wohngeld-Plus wording of 2023-01-01 (BGBl. 2022 I S. 2160). Both are the Fassung
in force on the Analysestichtag 2026-08-31, so the benchmark is a single consistent
Rechtsstand despite the two dates.
