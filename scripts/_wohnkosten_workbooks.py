"""Parse the BA "Wohn- und Kostensituation" workbooks into the committed extract.

The Statistik der Bundesagentur für Arbeit publishes one Excel workbook per region
and reference month. Every workbook carries the same four data sheets; this module
reads the two that restrict to rented accommodation:

- `Tabelle 1b HH Miete` — by size of the Haushaltsgemeinschaft
- `Tabelle 2b BG Miete` — by Bedarfsgemeinschaft type

Two properties of the source drive the naming in this module:

- The BA reports *actual* and *recognised* Kosten der Unterkunft. Neither is the
  amount a Bedarfsgemeinschaft is paid: disbursed benefits fall below recognised
  costs whenever income is set off against the claim. No measure name in this
  module may therefore suggest a payment, and `fail_if_measure_names_suggest_payment`
  enforces that.
- Some Träger book the laufende Betriebskosten into the Unterkunftskosten instead of
  recording them separately (source footnote 7). The three cost components are kept
  apart as the source reports them, and Bruttokaltmiete is formed as their sum
  Unterkunftskosten + kalte Betriebskosten, which is invariant to that booking
  choice.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

HOUSEHOLD_SIZE_SHEET = "Tabelle 1b HH Miete"
BG_TYPE_SHEET = "Tabelle 2b BG Miete"

# Column order of `Tabelle 1b HH Miete`, first column being `Insgesamt`.
HOUSEHOLD_SIZE_CATEGORIES: tuple[str, ...] = (
    "total",
    "1_person",
    "2_persons",
    "3_persons",
    "4_persons",
    "5_persons",
    "6_or_more_persons",
)

# Column order of `Tabelle 2b BG Miete`, first column being `Insgesamt`.
BG_TYPE_CATEGORIES: tuple[str, ...] = (
    "total",
    "single",
    "single_parent_1_child",
    "single_parent_2_children",
    "couple_no_child",
    "couple_1_child",
    "couple_2_children",
)

# The two cost concepts the BA reports. Neither is a disbursed benefit.
COST_BASES: tuple[str, ...] = ("actual", "recognised")

COST_COMPONENTS: tuple[str, ...] = (
    "kdu_total",
    "unterkunftskosten",
    "kalte_betriebskosten",
    "heizkosten",
)

_FORBIDDEN_MEASURE_SUBSTRINGS: tuple[str, ...] = (
    "payment",
    "paid",
    "disbursed",
    "benefit",
    "leistung",
    "zahlung",
    "auszahlung",
)


@dataclass(frozen=True)
class BaWorkbookIdentity:
    """The region and reference month one workbook describes.

    Attributes are carried into every parsed row so the long table stays keyed.
    """

    region_level: str
    """`"kreis"` or `"jobcenter"`."""
    region_code: str
    """Five-digit AGS for a Kreis, BA Dienststellennummer for a Jobcenter."""
    region_label: str
    """Region name exactly as the BA publishes it."""
    reference_month: str
    """Reference month as `YYYY-MM`."""


def load_ba_workbook(path: Path, identity: BaWorkbookIdentity) -> pd.DataFrame:
    """Read both Mietunterkünfte sheets of one BA workbook into a long frame.

    Args:
        path: Path to the downloaded `.xlsx` workbook.
        identity: Region and reference month the workbook describes.

    Returns:
        The parsed long frame including the derived Bruttokaltmiete rows.

    """
    import openpyxl

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        frames = [
            parse_ba_sheet(
                list(workbook[sheet].iter_rows(values_only=True)), breakdown, identity
            )
            for sheet, breakdown in (
                (HOUSEHOLD_SIZE_SHEET, "household_size"),
                (BG_TYPE_SHEET, "bg_type"),
            )
        ]
    finally:
        workbook.close()
    return add_bruttokaltmiete(pd.concat(frames, ignore_index=True))


def average_over_months(
    long_frames: Sequence[pd.DataFrame], label: str
) -> pd.DataFrame:
    """Average one long frame per month into the annual-average variant.

    Args:
        long_frames: One long frame per reference month, same regions and measures.
        label: Value to write into `reference_month`, e.g. `"2025-05..2026-04"`.

    Returns:
        A long frame of the same shape carrying the mean and an `n_months` column
        counting the months that actually contributed a value to each cell.

    """
    stacked = pd.concat(long_frames, ignore_index=True)
    keys = [
        "region_level",
        "region_code",
        "region_label",
        "accommodation_scope",
        "breakdown",
        "category",
        "measure",
    ]
    grouped = stacked.groupby(keys, as_index=False, dropna=False)["value"].agg(
        ["mean", "count"]
    )
    grouped = grouped.rename(columns={"mean": "value", "count": "n_months"})
    grouped.insert(0, "reference_month", label)
    return grouped[[*_LONG_COLUMNS, "n_months"]]


def parse_ba_sheet(
    rows: Sequence[Sequence[Any]],
    breakdown: str,
    identity: BaWorkbookIdentity,
) -> pd.DataFrame:
    """Parse one BA sheet into long rows.

    Args:
        rows: The sheet's cell values, row by row, first column being the row label.
        breakdown: `"household_size"` or `"bg_type"`; selects the column labels.
        identity: Region and reference month of the workbook.

    Returns:
        A long frame with one row per measure and category, columns
        `reference_month`, `region_level`, `region_code`, `region_label`,
        `accommodation_scope`, `breakdown`, `category`, `measure`, `value`.

    """
    categories = _categories_for(breakdown)
    records: list[dict[str, Any]] = []
    context = _RowContext()
    for row in rows:
        label = _row_label(row)
        if label is None:
            continue
        measure = context.resolve(label)
        if measure is None:
            continue
        for position, category in enumerate(categories, start=1):
            records.append(
                {
                    "reference_month": identity.reference_month,
                    "region_level": identity.region_level,
                    "region_code": identity.region_code,
                    "region_label": identity.region_label,
                    "accommodation_scope": "miete",
                    "breakdown": breakdown,
                    "category": category,
                    "measure": measure,
                    "value": _to_float(row[position] if position < len(row) else None),
                }
            )
    frame = pd.DataFrame.from_records(records, columns=_LONG_COLUMNS)
    fail_if_measure_names_suggest_payment(frame["measure"])
    return frame


def add_bruttokaltmiete(long_frame: pd.DataFrame) -> pd.DataFrame:
    """Append actual and recognised Bruttokaltmiete rows.

    Bruttokaltmiete is Unterkunftskosten plus kalte Betriebskosten, formed
    separately for the actual and the recognised cost concept and separately for
    the per-BG and the per-square-metre basis. Heizkosten are never included.

    Args:
        long_frame: Long frame as returned by `parse_ba_sheet`.

    Returns:
        The input frame with the derived Bruttokaltmiete rows appended.

    """
    keys = [
        "reference_month",
        "region_level",
        "region_code",
        "region_label",
        "accommodation_scope",
        "breakdown",
        "category",
    ]
    derived: list[pd.DataFrame] = [long_frame]
    for basis in COST_BASES:
        for per in ("per_bg", "per_sqm"):
            cold = f"{basis}_unterkunftskosten_eur_{per}"
            running = f"{basis}_kalte_betriebskosten_eur_{per}"
            wide = _spread_measures(long_frame, keys, (cold, running))
            if wide is None:
                continue
            total = (wide[cold] + wide[running]).rename("value").reset_index()
            total["measure"] = f"{basis}_bruttokaltmiete_eur_{per}"
            derived.append(total[_LONG_COLUMNS])
    return pd.concat(derived, ignore_index=True)


def spread_categories(long_frame: pd.DataFrame, breakdown: str) -> pd.DataFrame:
    """Reshape one breakdown of the long frame into the committed file layout.

    The committed extract puts the categories of a breakdown side by side, so the
    region keys are written once per measure rather than once per value. The
    canonical tables in `bld/data/` stay long; a committed raw input may be wide,
    as `data/kdu_gemeinden.csv` already is.

    Args:
        long_frame: Long frame as returned by `load_ba_workbook`.
        breakdown: `"household_size"` or `"bg_type"`.

    Returns:
        One row per region and measure, with one column per category.

    """
    categories = _categories_for(breakdown)
    keys = [
        "reference_month",
        "region_level",
        "region_code",
        "region_label",
        "accommodation_scope",
        "measure",
    ]
    part = long_frame.query("breakdown == @breakdown")
    wide = part.set_index([*keys, "category"])["value"].unstack("category")
    wide = wide.reindex(columns=list(categories))
    if "n_months" in part.columns:
        # A category withheld in some months has its own count. The row keeps the
        # largest, the number of months in which the region reported the measure
        # at all.
        wide.insert(0, "n_months", part.groupby(keys, dropna=False)["n_months"].max())
    wide = wide.reset_index()
    wide.columns.name = None
    return wide.sort_values([*keys]).reset_index(drop=True)


def fail_if_measure_names_suggest_payment(measures: pd.Series) -> None:
    """Raise when a measure name blurs recognised costs into disbursed benefits.

    The BA itself warns that benefits actually paid fall short of recognised
    Wohnkosten once income is set off. The source reports no payment at all, so a
    name implying one would be false on its face.

    Args:
        measures: Measure names to check.

    Raises:
        ValueError: If any name contains a payment word.

    """
    lowered = measures.astype(str).str.lower()
    for token in _FORBIDDEN_MEASURE_SUBSTRINGS:
        offending = sorted(set(measures[lowered.str.contains(token, regex=False)]))
        if offending:
            msg = (
                f"measure names must not suggest disbursed benefits, but "
                f"{offending} contain {token!r}. The BA reports actual and "
                f"recognised costs only; benefits paid are lower because income "
                f"is set off against the claim."
            )
            raise ValueError(msg)


def _spread_measures(
    long_frame: pd.DataFrame, keys: list[str], measures: tuple[str, ...]
) -> pd.DataFrame | None:
    """Put the named measures side by side, one row per key combination.

    `pivot_table` would expand the key columns to their full cartesian product,
    inventing rows for combinations the source never reports — a household-size
    category under the Bedarfsgemeinschaft-type breakdown, for instance. Setting
    the index and unstacking keeps only the combinations that exist.
    """
    parts = long_frame[long_frame["measure"].isin(measures)]
    if parts.empty:
        return None
    wide = parts.set_index([*keys, "measure"])["value"].unstack("measure")
    if any(measure not in wide.columns for measure in measures):
        return None
    return wide


_LONG_COLUMNS = [
    "reference_month",
    "region_level",
    "region_code",
    "region_label",
    "accommodation_scope",
    "breakdown",
    "category",
    "measure",
    "value",
]

_STANDALONE_MEASURES: dict[str, str] = {
    "Bestand Bedarfsgemeinschaften (BG)": "bg_stock",
    "Bestand BG mit laufenden anerkannten Kosten der Unterkunft": (
        "bg_stock_with_recognised_kdu"
    ),
    "Bestand BG mit lfd. anerk. Kosten der Unterkunft u. Angaben zur Wohnfläche": (
        "bg_stock_with_recognised_kdu_and_floor_area"
    ),
    "durchschnittliche Wohnfläche pro BG 4)": "mean_floor_area_sqm_per_bg",
    "durchschnittliche Wohnfläche pro Person in der Haushaltsgemeinschaft 4)": (
        "mean_floor_area_sqm_per_person"
    ),
    "durchschnittliche Wohnfläche pro Person in der Bedarfsgemeinschaft 4)": (
        "mean_floor_area_sqm_per_person"
    ),
}

_COST_HEADS: dict[str, str] = {
    "Laufende tatsächliche Kosten der Unterkunft insgesamt": "actual",
    "Laufende anerkannte Kosten der Unterkunft insgesamt": "recognised",
}

_COST_COMPONENT_LABELS: dict[str, str] = {
    "dav. Unterkunftskosten 7)": "unterkunftskosten",
    "dav. laufende Betriebskosten 7)": "kalte_betriebskosten",
    "dav. Heizkosten": "heizkosten",
}

_PER_LABELS: dict[str, str] = {
    "pro BG": "per_bg",
    "pro qm": "per_sqm",
    "pro Person in der Haushaltsgemeinschaft": "per_person",
    "pro Person in der Bedarfsgemeinschaft": "per_person",
}


class _RowContext:
    """Resolve an indented BA row label into a flat measure name.

    The sheets nest `pro BG` / `pro qm` rows under the cost concept and, one level
    deeper, under the cost component. Indentation is the only marker of that
    nesting, so the label's leading whitespace decides which parent applies.
    """

    def __init__(self) -> None:
        self._basis: str | None = None
        self._component: str | None = None

    def resolve(self, raw_label: str) -> str | None:
        depth = len(raw_label) - len(raw_label.lstrip(" "))
        label = raw_label.strip()
        if label in _STANDALONE_MEASURES:
            return _STANDALONE_MEASURES[label]
        if label in _COST_HEADS:
            self._basis = _COST_HEADS[label]
            self._component = "kdu_total"
            return None
        if label in _COST_COMPONENT_LABELS:
            self._component = _COST_COMPONENT_LABELS[label]
            return None
        if label in _PER_LABELS and self._basis is not None:
            component = "kdu_total" if depth <= _TOP_LEVEL_INDENT else self._component
            return f"{self._basis}_{component}_eur_{_PER_LABELS[label]}"
        return None


# Indentation width the BA uses for rows that belong to the cost concept itself.
_TOP_LEVEL_INDENT = 5


def _categories_for(breakdown: str) -> tuple[str, ...]:
    if breakdown == "household_size":
        return HOUSEHOLD_SIZE_CATEGORIES
    if breakdown == "bg_type":
        return BG_TYPE_CATEGORIES
    msg = f"breakdown must be 'household_size' or 'bg_type', not {breakdown!r}"
    raise ValueError(msg)


def _row_label(row: Sequence[Any]) -> str | None:
    if not row:
        return None
    first = row[0]
    if not isinstance(first, str):
        return None
    return first


def _to_float(cell: Any) -> float:
    """Convert a BA cell to a float, honouring the source's own value marks.

    - `*` marks a value withheld under statistical confidentiality: missing.
    - `-` and `–` mark "nothing to report": zero.
    - `x` and an empty cell mark "not applicable": missing.
    """
    if cell is None:
        return float("nan")
    if isinstance(cell, (int, float)):
        return float(cell)
    text = str(cell).strip()
    if text in {"-", "–", "—"}:
        return 0.0
    if text in {"", "*", "x", "X", "."}:
        return float("nan")
    return float(text.replace(".", "").replace(",", "."))
