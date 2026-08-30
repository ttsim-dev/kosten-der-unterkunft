"""Parse the BA "Wohn- und Kostensituation" workbooks and derive the P1.2 outcomes.

The Statistik der Bundesagentur für Arbeit publishes one Excel workbook per region
and reference month. Every workbook carries the same four data sheets; this module
reads the two that restrict to rented accommodation (§14.1 point 3):

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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pandas as pd

HOUSEHOLD_SIZE_SHEET = "Tabelle 1b HH Miete"
BG_TYPE_SHEET = "Tabelle 2b BG Miete"

HOUSEHOLD_SIZE_CATEGORIES: tuple[str, ...] = (
    "total",
    "1_person",
    "2_persons",
    "3_persons",
    "4_persons",
    "5_persons",
    "6_or_more_persons",
)
"""Column order of `Tabelle 1b HH Miete`, first column being `Insgesamt`."""

BG_TYPE_CATEGORIES: tuple[str, ...] = (
    "total",
    "single",
    "single_parent_1_child",
    "single_parent_2_children",
    "couple_no_child",
    "couple_1_child",
    "couple_2_children",
)
"""Column order of `Tabelle 2b BG Miete`, first column being `Insgesamt`."""

COST_BASES: tuple[str, ...] = ("actual", "recognised")
"""The two cost concepts the BA reports. Neither is a disbursed benefit."""

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
    """Everything about a workbook that is not in its data rows.

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
    """Average a stack of monthly long frames into the §14.1 annual-average variant.

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
    """Append actual and recognised Bruttokaltmiete rows (§14.1 point 5).

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
    region keys are written once per measure rather than once per value. D14 keeps
    the *canonical* table long; committed raw inputs may be wide, as
    `data/kdu_gemeinden.csv` already is.

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


def read_committed_extract(path: Path, breakdown: str) -> pd.DataFrame:
    """Read a committed extract without losing the leading zero of an AGS.

    Region codes are text: `01001` is Flensburg, `1001` is nothing. Type inference
    would read a Kreis-only file as integers, so the whole file is read as text and
    only the value columns are converted back.

    Args:
        path: Path to a `ba_wohnkosten_*_{breakdown}.csv`.
        breakdown: `"household_size"` or `"bg_type"`.

    Returns:
        The wide frame, region codes as text and category values as floats.

    """
    import pyarrow as pa
    import pyarrow.csv

    convert = pyarrow.csv.ConvertOptions(
        column_types=dict.fromkeys(_TEXT_COLUMNS, pa.string())
    )
    frame = pyarrow.csv.read_csv(path, convert_options=convert).to_pandas()
    numeric = [
        column
        for column in (*_categories_for(breakdown), "n_months")
        if column in frame.columns
    ]
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def gather_categories(wide_frame: pd.DataFrame, breakdown: str) -> pd.DataFrame:
    """Invert `spread_categories` and return the long frame.

    Args:
        wide_frame: A committed extract with one column per category.
        breakdown: `"household_size"` or `"bg_type"`.

    Returns:
        The long frame, keyed `region × category × measure`.

    """
    categories = [c for c in _categories_for(breakdown) if c in wide_frame.columns]
    id_vars = [c for c in wide_frame.columns if c not in categories]
    long_frame = wide_frame.melt(
        id_vars=id_vars, value_vars=categories, var_name="category", value_name="value"
    )
    long_frame["breakdown"] = breakdown
    ordered = [*_LONG_COLUMNS, *[c for c in ("n_months",) if c in long_frame.columns]]
    return long_frame[ordered]


