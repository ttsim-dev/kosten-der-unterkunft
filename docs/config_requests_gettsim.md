# Config requests — P0.7 (GETTSIM simulation)

`src/kdu/simulation/kdu_cap.py` is deliberately parameter-free: it takes caps, rents and
heating as arguments and holds no year and no legal value, as D5 requires. The
Rechtsstand constants below are currently defined in `scripts/gettsim_spike.py` and must move
into `src/kdu/config.py` before any `src/kdu/simulation/task_*.py` is written. The owner
of `config.py` should add them.

## Rechtsstand and GETTSIM constants

```python
GETTSIM_POLICY_DATE = "2026-08-31"  # D2 Analysestichtag, as the ISO string gettsim takes
MINDESTLOHN_EUR_PER_HOUR = 13.90  # §12.6; BGBl. 2025 I Nr. 268, in force 2026-01-01
WEEKS_PER_MONTH = 4.33  # §12.6's ΔH = Δy* / (WEEKS_PER_MONTH × Mindestlohn)
```

`MINDESTLOHN_EUR_PER_HOUR` duplicates a value GETTSIM already carries at
`sozialversicherung__mindestlohn`. Reading it out of the policy environment instead of
declaring it would be better and keeps a single source of truth; declaring it in config
is acceptable only with the BGBl. citation kept next to it.

## Income grid (§12.4)

```python
INCOME_GRID_STEP_EUR = 25
INCOME_GRID_MAX_EUR = 8_000
INCOME_GRID_CONSECUTIVE_ZEROS_TO_STOP = 12
BISECTION_TOLERANCE_EUR = 1.0  # D10: locate y* to €1
```

## Heating assumption (§12.3)

Held constant across scenarios by construction. The level itself comes from the BA
Wohnkostendaten and is not yet fixed; when it is, it belongs in config, not in a
simulation module:

```python
HEIZKOSTEN_M_EUR: Mapping[int, float]  # by household size, BA reference month ≤ 2026-08
HEIZKOSTEN_SENSITIVITY_FACTORS = (0.75, 1.0, 1.25)
```

## DataCatalog entries

Not yet needed — P0.7 has no task file. When it gets one:

```python
DATA_CATALOG.add("simulation_cells", BLD / "simulation_cells.parquet")
DATA_CATALOG.add("simulation_results", BLD / "simulation_results.parquet")
```

## Note

`GETTSIM_UNTERKUNFTSKOSTEN_COLUMN` stays in `kdu_cap.py` and should **not** move to
config. It is not a legal or temporal parameter; it is the name of the GETTSIM node the
module overrides, and it belongs next to the code that explains why the override exists
(see `docs/gettsim_audit.md` §2).
