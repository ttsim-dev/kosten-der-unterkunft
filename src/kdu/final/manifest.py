"""Register every figure and table in `bld/results_manifest.csv` (§5.2).

Every figure and table the project produces must be traceable back to the
dataset and script that made it, and must carry a one-line interpretation and
the single limitation a reader most needs to know. That is what
`register_result` records.

Call it once per output, right after writing the file:

```python
from kdu.config import FIGURES
from kdu.final.manifest import register_result

figure.write_html(FIGURES / "fig_proxy_error_h1.html")
register_result(
    filename="fig_proxy_error_h1.html",
    analysis_module="P0.3",
    dataset="analysis_sample_main.parquet",
    script="src/kdu/final/task_figures_proxy_error.py",
    interpretation=(
        "The median single-person KdU cap sits 10 % above the Wohngeld "
        "Höchstbetrag, with a spread of well over 100 € within Mietenstufen."
    ),
    limitation=(
        "12.9 % of Gemeinden are WoGG-linked, where the 10 % is a definitional "
        "identity rather than an empirical finding."
    ),
)
```

Rows are keyed on `filename`: re-registering an output replaces its row, so
re-running a task never duplicates an entry.
"""

import csv
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from kdu.config import ANALYSIS_DATE, catalog_path

# The seven §5.2 fields, in the order they appear in the CSV.
MANIFEST_COLUMNS: tuple[str, ...] = (
    "filename",
    "analysis_module",
    "dataset",
    "script",
    "created",
    "interpretation",
    "limitation",
)


@dataclass(frozen=True)
class ResultEntry:
    """One row of `results_manifest.csv`."""

    filename: str
    """Name of the figure or table file, without directories."""
    analysis_module: str
    """Module that produced it, for example `"P0.3"` or `"P1.2"`."""
    dataset: str
    """Underlying dataset, for example `"analysis_sample_main.parquet"`."""
    script: str
    """Repository-relative path of the script that wrote the file."""
    interpretation: str
    """One sentence on what the output shows."""
    limitation: str
    """The single caveat a reader most needs alongside it."""
    created: date = field(default_factory=lambda: ANALYSIS_DATE)
    """Creation date; defaults to the Analysestichtag so reruns stay stable."""

    def as_row(self) -> dict[str, str]:
        """Render the entry as the CSV row `MANIFEST_COLUMNS` describes."""
        values = asdict(self)
        values["created"] = self.created.isoformat()
        return {column: str(values[column]) for column in MANIFEST_COLUMNS}


def register_result(
    filename: str,
    analysis_module: str,
    dataset: str,
    script: str,
    interpretation: str,
    limitation: str,
    created: date | None = None,
    manifest_path: Path | None = None,
) -> Path:
    """Record one figure or table in the results manifest.

    Args:
        filename: Name of the output file, without directories.
        analysis_module: Producing module, for example `"P0.3"`.
        dataset: Underlying dataset the output was computed from.
        script: Repository-relative path of the producing script.
        interpretation: One sentence on what the output shows.
        limitation: The single caveat a reader most needs alongside it.
        created: Creation date; defaults to the Analysestichtag.
        manifest_path: Manifest to write; defaults to the catalog entry.

    Returns:
        The path of the manifest that was written.

    """
    entry = ResultEntry(
        filename=filename,
        analysis_module=analysis_module,
        dataset=dataset,
        script=script,
        interpretation=interpretation,
        limitation=limitation,
        created=created if created is not None else ANALYSIS_DATE,
    )
    path = manifest_path if manifest_path is not None else _default_manifest_path()
    write_manifest(upsert(read_manifest(path), entry), path)
    return path


def read_manifest(path: Path) -> pd.DataFrame:
    """Read the manifest, returning an empty frame if it does not exist yet."""
    if not path.exists():
        return pd.DataFrame(columns=list(MANIFEST_COLUMNS), dtype="string")
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, engine="pyarrow")
    return frame.reindex(columns=list(MANIFEST_COLUMNS), fill_value="")


def upsert(manifest: pd.DataFrame, entry: ResultEntry) -> pd.DataFrame:
    """Add `entry`, replacing any row already registered under its filename."""
    kept = manifest.loc[manifest["filename"] != entry.filename]
    row = pd.DataFrame([entry.as_row()], columns=list(MANIFEST_COLUMNS))
    return (
        pd.concat([kept, row], ignore_index=True)
        .sort_values(["analysis_module", "filename"])
        .reset_index(drop=True)
    )


def write_manifest(manifest: pd.DataFrame, path: Path) -> None:
    """Write the manifest, quoting every field so prose commas survive."""
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest.loc[:, list(MANIFEST_COLUMNS)].to_csv(
        path,
        index=False,
        quoting=csv.QUOTE_ALL,
    )


def _default_manifest_path() -> Path:
    return catalog_path("results_manifest")