def build_ba_outcomes(long_frame: pd.DataFrame) -> pd.DataFrame:
    r"""Derive the three §14.2 validation outcomes.

    For every cost component and basis of measurement:

    - `ba_gap_eur` — $G^{BA} = \overline{C^{actual}} - \overline{C^{recognized}}$
    - `ba_recognition_rate` — $R^{BA} = \overline{C^{recognized}} / \overline{C^{actual}}$
    - `ba_non_recognised_share` — $N^{BA} = 1 - R^{BA}$

    The gap is a difference between two cost concepts. It is not an unmet need and
    not a shortfall in benefits paid, because disbursed benefits are a third,
    lower, quantity that this source does not report.

    Args:
        long_frame: Long frame carrying `actual_*` and `recognised_*` measures.

    Returns:
        A long frame keyed by region, breakdown, category, `cost_component`, `basis`
        and `outcome`.

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
    frames: list[pd.DataFrame] = []
    components = (*COST_COMPONENTS, "bruttokaltmiete")
    for component in components:
        for per in ("per_bg", "per_sqm"):
            actual = f"actual_{component}_eur_{per}"
            recognised = f"recognised_{component}_eur_{per}"
            wide = _spread_measures(long_frame, keys, (actual, recognised))
            if wide is None:
                continue
            gap = wide[actual] - wide[recognised]
            rate = wide[recognised].where(wide[actual] > 0) / wide[actual].where(
                wide[actual] > 0
            )
            block = pd.DataFrame(
                {
                    "ba_gap_eur": gap,
                    "ba_recognition_rate": rate,
                    "ba_non_recognised_share": 1 - rate,
                }
            ).reset_index()
            block["cost_component"] = component
            block["basis"] = per
            frames.append(
                block.melt(
                    id_vars=[*keys, "cost_component", "basis"],
                    var_name="outcome",
                    value_name="value",
                )
            )
    return pd.concat(frames, ignore_index=True)


def build_jobcenter_kreis_crosswalk(regions: pd.DataFrame) -> pd.DataFrame:
    """Map every Jobcenter in the BA release to the Kreise it covers.

    The BA publishes one Kreis workbook and one Jobcenter workbook per territory
    and names the Jobcenter after the territory it serves, but spells the name
    differently in the two files: `Krefeld, Stadt` against `Krefeld`,
    `Mansfeld - Südharz` against `Mansfeld Südharz`. Matching therefore runs in
    three stages — the normalised label, the label with its Stadt/Land/Kreis
    qualifier removed, and finally `JOBCENTER_KREIS_OVERRIDES` for the Jobcenter
    whose name names no single Kreis at all.

    Args:
        regions: Frame with `region_level`, `region_code` and `region_label`,
            holding both `kreis` and `jobcenter` rows.

    Returns:
        One row per Jobcenter and covered Kreis, with `jobcenter_id`,
        `jobcenter_label`, `ags_kreis`, `kreis_label` and `n_policy_regions`.

    """
    regions = regions[["region_level", "region_code", "region_label"]].drop_duplicates()
    kreise = regions.query("region_level == 'kreis'")
    jobcenter = regions.query("region_level == 'jobcenter'")

    by_label = dict(
        zip(
            normalise_region_label(kreise["region_label"]),
            kreise["region_code"],
            strict=True,
        )
    )
    by_core = _unambiguous(
        _strip_region_qualifier(normalise_region_label(kreise["region_label"])),
        kreise["region_code"],
    )
    labels = dict(zip(kreise["region_code"], kreise["region_label"], strict=True))

    records: list[dict[str, object]] = []
    for code, raw_label in zip(
        jobcenter["region_code"], jobcenter["region_label"], strict=True
    ):
        for ags in _kreise_of_jobcenter(code, raw_label, by_label, by_core):
            records.append(
                {
                    "jobcenter_id": code,
                    "jobcenter_label": raw_label,
                    "ags_kreis": ags,
                    "kreis_label": labels.get(ags),
                }
            )
    merged = pd.DataFrame.from_records(records, columns=_CROSSWALK_COLUMNS)
    counts = merged.groupby("jobcenter_id")["ags_kreis"].transform("count")
    return (
        merged.assign(n_policy_regions=counts)
        .sort_values(["jobcenter_id", "ags_kreis"])
        .reset_index(drop=True)
    )


def normalise_region_label(labels: pd.Series) -> pd.Series:
    """Reduce a BA region name to a form both files spell the same way.

    The two files differ only in spacing around hyphens, in abbreviation dots and
    in commas, so folding those away makes most names identical.

    Args:
        labels: Region names as the BA publishes them.

    Returns:
        The folded names, lower case.

    """
    folded = labels.astype("string").str.lower()
    folded = folded.str.replace(r",\s*jc$", "", regex=True)
    folded = folded.str.replace(r"\s*-\s*", "-", regex=True)
    folded = folded.str.replace(r"[.,()]", " ", regex=True)
    return folded.str.replace(r"\s+", " ", regex=True).str.strip()


def check_jobcenter_kreis_stocks(
    crosswalk: pd.DataFrame, long_frame: pd.DataFrame
) -> pd.DataFrame:
    """Compare Jobcenter Bedarfsgemeinschaften against those of the Kreise served.

    Territories tile: a group of Jobcenter serving the same set of Kreise covers
    exactly those Kreise, so the two stocks of Bedarfsgemeinschaften must agree.
    Grouping by the set of Kreise rather than by the single Jobcenter keeps the
    check valid in both directions — one Jobcenter over several Kreise, as in the
    Vorderpfalz, and several Jobcenter over one Kreis, as in Berlin's twelve
    Bezirks-Jobcenter.

    Args:
        crosswalk: Output of `build_jobcenter_kreis_crosswalk`.
        long_frame: Long frame holding `bg_stock` for both region levels.

    Returns:
        One row per territory with `jobcenter_ids`, `ags_kreise`,
        `bg_stock_jobcenter`, `bg_stock_kreise` and their difference, so the caller
        can list the territories that disagree.

    """
    stocks = long_frame.query(
        "measure == 'bg_stock' and breakdown == 'household_size' "
        "and category == 'total'"
    ).set_index("region_code")["value"]
    territory = crosswalk.groupby("jobcenter_id")["ags_kreis"].apply(
        lambda codes: ",".join(sorted(codes))
    )
    grouped = (
        crosswalk.assign(territory=crosswalk["jobcenter_id"].map(territory))
        .groupby("territory")
        .agg(
            jobcenter_ids=("jobcenter_id", lambda ids: ",".join(sorted(set(ids)))),
            ags_kreise=("ags_kreis", lambda codes: ",".join(sorted(set(codes)))),
        )
        .reset_index(drop=True)
    )
    grouped["bg_stock_jobcenter"] = grouped["jobcenter_ids"].map(
        lambda ids: sum(stocks.get(one, float("nan")) for one in ids.split(","))
    )
    grouped["bg_stock_kreise"] = grouped["ags_kreise"].map(
        lambda codes: sum(stocks.get(one, float("nan")) for one in codes.split(","))
    )
    return grouped.assign(
        difference=grouped["bg_stock_jobcenter"] - grouped["bg_stock_kreise"]
    )


JOBCENTER_KREIS_OVERRIDES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        # Jobcenter whose name names no Kreis, or names it in a way no rule folds.
        "t04418": ("15084",),  # Burgenlandkreis, published as Kreis "Burgenland"
        "t04448": ("15087",),  # Mansfeld Südharz
        "t72312": ("09479",),  # Wunsiedel im Fichtelgebirge
        "t72904": ("09573",),  # Fürth, Land — the Landkreis, not the Stadt
        "t73902": ("09373",),  # Neumarkt idOPf
        "t85908": ("09183",),  # Mühldorf am Inn
        # Jobcenter serving several Kreise at once.
        "t52302": ("07311", "07314", "07318", "07338"),  # Vorderpfalz-Ludwigshafen
        "t54308": ("07313", "07337"),  # Landau-Südliche Weinstraße
        "t54312": ("07316", "07332"),  # Deutsche Weinstraße
        "t74302": ("09361", "09371"),  # Amberg-Sulzbach, with Amberg Stadt
        "t75102": ("09363", "09374"),  # Neustadt-Weiden
        "t81512": ("09263", "09278"),  # Straubing-Bogen, with Straubing Stadt
        # The twelve Berlin Bezirks-Jobcenter all serve the single Kreis Berlin.
        "t92202": ("11000",),
        "t92204": ("11000",),
        "t92208": ("11000",),
        "t92210": ("11000",),
        "t95502": ("11000",),
        "t95504": ("11000",),
        "t95506": ("11000",),
        "t95508": ("11000",),
        "t96202": ("11000",),
        "t96204": ("11000",),
        "t96206": ("11000",),
        "t96208": ("11000",),
    }
)
"""Jobcenter whose Kreise the label does not identify, verified by BG stock.

