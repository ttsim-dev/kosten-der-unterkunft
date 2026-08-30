# Config requests — BA Wohnkosten and Zensus 2022

Requests from the P1.2 / P1.3 external-data work to the agent that owns
`src/kdu/config.py` and to the agent that owns `pyproject.toml` / `pixi.lock`.
Nothing here has been applied by the requesting agent.

## Dependency

`openpyxl` is imported by `src/kdu/data_management/ba.py`, by
`scripts/fetch_ba_wohnkosten.py` and by `scripts/fetch_zensus_mieten.py` to read
the source `.xlsx` workbooks. It is already present in the solved environment as a
transitive dependency, but it is used directly and should be declared:

```toml
[tool.pixi.dependencies]
openpyxl = "*"
```

Add it, run `pixi lock`, and commit `pyproject.toml` and `pixi.lock` together.

## DataCatalog entries

The two new task modules address their inputs and outputs by path today, because
`src/kdu/config.py` belongs to another agent. Register them as follows and the
tasks can be switched over:

```python
# committed inputs
DATA_CATALOG.add("ba_wohnkosten_household_size",
                 DATA / "ba_wohnkosten" / "ba_wohnkosten_202604_household_size.csv")
DATA_CATALOG.add("ba_wohnkosten_bg_type",
                 DATA / "ba_wohnkosten" / "ba_wohnkosten_202604_bg_type.csv")
DATA_CATALOG.add("ba_wohnkosten_annual_household_size",
                 DATA / "ba_wohnkosten"
                 / "ba_wohnkosten_annual_mean_202505_202604_household_size.csv")
DATA_CATALOG.add("ba_wohnkosten_annual_bg_type",
                 DATA / "ba_wohnkosten"
                 / "ba_wohnkosten_annual_mean_202505_202604_bg_type.csv")
DATA_CATALOG.add("ba_download_manifest",
                 DATA / "ba_wohnkosten" / "ba_download_manifest.csv")
DATA_CATALOG.add("zensus_rents_raw",
                 DATA / "zensus" / "zensus2022_nettokaltmiete_gemeinden.csv")
DATA_CATALOG.add("zensus_download_manifest",
                 DATA / "zensus" / "zensus_download_manifest.csv")

# generated outputs
DATA_CATALOG.add("ba_wohnkosten_long", BLD / "ba_wohnkosten_long.parquet")
DATA_CATALOG.add("ba_wohnkosten_annual_mean_long",
                 BLD / "ba_wohnkosten_annual_mean_long.parquet")
DATA_CATALOG.add("ba_validation_outcomes", BLD / "ba_validation_outcomes.parquet")
DATA_CATALOG.add("jobcenter_kreis_crosswalk",
                 BLD / "jobcenter_kreis_crosswalk.parquet")
DATA_CATALOG.add("jobcenter_kreis_stock_check",
                 BLD / "jobcenter_kreis_stock_check.parquet")
DATA_CATALOG.add("zensus_rents_all_levels", BLD / "zensus_rents_all_levels.parquet")
DATA_CATALOG.add("zensus_rents_gemeinden", BLD / "zensus_rents_gemeinden.parquet")
```

## Constants

D5 keeps every temporal and legal parameter in one `config.py` block. These three
are currently defined in `src/kdu/data_management/task_ba.py` and
`scripts/fetch_ba_wohnkosten.py` and belong there instead:

```python
BA_REFERENCE_MONTH = "2026-04"
"""Latest BA month published at or before the D2 Analysestichtag 2026-08-31.

The Statistik der Bundesagentur für Arbeit publishes the Wohn- und Kostensituation
with roughly a four-month lag; April 2026 was the newest release on 2026-08-27, and
May 2026 returned 404.
"""

BA_ANNUAL_MEAN_WINDOW = ("2025-05", "2026-04")
"""Twelve-month window behind the §14.1 annual-average robustness variant."""

ZENSUS_REFERENCE_DATE = "2022-05-15"
"""Stichtag of the Zensus 2022."""
```

## Source register

Every downloaded file is recorded with its URL, retrieval date, byte size and
SHA-256 in `data/ba_wohnkosten/ba_download_manifest.csv` and
`data/zensus/zensus_download_manifest.csv`. Whoever assembles
`source_register.csv` can read both directly; the columns are
`source`, `source_url`, `retrieved_date`, `n_bytes`, `sha256` plus the region and
reference-month keys.

## `jobcenter_id` in the Gemeinde crosswalk

`build_crosswalk` in `src/kdu/data_management/crosswalk.py` leaves `jobcenter_id`
as a typed placeholder and its docstring says the BA module fills it. The filler is
`kdu.data_management.ba.add_jobcenter_id(crosswalk, jobcenter_kreis)`. Because two
pytask tasks may not write the same product, `task_ba_jobcenter_crosswalk`
currently writes the filled table to
`bld/municipality_crosswalk_with_jobcenter.parquet` instead.

The owner of `task_crosswalk.py` should call `add_jobcenter_id` there, taking
`bld/jobcenter_kreis_crosswalk.parquet` as its second input, after which the extra
product and its `TODO` in `task_ba.py` can go. The column is filled wherever the
Kreis has exactly one Jobcenter and stays missing for Berlin, whose single Gemeinde
is served by twelve Bezirks-Jobcenter.

## Results manifest

Nothing here is registered in `results_manifest.csv`. Every output of these two
task modules is an intermediate dataset, and §5.2 reserves the manifest for
figures and tables — the presented output, with an interpretation and a
limitation. The P1.2 and P1.3 figures that will be built on these datasets are the
entries that belong in it.
