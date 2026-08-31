"""Fetch the BA "Wohn- und Kostensituation" workbooks once and commit the extract.

Run this by hand, not from the pytask graph:

```bash
pixi run python scripts/fetch_ba_wohnkosten.py
```

The Statistik der Bundesagentur für Arbeit publishes one workbook per region and
reference month behind an Einzelheftsuche listing. Downloading all of them is a few
thousand HTTP requests and roughly 1.5 GB, so the workbooks themselves stay out of
the repository. What is committed instead is:

- `data/ba_wohnkosten/ba_wohnkosten_<month>.csv` — the parsed long extract for the
  reference month, Kreise and Jobcenter
- `data/ba_wohnkosten/ba_wohnkosten_annual_mean_<from>_<to>.csv` — the twelve-month
  average per Kreis, carried as robustness against a single reference month
- `data/ba_wohnkosten/ba_download_manifest.csv` — source URL, retrieval date, byte
  size and SHA-256 of every workbook that went into the two extracts, so any file
  can be fetched again and checked against what was parsed here
- `data/ba_wohnkosten/kdu-d-0-<month>-xlsx.xlsx` — the national workbook kept
  verbatim, because its `Hinweis_SGB-II_Wohnkosten` sheet carries the BA's own
  methodological notes
"""

import csv
import datetime as dt
import hashlib
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from _wohnkosten_workbooks import (
    BaWorkbookIdentity,
    average_over_months,
    load_ba_workbook,
    spread_categories,
)

REFERENCE_MONTH = "202604"
"""Latest month published at or before the 2026-08-31 Analysestichtag."""

ANNUAL_MEAN_MONTHS: tuple[str, ...] = (
    "202505",
    "202506",
    "202507",
    "202508",
    "202509",
    "202510",
    "202511",
    "202512",
    "202601",
    "202602",
    "202603",
    "202604",
)

LISTING_URL = (
    "https://statistik.arbeitsagentur.de/SiteGlobals/Forms/Suche/"
    "Einzelheftsuche_Formular.html?topic_f=kdu-kdu&gtp=15084_list%253D{page}"
)
FILE_URL = (
    "https://statistik.arbeitsagentur.de/Statistikdaten/Detail/{month}/iiia7/"
    "kdu-kdu/kdu-{code}-0-{month}-xlsx.xlsx?__blob=publicationFile&v=1"
)

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "ba_wohnkosten"
CACHE_DIR = ROOT / "bld" / "ba_downloads"

_LISTING_ITEM = re.compile(
    r'<a href="(/Statistikdaten/Detail/[^"]+?\.xlsx)[^"]*"[^>]*>\s*'
    r'<h3 class="withHeader">\s*(.*?)</h3>',
    re.DOTALL,
)
_FILE_CODE = re.compile(r"/kdu-([^/]+?)-0-\d{6}-xlsx\.xlsx")
_TAGS = re.compile(r"<[^>]+>")