Every entry reproduces the Jobcenter's own stock of Bedarfsgemeinschaften as the
sum over the listed Kreise, which is what `check_jobcenter_kreis_stocks` asserts.
"""

_TEXT_COLUMNS = (
    "reference_month",
    "region_level",
    "region_code",
    "region_label",
    "accommodation_scope",
    "breakdown",
    "category",
    "measure",
)
"""Columns of a committed extract that are text, whatever they look like."""

_CROSSWALK_COLUMNS = ["jobcenter_id", "jobcenter_label", "ags_kreis", "kreis_label"]

_REGION_QUALIFIERS = (
    "stadt",
    "land",
    "landkreis",
    "kreis",
    "hansestadt",
    "landeshauptstadt",
    "eifelkreis",
)


def _kreise_of_jobcenter(
    code: str,
    raw_label: str,
    by_label: dict[str, str],
    by_core: dict[str, str],
) -> tuple[str, ...]:
    if code in JOBCENTER_KREIS_OVERRIDES:
        return JOBCENTER_KREIS_OVERRIDES[code]
    label = normalise_region_label(pd.Series([raw_label])).iloc[0]
    if label in by_label:
        return (by_label[label],)
    core = _strip_region_qualifier(pd.Series([label])).iloc[0]
    if core in by_core:
        return (by_core[core],)
    return ()


def _strip_region_qualifier(labels: pd.Series) -> pd.Series:
    pattern = r"\b(" + "|".join(_REGION_QUALIFIERS) + r")\b"
    stripped = labels.str.replace(pattern, " ", regex=True)
    return stripped.str.replace(r"\s+", " ", regex=True).str.strip(" -")


def _unambiguous(keys: pd.Series, values: pd.Series) -> dict[str, str]:
    """Keep only the keys that identify a single region."""
    counts = keys.value_counts()
    return {
        key: value for key, value in zip(keys, values, strict=True) if counts[key] == 1
    }


def add_jobcenter_id(
    crosswalk: pd.DataFrame, jobcenter_kreis: pd.DataFrame
) -> pd.DataFrame:
    """Fill the Gemeinde crosswalk's `jobcenter_id` from the Kreis it sits in.

    A Gemeinde is served by the Jobcenter of its Kreis, so the id travels down
    from `build_jobcenter_kreis_crosswalk`. Berlin is the one place where that
    fails: twelve Bezirks-Jobcenter serve the single Gemeinde Berlin, and no single
    id describes it, so the column stays missing there.

    Args:
        crosswalk: The Gemeinde crosswalk, keyed `ags`, carrying `ags_kreis`.
        jobcenter_kreis: Output of `build_jobcenter_kreis_crosswalk`.

    Returns:
        The crosswalk with `jobcenter_id` filled wherever the Kreis has exactly one
        Jobcenter.

    """
    per_kreis = jobcenter_kreis.groupby("ags_kreis")["jobcenter_id"].agg(
        ["first", "nunique"]
    )
    unique = per_kreis.loc[per_kreis["nunique"] == 1, "first"]
    filled = crosswalk["ags_kreis"].map(unique).astype("string")
    return crosswalk.assign(jobcenter_id=filled)


def split_validation_samples(
    crosswalk: pd.DataFrame,
    kreisfrei_ags: Sequence[str],
    uniform_caps: Mapping[str, float],
) -> pd.DataFrame:
    """Assign every Jobcenter to the §14.3 main or extended sample.

    The sample is a property of the Jobcenter, not of one of its Kreise, so a
    Jobcenter never straddles the two. It is in the main sample when

    - it covers exactly one policy region, which under D1 means one Kreis — this is
      what a kreisfreie Stadt satisfies by construction, and what all twelve Berlin
      Bezirks-Jobcenter satisfy because they share the single Kreis Berlin; or
    - it covers several Kreise but one KdU rule holds across all of them, meaning
      every one of those Kreise carries a single cap and the caps agree.

    Everything else spans several policy regions with different rules and is
    robustness only.

    Args:
        crosswalk: Output of `build_jobcenter_kreis_crosswalk`.
        kreisfrei_ags: AGS of the kreisfreie Städte, reported as a flag.
        uniform_caps: The single cap of each Kreis that carries exactly one. Kreise
            with several Vergleichsräume, and Kreise with no cap, are absent.

    Returns:
        The crosswalk with `sample` (`"main"` or `"extended"`) and the two boolean
        flags `is_kreisfrei` and `has_uniform_kdu_rule`, both constant within a
        Jobcenter.

    """
    kreisfrei = set(kreisfrei_ags)
    per_jobcenter = crosswalk.groupby("jobcenter_id")["ags_kreis"]
    uniform = per_jobcenter.transform(
        lambda codes: _one_rule_across(codes, uniform_caps)
    )
    all_kreisfrei = per_jobcenter.transform(lambda codes: bool(set(codes) <= kreisfrei))
    result = crosswalk.assign(
        is_kreisfrei=all_kreisfrei.astype(bool),
        has_uniform_kdu_rule=uniform.astype(bool),
    )
    in_main = (result["n_policy_regions"] == 1) | result["has_uniform_kdu_rule"]
    return result.assign(sample=in_main.map({True: "main", False: "extended"}))


def _one_rule_across(codes: pd.Series, uniform_caps: Mapping[str, float]) -> bool:
    """Report whether one KdU rule holds across all Kreise of a Jobcenter."""
    caps = [uniform_caps.get(code) for code in codes]
    if any(cap is None for cap in caps):
        return False
    return len(set(caps)) == 1


def summarise_extended_sample(
    crosswalk: pd.DataFrame,
    kdu_by_kreis: pd.DataFrame,
    cap_column: str,
) -> pd.DataFrame:
    """Describe the within-Jobcenter spread of the KdU cap (§14.3).

    For a Jobcenter spanning several policy regions the cap is not a single number.
    The population-weighted mean, the minimum, the maximum and the within-Jobcenter
    standard deviation replace it, and the plan treats every result built on them
    as robustness.

    Args:
        crosswalk: Output of `split_validation_samples`.
        kdu_by_kreis: One row per Kreis with `ags_kreis`, `population` and the cap.
        cap_column: Name of the cap column in `kdu_by_kreis`.

    Returns:
        One row per Jobcenter in the extended sample with `kdu_mean_weighted`,
        `kdu_min`, `kdu_max` and `kdu_sd_within`.

    """
    extended = crosswalk.query("sample == 'extended'")
    merged = pd.merge(extended, kdu_by_kreis, on="ags_kreis", how="left")

    def _summarise(group: pd.DataFrame) -> pd.Series:
        cap = group[cap_column]
        weight = group["population"]
        usable = cap.notna() & weight.notna() & (weight > 0)
        weighted = (
            (cap[usable] * weight[usable]).sum() / weight[usable].sum()
            if usable.any()
            else float("nan")
        )
        return pd.Series(
            {
                "kdu_mean_weighted": weighted,
                "kdu_min": cap.min(),
                "kdu_max": cap.max(),
                "kdu_sd_within": cap.std(ddof=1),
                "n_policy_regions": len(group),
            }
        )

    return merged.groupby("jobcenter_id", as_index=False).apply(
        _summarise, include_groups=False
    )


def fail_if_measure_names_suggest_payment(measures: pd.Series) -> None:
    """Raise when a measure name blurs recognised costs into disbursed benefits.

    §14.1 point 6 exists because the BA itself warns that benefits actually paid
    fall short of recognised Wohnkosten once income is set off. The source reports
    no payment at all, so a name implying one would be false on its face.

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


_TOP_LEVEL_INDENT = 5
"""Indentation width the BA uses for rows that belong to the cost concept itself."""


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
