# Config requests from P0.1

`src/kdu/config.py` is owned by another module. This file records what P0.1 needed from
it, what it found there, and what is still missing.

## Already present and used

P0.1 imports all of these from `kdu.config` unchanged:

| Name | Used for |
| --- | --- |
| `ANALYSIS_DATE` | the `analysis_date` column and the report header |
| `LEGAL_VINTAGE.gebietsstand` | the `geometry_vintage` column |
| `HOUSEHOLD_SIZES` | the long table's `household_size` axis |
| `MAIN_SAMPLE_HOUSEHOLD_SIZES` | the D3 balance criterion for `analysis_sample_main` |
| `WOGG_SAFETY_MARKUP`, `WOGG_SAFETY_MARKUP_TOLERANCE` | the D7 ratio detector |
| `ExclusionReason` | reason codes for Gemeinden with no admissible rule |
| `corpus_root()`, `CORPUS_PATHS` | locating the Sciebo corpus (D4) |
| `BLD`, `ROOT`, `DATA` | artefact paths |
| `DATA_CATALOG` entries | `kdu_gemeinden`, `gemeinde_lookup`, `gemeinde_population`, `gemeinden_geojson`, `kdu_municipality_household`, `kdu_policy_region_household`, `analysis_sample_main`, `analysis_sample_extended`, `source_register`, `exclusion_log`, `data_dictionary`, `quality_report` |

## Requested additions

### 1. Catalog entries for six P0.1 artefacts

These are written to `BLD / "<name>"` directly today, because the catalog has no entry
for them. They are inputs to later modules and belong in the catalog:

```python
DATA_CATALOG.add("validation_worklist", BLD / "validation_worklist.csv")
DATA_CATALOG.add("coverage_by_state", BLD / "coverage_by_state.csv")
DATA_CATALOG.add("quality_check_results", BLD / "quality_check_results.csv")
DATA_CATALOG.add("source_match_summary", BLD / "source_match_summary.csv")
DATA_CATALOG.add("wogg_link_disagreements", BLD / "wogg_link_disagreements.csv")
DATA_CATALOG.add("kdu_warn_flags", BLD / "kdu_warn_flags.parquet")
DATA_CATALOG.add("wogg_benchmark", BLD / "wogg_benchmark.parquet")
```

The last one is P0.2's product; P0.1 reads it as a plain path today.

### 2. A second exclusion-reason enum

`ExclusionReason` names the six D3 codes for Gemeinden that hold no admissible rule at
all. P0.1 also has to exclude Gemeinden that hold a rule the *main* sample cannot use,
which is a different situation and must not be conflated with the first in a coverage
table. It is currently defined in `harmonise.MainSampleExclusionReason`:

```python
class MainSampleExclusionReason(StrEnum):
    NUR_NETTOKALTMIETE = "nur_nettokaltmiete"
    HAUSHALTSGROESSEN_UNVOLLSTAENDIG = "haushaltsgroessen_unvollstaendig"
```

### 3. The cold-opex scenario band is derived, not configured

D3 sends the 576 Netto-only Gemeinden to the extended sample under a low / mid / high
kalte-Betriebskosten band, but neither the plan nor the decision log fixes its values.
P0.1 therefore derives the band from the local €/m² figures the KdU documents themselves
publish (the 10th, 50th, and 90th percentile), because §6.3 forbids importing a
nationwide average. If a legal or statistical source for the band is settled later, the
three numbers belong in `config.py` and `harmonise.cold_opex_scenario_band` should read
them from there.

### 4. Quality thresholds

These are defined in `quality.py` as module constants. They are analysis parameters rather than
legal ones, so they may reasonably stay there, but if `config.py` is meant to hold every
threshold they should move:

- `ABSOLUTE_CAP_FLOOR_EUR = 150.0`, `ABSOLUTE_CAP_CEILING_EUR = 2_500.0`
- `OUTLIER_PERCENTILES = (0.005, 0.995)`
- `MIN_RANDOM_SAMPLE = 100`, `MIN_PER_STATE = 2`, `N_EXTREME_DEVIATIONS = 20`
- `NEIGHBOUR_JUMP_THRESHOLD = 0.30`
- `RANDOM_SEED = 20260831`
