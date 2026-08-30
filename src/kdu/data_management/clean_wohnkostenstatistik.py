"""The Bundesagentur statistic on the housing costs of Bedarfsgemeinschaften.

The Bundesagentur für Arbeit publishes, per Jobcenter and household size, the
mean Bruttokaltmiete that Bedarfsgemeinschaften actually pay and the mean
amount their Jobcenter recognises. The difference between the two is money the
household meets out of its Regelbedarf, and it is the only administrative
measure of a local cap binding.

Two properties of the source govern every number taken from it:

- **Neither figure is a benefit paid.** The Bundesagentur reports costs
  recognised, not amounts disbursed; what a household receives is lower still,
  because income is set off against the claim.
- **Both figures are means over all Bedarfsgemeinschaften**, including the
  majority whose costs are recognised in full. A mean shortfall of a few euro
  is consistent with most households losing nothing and a few losing a great
  deal; the source publishes no count of affected households, so no share of
  households may be derived from it.

The statistic is reported by Jobcenter. `district_ags` reaches it through the
crosswalk built here, which matches Jobcenter to the Kreise they serve.
"""

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

import pandas as pd
import pyarrow as pa
import pyarrow.csv

from kdu.joins import merge_without_duplicating

# Digits in the Kreis AGS.
KREIS_AGS_LENGTH = 5

# The category columns of a committed extract, in publication order.
HOUSEHOLD_SIZE_CATEGORIES: Mapping[str, int] = MappingProxyType(
    {
        "1_person": 1,
        "2_persons": 2,
        "3_persons": 3,
        "4_persons": 4,
        "5_persons": 5,
    },
)
"""Category column → household size. Six and more is outside the reported sizes."""

# The measures the validation reads. Everything else the source publishes is
# left in the committed extract rather than carried into the analysis tables.
MEASURES: Mapping[str, str] = MappingProxyType(
    {
        "actual_bruttokaltmiete_eur_per_bg": "actual_bruttokaltmiete",
        "recognised_bruttokaltmiete_eur_per_bg": "recognised_bruttokaltmiete",
        "bg_stock": "bedarfsgemeinschaften",
    },
)

# Columns of `wohnkostenstatistik.parquet`, in order.
WOHNKOSTENSTATISTIK_COLUMNS: tuple[str, ...] = (
    "jobcenter_id",
    "district_ags",
    "household_size",
    "bedarfsgemeinschaften",
    "actual_bruttokaltmiete",
    "recognised_bruttokaltmiete",
    "non_recognised_share",
)

# Columns of a committed extract that are text, whatever they look like.
_TEXT_COLUMNS: tuple[str, ...] = (
    "reference_month",
    "region_level",
    "region_code",
    "region_label",
    "accommodation_scope",
    "measure",
)

_REGION_QUALIFIERS: tuple[str, ...] = (
    "stadt",
    "land",
    "landkreis",
    "kreis",
    "hansestadt",
    "landeshauptstadt",
    "eifelkreis",
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
    },
)
"""Jobcenter whose Kreise their published label does not identify.

Each entry reproduces the Jobcenter's own stock of Bedarfsgemeinschaften as the
sum over the listed Kreise.
"""


def build_wohnkostenstatistik(extract: pd.DataFrame) -> pd.DataFrame:
    """Turn the committed extract into the long table the validation reads.

    Args:
        extract: A committed `ba_wohnkosten_*_household_size.csv`, as read by
            {func}`read_committed_extract`.

    Returns:
        One row per Jobcenter and household size, with
        `WOHNKOSTENSTATISTIK_COLUMNS`. `non_recognised_share` is the share of
        reported housing costs the Jobcenter does not recognise; it is a share
        of euro, never of households.

    """
    crosswalk = build_jobcenter_kreis_crosswalk(extract)
    by_jobcenter = _reshape_measures(extract.query("region_level == 'jobcenter'"))
    sole_kreis = _sole_kreis_per_jobcenter(crosswalk)

    frame = merge_without_duplicating(by_jobcenter, sole_kreis, on=["jobcenter_id"])
    frame["non_recognised_share"] = 1 - (
        frame["recognised_bruttokaltmiete"] / frame["actual_bruttokaltmiete"]
    )
    return (
        frame.loc[:, list(WOHNKOSTENSTATISTIK_COLUMNS)]
        .sort_values(["jobcenter_id", "household_size"])
        .reset_index(drop=True)
    )