def main() -> None:
    """Download, parse and write every committed BA artefact."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    retrieved = dt.date.today().isoformat()

    regions = list_regions(REFERENCE_MONTH)
    kreise = [r for r in regions if r[0] == "kreis"]
    jobcenter = [r for r in regions if r[0] == "jobcenter"]
    print(f"{len(kreise)} Kreise and {len(jobcenter)} Jobcenter for {REFERENCE_MONTH}")

    manifest: list[dict[str, object]] = []

    reference = _parse_month(regions, REFERENCE_MONTH, retrieved, manifest)
    _write_extract(reference, f"ba_wohnkosten_{REFERENCE_MONTH}")

    monthly = [
        _parse_month(kreise, month, retrieved, manifest)
        for month in ANNUAL_MEAN_MONTHS
        if month != REFERENCE_MONTH
    ]
    monthly.append(reference.query("region_level == 'kreis'"))
    window = f"{ANNUAL_MEAN_MONTHS[0]}_{ANNUAL_MEAN_MONTHS[-1]}"
    annual = average_over_months(monthly, window.replace("_", ".."))
    _write_extract(annual, f"ba_wohnkosten_annual_mean_{window}")

    national_url = FILE_URL.format(month=REFERENCE_MONTH, code="d")
    national = CACHE_DIR / f"kdu-d-0-{REFERENCE_MONTH}-xlsx.xlsx"
    payload = _download(national_url, national)
    (DATA_DIR / national.name).write_bytes(payload)
    manifest.append(
        _manifest_row(
            "deutschland",
            "d",
            "Deutschland",
            REFERENCE_MONTH,
            national_url,
            payload,
            retrieved,
        )
    )

    manifest_path = DATA_DIR / "ba_download_manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest[0]))
        writer.writeheader()
        writer.writerows(manifest)
    print(f"wrote {manifest_path} ({len(manifest):,} files)")


def _write_extract(long_frame: pd.DataFrame, stem: str) -> None:
    for breakdown in ("household_size", "bg_type"):
        wide = spread_categories(long_frame, breakdown)
        path = DATA_DIR / f"{stem}_{breakdown}.csv"
        wide.to_csv(path, index=False, float_format="%.4f")
        print(f"wrote {path} ({len(wide):,} rows)")


def list_regions(month: str) -> list[tuple[str, str, str]]:
    """Page the Einzelheftsuche listing for every region published in `month`.

    Args:
        month: Reference month as `YYYYMM`.

    Returns:
        Tuples of region level, region code and region label. The region level is
        `"kreis"` for a five-digit AGS, `"jobcenter"` for a `t`-prefixed BA
        Dienststellennummer and `"other"` for the national, East/West and Länder
        aggregates.

    """
    regions: list[tuple[str, str, str]] = []
    page = 1
    while True:
        html = _get(LISTING_URL.format(page=page)).decode("utf-8", "replace")
        items = _LISTING_ITEM.findall(html)
        if not items:
            break
        reached_older_month = False
        for url, raw_title in items:
            if f"-{month}-" not in url:
                reached_older_month = True
                break
            match = _FILE_CODE.search(url)
            if match is None:
                msg = f"listing entry {url} does not carry a region code"
                raise ValueError(msg)
            code = match.group(1)
            title = re.sub(r"\s+", " ", unescape(_TAGS.sub("", raw_title))).strip()
            label = title.split("–", 1)[-1].strip()
            regions.append((_region_level(code), code, label))
        if reached_older_month:
            break
        page += 1
        time.sleep(0.2)
    return regions


def _region_level(code: str) -> str:
    if code.startswith("t"):
        return "jobcenter"
    if len(code) == 5 and code.isdigit():
        return "kreis"
    return "other"


def _parse_month(
    regions: list[tuple[str, str, str]],
    month: str,
    retrieved: str,
    manifest: list[dict[str, object]],
) -> pd.DataFrame:
    wanted = [r for r in regions if r[0] in {"kreis", "jobcenter"}]
    frames: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        payloads = list(pool.map(lambda region: _fetch_region(region, month), wanted))
    for (level, code, label), fetched in zip(wanted, payloads, strict=True):
        if fetched is None:
            print(f"  {code} not published for {month}, skipped")
            continue
        url, path, payload = fetched
        manifest.append(
            _manifest_row(level, code, label, month, url, payload, retrieved)
        )
        identity = BaWorkbookIdentity(
            region_level=level,
            region_code=code,
            region_label=label,
            reference_month=f"{month[:4]}-{month[4:]}",
        )
        frames.append(load_ba_workbook(path, identity))
    print(f"  parsed {len(frames)} workbooks for {month}")
    return pd.concat(frames, ignore_index=True)


def _fetch_region(
    region: tuple[str, str, str], month: str
) -> tuple[str, Path, bytes] | None:
    """Download one region's workbook, or return `None` when it was never published.

    Region codes come from the reference month's listing. A Kreis or Jobcenter
    created since an earlier month has no workbook there, and the portal answers
    404. That is a fact about the region, not a failure of the run.
    """
    _, code, _label = region
    url = FILE_URL.format(month=month, code=code)
    path = CACHE_DIR / f"kdu-{code}-0-{month}.xlsx"
    try:
        return url, path, _download(url, path)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def _download(url: str, path: Path) -> bytes:
    if path.exists():
        return path.read_bytes()
    payload = _get(url)
    path.write_bytes(payload)
    return payload


_BACKOFF_SECONDS = (30, 60, 120, 240, 480)
"""Waits between retries, in seconds.

The portal answers 403, 429 or 503 when a run requests faster than it serves.
"""


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "kdu-research/1.0"})
    for wait in (*_BACKOFF_SECONDS, None):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code not in {403, 429, 503} or wait is None:
                raise
            print(f"  {error.code} on {url.rsplit('/', 1)[-1]}, waiting {wait}s")
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            if wait is None:
                raise
            print(f"  {error} on {url.rsplit('/', 1)[-1]}, waiting {wait}s")
            time.sleep(wait)
    msg = f"could not download {url}"
    raise RuntimeError(msg)


def _manifest_row(
    level: str,
    code: str,
    label: str,
    month: str,
    url: str,
    payload: bytes,
    retrieved: str,
) -> dict[str, object]:
    return {
        "source": "BA Statistik, Wohn- und Kostensituation (Monatszahlen)",
        "region_level": level,
        "region_code": code,
        "region_label": label,
        "reference_month": f"{month[:4]}-{month[4:]}",
        "source_url": url,
        "retrieved_date": retrieved,
        "n_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


if __name__ == "__main__":
    main()