def build_jobcenter_kreis_crosswalk(extract: pd.DataFrame) -> pd.DataFrame:
    """Map every Jobcenter in the release to the Kreise it covers.

    The Bundesagentur publishes one Kreis table and one Jobcenter table per
    territory, and names the Jobcenter after the territory it serves — but
    spells the name differently in the two: `Krefeld, Stadt` against `Krefeld`,
    `Mansfeld - Südharz` against `Mansfeld Südharz`. Matching therefore runs in
    three stages: the folded label, the label with its Stadt, Land or Kreis
    qualifier removed, and finally `JOBCENTER_KREIS_OVERRIDES` for the
    Jobcenter whose name identifies no single Kreis.

    Args:
        extract: A committed extract holding both `kreis` and `jobcenter` rows.

    Returns:
        One row per Jobcenter and covered Kreis, with `jobcenter_id`,
        `jobcenter_label`, `district_ags` and `n_districts`.

    """
    regions = extract[
        ["region_level", "region_code", "region_label"]
    ].drop_duplicates()
    kreise = regions.query("region_level == 'kreis'")
    jobcenter = regions.query("region_level == 'jobcenter'")

    by_label = dict(
        zip(
            fold_region_label(kreise["region_label"]),
            kreise["region_code"],
            strict=True,
        ),
    )
    by_core = _unambiguous(
        _strip_region_qualifier(fold_region_label(kreise["region_label"])),
        kreise["region_code"],
    )
    labels = dict(zip(kreise["region_code"], kreise["region_label"], strict=True))

    records = [
        {
            "jobcenter_id": code,
            "jobcenter_label": raw_label,
            "district_ags": district_ags,
            "district_label": labels.get(district_ags),
        }
        for code, raw_label in zip(
            jobcenter["region_code"],
            jobcenter["region_label"],
            strict=True,
        )
        for district_ags in _districts_of_jobcenter(code, raw_label, by_label, by_core)
    ]
    matched = pd.DataFrame.from_records(
        records,
        columns=["jobcenter_id", "jobcenter_label", "district_ags", "district_label"],
    )
    counts = matched.groupby("jobcenter_id")["district_ags"].transform("count")
    return (
        matched.assign(n_districts=counts)
        .sort_values(["jobcenter_id", "district_ags"])
        .reset_index(drop=True)
    )


def fold_region_label(labels: pd.Series) -> pd.Series:
    """Reduce a region name to a form both published tables spell the same way.

    The two tables differ only in spacing around hyphens, in abbreviation dots
    and in commas, so folding those away makes most names identical.

    Args:
        labels: Region names as published.

    Returns:
        The folded names, lower case.

    """
    folded = labels.astype("string").str.lower()
    folded = folded.str.replace(r",\s*jc$", "", regex=True)
    folded = folded.str.replace(r"\s*-\s*", "-", regex=True)
    folded = folded.str.replace(r"[.,()]", " ", regex=True)
    return folded.str.replace(r"\s+", " ", regex=True).str.strip()


def read_committed_extract(path: Path) -> pd.DataFrame:
    """Read a committed extract without losing the leading zero of a region code.

    Region codes are text: `01001` is Flensburg, `1001` is nothing. Type
    inference would read a file of Kreis codes as integers, so every key column
    is read as text and only the category columns are converted back.

    Args:
        path: Path to a `ba_wohnkosten_*_household_size.csv`.

    Returns:
        The wide frame, region codes as text and category values as floats.

    """
    convert = pyarrow.csv.ConvertOptions(
        column_types=dict.fromkeys(_TEXT_COLUMNS, pa.string()),
    )
    frame = pyarrow.csv.read_csv(path, convert_options=convert).to_pandas()
    for column in HOUSEHOLD_SIZE_CATEGORIES:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def _reshape_measures(extract: pd.DataFrame) -> pd.DataFrame:
    """Stack the category columns and put the wanted measures side by side."""
    present = [
        column for column in HOUSEHOLD_SIZE_CATEGORIES if column in extract.columns
    ]
    long_frame = extract.melt(
        id_vars=["region_code", "measure"],
        value_vars=present,
        var_name="category",
        value_name="value",
    )
    long_frame = long_frame[long_frame["measure"].isin(MEASURES)]
    long_frame["household_size"] = long_frame["category"].map(
        dict(HOUSEHOLD_SIZE_CATEGORIES),
    )
    long_frame["measure"] = long_frame["measure"].map(dict(MEASURES))

    wide = (
        long_frame.set_index(["region_code", "household_size", "measure"])["value"]
        .unstack("measure")
        .reset_index()
        .rename(columns={"region_code": "jobcenter_id"})
    )
    wide.columns.name = None
    return wide.reindex(
        columns=["jobcenter_id", "household_size", *MEASURES.values()],
    )


def _sole_kreis_per_jobcenter(crosswalk: pd.DataFrame) -> pd.DataFrame:
    """Keep the Jobcenter that serve exactly one Kreis, with that Kreis.

    A Jobcenter covering several Kreise has no single `district_ags`, so its
    rows carry a missing one rather than an arbitrary choice among them.
    """
    sole = crosswalk.query("n_districts == 1")
    return sole[["jobcenter_id", "district_ags"]].reset_index(drop=True)


def _districts_of_jobcenter(
    code: str,
    raw_label: str,
    by_label: dict[str, str],
    by_core: dict[str, str],
) -> tuple[str, ...]:
    if code in JOBCENTER_KREIS_OVERRIDES:
        return JOBCENTER_KREIS_OVERRIDES[code]
    label = fold_region_label(pd.Series([raw_label])).iloc[0]
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
        key: value
        for key, value in zip(keys, values, strict=True)
        if counts[key] == 1
    }
